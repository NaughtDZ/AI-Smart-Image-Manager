import os
import time
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PIL import Image, ImageOps

from database import ImageDB
from utils import scan_directory_generator, is_image_file

# ==========================================
# 1. 导入图片工作线程 (高效版)
# ==========================================
class ImportWorker(QThread):
    progress_signal = Signal(int, int)
    status_signal = Signal(str)
    finished_signal = Signal(list)
    
    def __init__(self, db_path, target_paths, recursive=True):
        super().__init__()
        self.db_path = db_path
        self.target_paths = target_paths
        self.recursive = recursive
        self._is_running = True

    def run(self):
        # 初始化 DB 实例
        db = ImageDB(self.db_path)
        print(f"[Worker] Using DB Path: {db.db_path}")
        
        count = 0
        added_ids = []
        self.status_signal.emit("正在准备扫描...")
        
        # 【关键】建立长连接，而不是在循环里反复 open/close
        conn = db.get_connection_for_batch()
        cursor = conn.cursor()
        
        try:
            for path in self.target_paths:
                if not self._is_running: break
                
                if os.path.isfile(path):
                    if is_image_file(path):
                        self._insert_one(cursor, path, added_ids)
                        count += 1
                        
                elif os.path.isdir(path):
                    self.status_signal.emit(f"扫描目录: {path}")
                    for full_path, file_name, dir_path, size in scan_directory_generator(path, self.recursive):
                        if not self._is_running: break
                        
                        self._insert_one(cursor, full_path, added_ids, file_name, dir_path, size)
                        count += 1
                        
                        # 每 50 条提交一次，防止内存堆积，也防止全盘回滚
                        if count % 50 == 0:
                            conn.commit()
                            self.progress_signal.emit(count, 0)
                            self.status_signal.emit(f"已导入: {count} 张")
            
            # 最后提交剩余的数据
            conn.commit()
            print(f"[Worker] Import finished. Total: {count}, IDs gathered: {len(added_ids)}")
            
        except Exception as e:
            print(f"[Worker Error] {e}")
            conn.rollback()
        finally:
            conn.close()

        self.finished_signal.emit(added_ids)

    def _insert_one(self, cursor, full_path, added_ids, file_name=None, dir_path=None, size=None):
        """辅助函数：执行单条插入，不提交"""
        if file_name is None:
            file_name = os.path.basename(full_path)
        if dir_path is None:
            dir_path = os.path.dirname(full_path)
        if size is None:
            size = os.path.getsize(full_path)
            
        try:
            # 插入
            cursor.execute("INSERT OR IGNORE INTO images (file_path, file_name, dir_path, file_size) VALUES (?, ?, ?, ?)", 
                           (full_path, file_name, dir_path, size))
            
            # 获取 ID (如果是新插入的，rowid就是ID；如果是忽略的，查询ID)
            # 为了准确获取ID，我们还是查一次
            cursor.execute("SELECT id FROM images WHERE file_path = ?", (full_path,))
            row = cursor.fetchone()
            if row:
                img_id = row['id']
                added_ids.append(img_id)
                # print(f"[Debug] Inserted/Found ID: {img_id} - {file_name}")
        except Exception as e:
            print(f"[Insert Error] {e}")

    def stop(self):
        self._is_running = False

# ==========================================
# 2. 缩略图生成 + 自动清理线程
# ==========================================
class ThumbnailWorker(QThread):
    thumbnail_ready = Signal(int, object) 
    finished_signal = Signal()
    file_missing_signal = Signal(str) 

    def __init__(self, db_path, image_data_list, size=(256, 256)):
        super().__init__()
        self.db_path = db_path 
        self.image_data_list = image_data_list
        self.size = size
        self._is_running = True

    def run(self):
        db = ImageDB(self.db_path)
        for img_data in self.image_data_list:
            if not self._is_running: break
            
            file_path = img_data['file_path']
            img_id = img_data['id']
            
            if not os.path.exists(file_path):
                # print(f"[WARN] File missing: {file_path}")
                db.delete_image_by_id(img_id)
                self.file_missing_signal.emit(file_path)
                continue

            try:
                with Image.open(file_path) as img:
                    img = ImageOps.exif_transpose(img)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.thumbnail(self.size, Image.Resampling.LANCZOS)
                    data = img.tobytes("raw", "RGB")
                    qim = QImage(data, img.width, img.height, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qim)
                    self.thumbnail_ready.emit(img_id, pixmap)
            except Exception as e:
                pass
        self.finished_signal.emit()

    def stop(self):
        self._is_running = False

# ==========================================
# 3. AI / 正则 打标工作线程
# ==========================================
class TaggerWorker(QThread):
    progress_signal = Signal(int, int)
    status_signal = Signal(str)
    finished_signal = Signal()
    
    def __init__(self, db_path, image_ids, mode='ai', ai_engine=None, regex_pattern=None, tag_action='append'):
        super().__init__()
        self.db_path = db_path
        self.image_ids = image_ids
        self.mode = mode
        self.ai_engine = ai_engine
        self.regex_pattern = regex_pattern
        self.tag_action = tag_action
        self._is_running = True

    def run(self):
        db = ImageDB(self.db_path)
        total = len(self.image_ids)
        if not self.image_ids:
            self.finished_signal.emit()
            return

        if self.tag_action == 'overwrite':
            for img_id in self.image_ids:
                if not self._is_running: break
                db.clear_tags_for_image(img_id)

        conn = db.get_connection()
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(self.image_ids))
        cursor.execute(f"SELECT id, file_path, file_name FROM images WHERE id IN ({placeholders})", self.image_ids)
        rows = cursor.fetchall()
        conn.close() 
        
        count = 0
        for row in rows:
            if not self._is_running: break
            img_id = row['id']
            file_path = row['file_path']
            file_name = row['file_name']
            tags_to_add = []
            
            if self.mode == 'ai' and self.ai_engine:
                try:
                    tags = self.ai_engine.predict(file_path)
                    tags_to_add = tags 
                except Exception as e:
                    print(f"[ERROR] AI: {e}")

            elif self.mode == 'regex' and self.regex_pattern:
                import re
                try:
                    matches = re.findall(self.regex_pattern, file_name)
                    matches = list(set(matches))
                    tags_to_add = [(m, 1.0) for m in matches if m]
                except Exception as e:
                    print(f"[ERROR] Regex: {e}")

            if tags_to_add:
                db_mode = 'unique' if self.tag_action == 'unique' else 'append'
                for tag_name, conf in tags_to_add:
                    db.add_image_tag(img_id, tag_name, conf, 
                                     is_prediction=(1 if self.mode=='ai' else 0), 
                                     mode=db_mode)
            count += 1
            if count % 5 == 0:
                self.progress_signal.emit(count, total)
                self.status_signal.emit(f"处理中: {count}/{total}")

        self.finished_signal.emit()

    def stop(self):
        self._is_running = False