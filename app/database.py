import sqlite3
import os
from typing import List, Tuple, Optional, Dict

class ImageDB:
    def __init__(self, db_path: str = "images.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                dir_path TEXT NOT NULL,
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_viewed TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_tags (
                image_id INTEGER,
                tag_id INTEGER,
                confidence REAL DEFAULT 1.0,
                is_prediction INTEGER DEFAULT 0,
                PRIMARY KEY (image_id, tag_id),
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        ''')
        
        conn.commit()
        conn.close()

    # ================= 图片操作 =================

    def add_image(self, file_path: str, file_name: str, dir_path: str, size: int = 0) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 插入或忽略 (保持原有 Tag 不变)
            cursor.execute("INSERT OR IGNORE INTO images (file_path, file_name, dir_path, file_size) VALUES (?, ?, ?, ?)", 
                           (file_path, file_name, dir_path, size))
            
            # 尝试获取ID
            cursor.execute("SELECT id FROM images WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                return row['id']
            return -1
        except Exception as e:
            print(f"Error adding image: {e}")
            return -1
        finally:
            conn.close()

    def delete_image_by_id(self, image_id: int):
        """删除单个图片记录"""
        conn = self.get_connection()
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        conn.commit()
        conn.close()

    def delete_images_by_dir(self, dir_path: str):
        """删除文件夹记录"""
        conn = self.get_connection()
        # 精确匹配
        conn.execute("DELETE FROM images WHERE dir_path = ?", (dir_path,))
        conn.commit()
        conn.close()

    def get_all_folders(self) -> List[str]:
        """获取所有已导入的文件夹路径 (去重)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT dir_path FROM images ORDER BY dir_path")
        folders = [row['dir_path'] for row in cursor.fetchall()]
        conn.close()
        return folders

    def get_images_paginated(self, page: int = 1, page_size: int = 50, filters: dict = None) -> Tuple[List[dict], int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        offset = (page - 1) * page_size
        
        query = "SELECT DISTINCT i.* FROM images i"
        params = []
        conditions = []

        if filters:
            # Tag 筛选
            if filters.get('tags'):
                tags = filters['tags']
                for tag in tags:
                    sub_query = """
                        EXISTS (
                            SELECT 1 FROM image_tags it 
                            JOIN tags t ON it.tag_id = t.id 
                            WHERE it.image_id = i.id AND t.name = ?
                        )
                    """
                    conditions.append(sub_query)
                    params.append(tag)

            # 关键字筛选
            if filters.get('path_keyword'):
                conditions.append("(i.file_name LIKE ? OR i.file_path LIKE ?)")
                kw = f"%{filters['path_keyword']}%"
                params.extend([kw, kw])
            
            # 目录筛选
            if filters.get('exact_dir'):
                 conditions.append("i.dir_path = ?")
                 params.append(filters['exact_dir'])

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        # 总数
        count_sql = f"SELECT COUNT(DISTINCT i.id) FROM images i {where_clause}"
        cursor.execute(count_sql, params)
        total_count = cursor.fetchone()[0]

        # 数据
        data_sql = f"{query} {where_clause} ORDER BY i.id DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        
        cursor.execute(data_sql, params)
        result = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return result, total_count

    # ================= Tag 操作 =================

    def add_tag(self, tag_name: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            conn.commit()
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            res = cursor.fetchone()
            return res['id'] if res else -1
        finally:
            conn.close()

    def clear_tags_for_image(self, image_id: int):
        """清空某张图片的所有标签 (用于覆盖模式)"""
        conn = self.get_connection()
        conn.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
        conn.commit()
        conn.close()

    def add_image_tag(self, image_id: int, tag_name: str, confidence: float = 1.0, is_prediction: int = 0, mode: str = 'append'):
        """
        mode:
          'overwrite': 调用此前应先调用 clear_tags_for_image (或者在此处逻辑处理)
                       但在批量操作中，通常是先清空一次，然后批量 add。
                       如果这里单条处理，overwrite 意义是 replace。
          'append': INSERT OR REPLACE (更新置信度)
          'unique': INSERT OR IGNORE (如果存在则不更新)
        """
        tag_id = self.add_tag(tag_name)
        if tag_id == -1: return

        conn = self.get_connection()
        cursor = conn.cursor()
        
        if mode == 'unique':
            # 仅添加不存在的
            cursor.execute("""
                INSERT OR IGNORE INTO image_tags (image_id, tag_id, confidence, is_prediction) 
                VALUES (?, ?, ?, ?)
            """, (image_id, tag_id, confidence, is_prediction))
        else: 
            # append / overwrite (在SQL层面 append 和 overwrite 单条记录是一样的，区别在于是否预先清空了旧tag)
            # 使用 REPLACE 更新置信度
            cursor.execute("""
                INSERT OR REPLACE INTO image_tags (image_id, tag_id, confidence, is_prediction) 
                VALUES (?, ?, ?, ?)
            """, (image_id, tag_id, confidence, is_prediction))
        
        conn.commit()
        conn.close()
        
    def get_tags_for_image(self, image_id: int) -> List[dict]:
        """获取某张图片的详细 tag 信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.name, it.confidence FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE it.image_id = ?
            ORDER BY it.confidence DESC
        ''', (image_id,))
        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tags

    def get_all_tags(self) -> List[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM tags ORDER BY name")
        tags = [row['name'] for row in cursor.fetchall()]
        conn.close()
        return tags