import os
import time
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PIL import Image, ImageOps

from database import ImageDB
from utils import scan_directory_generator, is_image_file

# ==========================================
# 1. 导入图片工作线程
# ==========================================
class ImportWorker(QThread):
    progress_signal = Signal(int, int)  # (新增数, 总数-这里暂未用)
    status_signal = Signal(str)
    finished_signal = Signal(list)      # 修改：返回新增的 image_id 列表，便于后续自动打标
    
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
        
        for path in self.target_paths:
            if not self._is_running: break
            
            if os.path.isfile(path):
                if is_image_file(path):
                    self.status_signal.emit(f"导入: {os.path.basename(path)}")
                    new_id = db.add_image(path, os.path.basename(path), os.path.dirname(path), os.path.getsize(path))
                    if new_id != -1:
                        added_ids.append(new_id)
                        count += 1
            elif os.path.isdir(path):
                self.status_signal.emit(f"扫描目录: {path}")
                for full_path, file_name, dir_path, size in scan_directory_generator(path, self.recursive):
                    if not self._is_running: break
                    
                    new_id = db.add_image(full_path, file_name, dir_path, size)
                    if new_id != -1:
                        added_ids.append(new_id)
                        count += 1
                    
                    if count % 10 == 0:
                        self.progress_signal.emit(count, 0) 
                        self.status_signal.emit(f"已导入: {count} 张")

        self.finished_signal.emit(added_ids)

    def stop(self):
        self._is_running = False

# ==========================================
# 2. 缩略图生成 + 自动清理线程
# ==========================================
class ThumbnailWorker(QThread):
    thumbnail_ready = Signal(int, object) 
    finished_signal = Signal()
    file_missing_signal = Signal(str) # 通知UI文件丢失

    def __init__(self, db_path, image_data_list, size=(256, 256)):
        super().__init__()
        self.db_path = db_path # 需要DB路径来删除记录
        self.image_data_list = image_data_list
        self.size = size
        self._is_running = True

    def run(self):
        # 使用独立连接删除记录
        db = ImageDB(self.db_path)
        
        for img_data in self.image_data_list:
            if not self._is_running: break
            
            file_path = img_data['file_path']
            img_id = img_data['id']
            
            # 1. 检查文件是否存在
            if not os.path.exists(file_path):
                # 自动删除逻辑
                print(f"File not found: {file_path}, deleting from DB.")
                db.delete_image_by_id(img_id)
                self.file_missing_signal.emit(file_path)
                continue

            # 2. 生成缩略图
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
        """
        tag_action: 'overwrite' (清空后添加), 'append' (添加/更新), 'unique' (仅添加不重复)
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

        # 1. 如果是覆盖模式，先批量清空这些图片的 Tag
        if self.tag_action == 'overwrite':
            self.status_signal.emit("正在清理旧标签...")
            for img_id in self.image_ids:
                if not self._is_running: break
                db.clear_tags_for_image(img_id)

        # 2. 获取图片信息
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
                    print(f"AI Error {file_path}: {e}")

            elif self.mode == 'regex' and self.regex_pattern:
                import re
                try:
                    # 正则匹配
                    matches = re.findall(self.regex_pattern, file_name)
                    # 结果去重
                    matches = list(set(matches))
                    tags_to_add = [(m, 1.0) for m in matches if m]
                except Exception as e:
                    print(f"Regex Error: {e}")

            # 写入数据库
            if tags_to_add:
                # 覆盖模式下，clear 已经在循环外做过了，这里 add 就行
                # 但是为了逻辑复用，我们传给 db 的 mode 只有 'append' 和 'unique'
                # 这里的 'overwrite' 已经在上面处理成了 '清空 + append'
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