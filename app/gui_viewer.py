import os
from PySide6.QtWidgets import (QMainWindow, QGraphicsView, QGraphicsScene, 
                               QGraphicsPixmapItem, QVBoxLayout, QWidget, QLabel)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QImage, QAction

class PhotoGraphicsView(QGraphicsView):
    """
    自定义的图形视图，拦截按键事件用于翻页
    """
    # 定义信号，通知主窗口翻页
    request_prev = Signal()
    request_next = Signal()

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        # 优化显示质量
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        # 允许鼠标拖拽平移
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        # 隐藏滚动条
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 背景色
        self.setStyleSheet("background-color: #222; border: none;")

    def wheelEvent(self, event):
        """滚轮缩放逻辑"""
        # 设置缩放锚点为鼠标位置
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        zoom_in = event.angleDelta().y() > 0
        scale_factor = 1.15 if zoom_in else 1 / 1.15
        self.scale(scale_factor, scale_factor)

    def keyPressEvent(self, event):
        """
        拦截按键：
        左右键 -> 发送翻页信号
        其他键 -> 交给父类处理（如 Esc）
        """
        if event.key() == Qt.Key_Left:
            self.request_prev.emit()
            event.accept() # 标记事件已处理
        elif event.key() == Qt.Key_Right:
            self.request_next.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

class ImageViewerWindow(QMainWindow):
    """
    大图查看器主窗口
    """
    def __init__(self, image_list, current_index=0):
        super().__init__()
        self.image_list = image_list
        self.current_index = current_index
        
        # 1. 创建场景
        self.scene = QGraphicsScene()
        
        # 2. 创建自定义的 View (使用上面的类)
        self.view = PhotoGraphicsView(self.scene)
        
        # 3. 连接翻页信号
        self.view.request_prev.connect(self.show_prev)
        self.view.request_next.connect(self.show_next)
        
        self.setCentralWidget(self.view)
        
        # 当前显示的 Item
        self.pixmap_item = None
        
        # 4. 加载初始图片
        self.load_image()
        
        # 5. 设置窗口默认大小
        self.resize(1000, 800)

    def load_image(self):
        if not self.image_list or self.current_index < 0 or self.current_index >= len(self.image_list):
            return
            
        img_data = self.image_list[self.current_index]
        file_path = img_data['file_path'] # 确保 gui_main 传进来的是字典包含 'file_path'
        
        self.setWindowTitle(f"Viewing: {os.path.basename(file_path)} ({self.current_index + 1}/{len(self.image_list)})")
        
        # 加载图片
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            print(f"Failed to load image: {file_path}")
            return
            
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        
        # 重置视图缩放
        self.view.resetTransform()
        
        # 适应窗口大小 (Fit to Window)
        self.fit_to_window()

    def fit_to_window(self):
        """让图片适应窗口大小"""
        if self.pixmap_item:
            # 强制刷新一下场景计算
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def show_prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_image()

    def show_next(self):
        if self.current_index < len(self.image_list) - 1:
            self.current_index += 1
            self.load_image()
            
    def keyPressEvent(self, event):
        # 处理 ESC 退出
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)