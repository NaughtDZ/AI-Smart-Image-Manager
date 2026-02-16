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
        db = ImageDB(self.db_path)
        count = 0
        added_ids = []
        self.status_signal.emit("正在准备扫描...")
        
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
                        
                        if count % 50 == 0:
                            conn.commit()
                            self.progress_signal.emit(count, 0)
                            self.status_signal.emit(f"已导入: {count} 张")
            
            conn.commit()
            
        except Exception as e:
            print(f"[Worker Error] {e}")
            conn.rollback()
        finally:
            conn.close()

        self.finished_signal.emit(added_ids)

    def _insert_one(self, cursor, full_path, added_ids, file_name=None, dir_path=None, size=None):
        if file_name is None:
            file_name = os.path.basename(full_path)
        if dir_path is None:
            dir_path = os.path.dirname(full_path)
        if size is None:
            size = os.path.getsize(full_path)
            
        try:
            cursor.execute("INSERT OR IGNORE INTO images (file_path, file_name, dir_path, file_size) VALUES (?, ?, ?, ?)", 
                           (full_path, file_name, dir_path, size))
            
            cursor.execute("SELECT id FROM images WHERE file_path = ?", (full_path,))
            row = cursor.fetchone()
            if row:
                img_id = row['id']
                added_ids.append(img_id)
        except Exception as e:
            print(f"[Insert Error] {e}")

    def stop(self):
        self._is_running = False

# ==========================================
# 2. 缩略图生成 + 自动清理线程 (保持不变)
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
# 3. AI / 正则 打标工作线程 (增加 Skip 逻辑)
# ==========================================
class TaggerWorker(QThread):
    progress_signal = Signal(int, int)
    status_signal = Signal(str)
    finished_signal = Signal()
    
    def __init__(self, db_path, image_ids, mode='ai', ai_engine=None, regex_pattern=None, tag_action='append'):
        """
        tag_action: 'overwrite', 'append', 'unique', 'skip'
        """
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

        # 1. 覆盖模式：先清空
        if self.tag_action == 'overwrite':
            self.status_signal.emit("正在清理旧标签...")
            for idx, img_id in enumerate(self.image_ids):
                if not self._is_running: break
                db.clear_tags_for_image(img_id)
                if idx % 100 == 0:
                     self.status_signal.emit(f"正在清理旧标签... {idx}/{total}")

        conn = db.get_connection()
        cursor = conn.cursor()
        
        CHUNK_SIZE = 500 
        processed_count = 0
        
        try:
            for i in range(0, total, CHUNK_SIZE):
                if not self._is_running: break
                
                chunk_ids = self.image_ids[i : i + CHUNK_SIZE]
                
                placeholders = ','.join(['?'] * len(chunk_ids))
                query = f"SELECT id, file_path, file_name FROM images WHERE id IN ({placeholders})"
                
                cursor.execute(query, chunk_ids)
                rows = cursor.fetchall()
                
                for row in rows:
                    if not self._is_running: break
                    
                    img_id = row['id']
                    file_path = row['file_path']
                    file_name = row['file_name']
                    
                    # [NEW] Skip 模式逻辑检查
                    if self.tag_action == 'skip':
                        # 检查是否有任何 Tag
                        cursor.execute("SELECT 1 FROM image_tags WHERE image_id = ? LIMIT 1", (img_id,))
                        if cursor.fetchone():
                            # 如果有结果，说明有 Tag，直接跳过
                            processed_count += 1
                            if processed_count % 5 == 0:
                                self.progress_signal.emit(processed_count, total)
                                self.status_signal.emit(f"跳过已有标签: {processed_count}/{total}")
                            continue

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
                        # 转换模式给 DB
                        # 'skip' 模式下，对于没跳过的图片，行为等同于 append
                        db_mode = 'unique' if self.tag_action == 'unique' else 'append'
                        
                        for tag_name, conf in tags_to_add:
                            db.add_image_tag(img_id, tag_name, conf, 
                                             is_prediction=(1 if self.mode=='ai' else 0), 
                                             mode=db_mode)
                    
                    processed_count += 1
                    
                    if processed_count % 5 == 0:
                        self.progress_signal.emit(processed_count, total)
                        self.status_signal.emit(f"正在打标: {processed_count}/{total}")

        except Exception as e:
            print(f"[Tagger Error] {e}")
        finally:
            conn.close()

        self.finished_signal.emit()

    def stop(self):
        self._is_running = False