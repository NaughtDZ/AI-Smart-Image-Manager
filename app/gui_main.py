import os
import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog, 
                               QSplitter, QLineEdit, QProgressBar, QMessageBox, QTabWidget,
                               QDialog, QCheckBox, QRadioButton, QButtonGroup, QFormLayout,
                               QComboBox, QSpinBox, QMenu)
from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QIcon, QAction, QCursor

from database import ImageDB
from workers import ImportWorker, ThumbnailWorker, TaggerWorker
from gui_viewer import ImageViewerWindow

# 样式
STYLE_SHEET = """
    QMainWindow { background-color: #2b2b2b; color: #ffffff; }
    QWidget { color: #ffffff; }
    QListWidget, QTreeWidget { background-color: #333333; border: 1px solid #444; }
    QListWidget::item:selected { background-color: #0078d7; }
    QLineEdit, QSpinBox, QComboBox { background-color: #333333; color: #ffffff; border: 1px solid #555; padding: 4px;}
    QPushButton { background-color: #444444; border: 1px solid #555; padding: 6px; }
    QPushButton:hover { background-color: #555555; }
    QTabWidget::pane { border: 1px solid #444; }
    QTabBar::tab { background: #333; color: #aaa; padding: 8px; }
    QTabBar::tab:selected { background: #444; color: #fff; }
    QGroupBox { border: 1px solid #555; margin-top: 10px; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
"""

# ================= 对话框类 =================

class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入选项")
        self.resize(400, 300)
        self.layout = QVBoxLayout(self)
        
        # 1. 递归选项
        self.chk_recursive = QCheckBox("递归扫描子目录")
        self.chk_recursive.setChecked(True)
        self.layout.addWidget(self.chk_recursive)
        
        # 2. 自动打标选项
        self.group_tag = QCheckBox("导入后立即自动打标")
        self.layout.addWidget(self.group_tag)
        
        # 3. 打标配置 (默认隐藏)
        self.tag_options = QWidget()
        self.tag_layout = QVBoxLayout(self.tag_options)
        
        # 模式
        self.lbl_mode = QLabel("打标模式:")
        self.tag_layout.addWidget(self.lbl_mode)
        self.btn_group_mode = QButtonGroup(self)
        self.rb_append = QRadioButton("追加 (Append)")
        self.rb_append.setChecked(True)
        self.rb_overwrite = QRadioButton("覆盖 (Overwrite)")
        self.rb_unique = QRadioButton("仅添加不重复 (Unique)")
        self.btn_group_mode.addButton(self.rb_append, 0)
        self.btn_group_mode.addButton(self.rb_overwrite, 1)
        self.btn_group_mode.addButton(self.rb_unique, 2)
        
        self.tag_layout.addWidget(self.rb_append)
        self.tag_layout.addWidget(self.rb_overwrite)
        self.tag_layout.addWidget(self.rb_unique)

        # 类型 (AI vs Regex) - 简化起见，导入时默认用 AI
        self.lbl_type = QLabel("注意：导入时仅支持 AI 自动打标")
        self.tag_layout.addWidget(self.lbl_type)

        self.layout.addWidget(self.tag_options)
        
        # 连接
        self.group_tag.toggled.connect(self.tag_options.setVisible)
        self.tag_options.setVisible(False)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("开始导入")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        self.layout.addLayout(btn_layout)

    def get_data(self):
        mode_map = {0: 'append', 1: 'overwrite', 2: 'unique'}
        return {
            'recursive': self.chk_recursive.isChecked(),
            'auto_tag': self.group_tag.isChecked(),
            'tag_mode': mode_map[self.btn_group_mode.checkedId()]
        }

class BatchTagDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量打标")
        self.resize(400, 350)
        self.layout = QVBoxLayout(self)
        
        # 1. 方式选择
        self.cmb_method = QComboBox()
        self.cmb_method.addItem("AI 自动识别", "ai")
        self.cmb_method.addItem("正则表达式 (文件名)", "regex")
        self.layout.addWidget(QLabel("打标方式:"))
        self.layout.addWidget(self.cmb_method)
        
        # 2. 正则输入框 (默认隐藏)
        self.regex_widget = QWidget()
        self.regex_layout = QVBoxLayout(self.regex_widget)
        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText("例如: (.*?)_image")
        self.regex_layout.addWidget(QLabel("正则表达式:"))
        self.regex_layout.addWidget(self.regex_input)
        self.layout.addWidget(self.regex_widget)
        self.regex_widget.setVisible(False)
        
        self.cmb_method.currentIndexChanged.connect(self.on_method_change)

        # 3. 模式选择
        self.layout.addWidget(QLabel("写入模式:"))
        self.btn_group = QButtonGroup(self)
        self.rb_append = QRadioButton("追加 (Append)")
        self.rb_append.setChecked(True)
        self.rb_overwrite = QRadioButton("覆盖 (Overwrite)")
        self.rb_unique = QRadioButton("仅添加不重复 (Unique)")
        self.btn_group.addButton(self.rb_append, 0)
        self.btn_group.addButton(self.rb_overwrite, 1)
        self.btn_group.addButton(self.rb_unique, 2)
        
        self.layout.addWidget(self.rb_append)
        self.layout.addWidget(self.rb_overwrite)
        self.layout.addWidget(self.rb_unique)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("开始")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        self.layout.addLayout(btn_layout)

    def on_method_change(self):
        is_regex = (self.cmb_method.currentData() == 'regex')
        self.regex_widget.setVisible(is_regex)

    def get_data(self):
        mode_map = {0: 'append', 1: 'overwrite', 2: 'unique'}
        return {
            'method': self.cmb_method.currentData(),
            'regex': self.regex_input.text(),
            'mode': mode_map[self.btn_group.checkedId()]
        }

# ================= 主窗口 =================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Image Manager Pro")
        self.resize(1300, 850)
        self.setStyleSheet(STYLE_SHEET)
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(self.base_dir, "..", "images.db")
        self.models_dir = os.path.join(self.base_dir, "models")
        
        self.db = ImageDB(self.db_path)
        
        # 状态
        self.current_page = 1
        self.page_size = 50
        self.total_images = 0
        self.current_filters = {}
        
        # AI 引擎缓存
        self.ai_engine = None 
        
        self.init_ui()
        self.refresh_all_data()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # ================= 左侧面板 =================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具栏
        tool_layout = QHBoxLayout()
        btn_import = QPushButton("导入")
        btn_import.clicked.connect(self.open_import_dialog)
        btn_batch = QPushButton("批量打标")
        btn_batch.clicked.connect(self.open_batch_tag_dialog)
        tool_layout.addWidget(btn_import)
        tool_layout.addWidget(btn_batch)
        left_layout.addLayout(tool_layout)
        
        # 搜索
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件名...")
        self.search_input.returnPressed.connect(self.apply_filters)
        left_layout.addWidget(self.search_input)
        
        # 选项卡 (Tag | Folder)
        self.left_tabs = QTabWidget()
        
        # Tab 1: Tags
        self.tag_list_widget = QListWidget()
        self.tag_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.tag_list_widget.itemSelectionChanged.connect(self.apply_filters)
        self.left_tabs.addTab(self.tag_list_widget, "标签")
        
        # Tab 2: Folders
        self.folder_list_widget = QListWidget()
        self.folder_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list_widget.customContextMenuRequested.connect(self.show_folder_menu)
        self.folder_list_widget.itemClicked.connect(self.on_folder_clicked) # 单击筛选
        self.left_tabs.addTab(self.folder_list_widget, "文件夹")
        
        left_layout.addWidget(self.left_tabs)
        splitter.addWidget(left_panel)
        
        # ================= 中间面板 (图片网格) =================
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        
        # 顶部栏 (页码控制)
        top_bar = QHBoxLayout()
        self.lbl_status = QLabel("就绪")
        
        page_ctrl_layout = QHBoxLayout()
        page_ctrl_layout.addWidget(QLabel("每页:"))
        self.cmb_page_size = QComboBox()
        self.cmb_page_size.addItems(["30", "50", "100", "200"])
        self.cmb_page_size.setCurrentIndex(1) # default 50
        self.cmb_page_size.currentIndexChanged.connect(self.on_page_size_change)
        page_ctrl_layout.addWidget(self.cmb_page_size)
        
        btn_prev = QPushButton("<")
        btn_prev.setFixedSize(30, 30)
        btn_prev.clicked.connect(self.prev_page)
        
        self.spin_page = QSpinBox()
        self.spin_page.setRange(1, 9999)
        self.spin_page.editingFinished.connect(self.jump_to_page)
        
        self.lbl_total_page = QLabel("/ 1")
        
        btn_next = QPushButton(">")
        btn_next.setFixedSize(30, 30)
        btn_next.clicked.connect(self.next_page)
        
        page_ctrl_layout.addWidget(btn_prev)
        page_ctrl_layout.addWidget(self.spin_page)
        page_ctrl_layout.addWidget(self.lbl_total_page)
        page_ctrl_layout.addWidget(btn_next)
        
        top_bar.addWidget(self.lbl_status)
        top_bar.addStretch()
        top_bar.addLayout(page_ctrl_layout)
        
        center_layout.addLayout(top_bar)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        center_layout.addWidget(self.progress_bar)
        
        # 图片列表
        self.image_list_widget = QListWidget()
        self.image_list_widget.setViewMode(QListWidget.IconMode)
        self.image_list_widget.setIconSize(QSize(150, 150))
        self.image_list_widget.setResizeMode(QListWidget.Adjust)
        self.image_list_widget.setSpacing(10)
        self.image_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.image_list_widget.itemDoubleClicked.connect(self.open_viewer)
        self.image_list_widget.itemSelectionChanged.connect(self.on_image_selected)
        center_layout.addWidget(self.image_list_widget)
        
        splitter.addWidget(center_panel)
        
        # ================= 右侧面板 (详细信息) =================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        right_layout.addWidget(QLabel("<b>图片信息</b>"))
        self.lbl_filename = QLabel("-")
        self.lbl_filename.setWordWrap(True)
        right_layout.addWidget(self.lbl_filename)
        
        right_layout.addWidget(QLabel("<b>当前标签:</b>"))
        self.info_tag_list = QListWidget()
        right_layout.addWidget(self.info_tag_list)
        
        splitter.addWidget(right_panel)
        
        # 比例设置
        splitter.setSizes([250, 800, 250])

    # ================= 数据加载与筛选 =================

    def refresh_all_data(self):
        self.load_tags_list()
        self.load_folders_list()
        self.refresh_image_list()

    def load_tags_list(self):
        self.tag_list_widget.clear()
        tags = self.db.get_all_tags()
        for tag in tags:
            self.tag_list_widget.addItem(tag)
            
    def load_folders_list(self):
        self.folder_list_widget.clear()
        folders = self.db.get_all_folders()
        
        # 添加一个“全部”选项
        item_all = QListWidgetItem("全部图片")
        item_all.setData(Qt.UserRole, None)
        self.folder_list_widget.addItem(item_all)
        
        for f in folders:
            item = QListWidgetItem(f)
            item.setData(Qt.UserRole, f)
            self.folder_list_widget.addItem(item)

    def refresh_image_list(self):
        self.image_list_widget.clear()
        
        # 获取筛选条件
        filters = {}
        keyword = self.search_input.text().strip()
        if keyword:
            filters['path_keyword'] = keyword
            
        selected_tags = [item.text() for item in self.tag_list_widget.selectedItems()]
        if selected_tags:
            filters['tags'] = selected_tags

        # 目录筛选
        curr_folder_item = self.folder_list_widget.currentItem()
        if curr_folder_item and curr_folder_item.data(Qt.UserRole):
            filters['exact_dir'] = curr_folder_item.data(Qt.UserRole)

        # 查询
        images, total_count = self.db.get_images_paginated(self.current_page, self.page_size, filters)
        self.total_images = total_count
        
        # 更新分页控件
        total_pages = (total_count + self.page_size - 1) // self.page_size
        if total_pages == 0: total_pages = 1
        
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(self.current_page)
        self.spin_page.setMaximum(total_pages)
        self.spin_page.blockSignals(False)
        
        self.lbl_total_page.setText(f"/ {total_pages} (Total: {total_count})")
        
        # 填充列表
        for img in images:
            item = QListWidgetItem(img['file_name'])
            item.setData(Qt.UserRole, img['id'])
            item.setData(Qt.UserRole + 1, img['file_path'])
            self.image_list_widget.addItem(item)
            
        # 线程加载缩略图
        if images:
            self.load_thumbnails(images)

    def load_thumbnails(self, images):
        if hasattr(self, 'thumb_worker') and self.thumb_worker.isRunning():
            self.thumb_worker.stop()
            self.thumb_worker.wait()
            
        self.thumb_worker = ThumbnailWorker(self.db_path, images, size=(200, 200))
        self.thumb_worker.thumbnail_ready.connect(self.update_thumbnail)
        self.thumb_worker.file_missing_signal.connect(self.on_file_missing)
        self.thumb_worker.start()

    @Slot(int, object)
    def update_thumbnail(self, img_id, pixmap):
        for i in range(self.image_list_widget.count()):
            item = self.image_list_widget.item(i)
            if item.data(Qt.UserRole) == img_id:
                item.setIcon(QIcon(pixmap))
                break

    @Slot(str)
    def on_file_missing(self, path):
        # 状态栏提示，但不弹窗打扰
        self.lbl_status.setText(f"移除不存在文件: {os.path.basename(path)}")
        # 刷新列表可能太频繁，暂时不刷新，等用户翻页自然刷新，或者等线程结束刷新
        # 如果需要实时刷新界面移除Item，可以在这里做，但需注意索引变化
        
    def apply_filters(self):
        self.current_page = 1
        self.refresh_image_list()

    def on_folder_clicked(self, item):
        self.current_page = 1
        self.refresh_image_list()

    def show_folder_menu(self, pos):
        item = self.folder_list_widget.itemAt(pos)
        if not item: return
        
        dir_path = item.data(Qt.UserRole)
        if not dir_path: return # "全部"选项不可删
        
        menu = QMenu()
        del_action = QAction(f"从数据库移除: {dir_path}", self)
        del_action.triggered.connect(lambda: self.remove_folder_from_db(dir_path))
        menu.addAction(del_action)
        menu.exec(self.folder_list_widget.mapToGlobal(pos))

    def remove_folder_from_db(self, dir_path):
        reply = QMessageBox.question(self, "确认删除", f"确定移除该文件夹的记录吗?\n{dir_path}\n(本地文件不会被删除)", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_images_by_dir(dir_path)
            self.load_folders_list()
            self.refresh_image_list()

    def on_image_selected(self):
        """显示右侧详细信息"""
        items = self.image_list_widget.selectedItems()
        self.info_tag_list.clear()
        self.lbl_filename.setText("-")
        
        if not items: return
        
        # 只显示第一个选中的图片信息
        item = items[0]
        img_id = item.data(Qt.UserRole)
        path = item.data(Qt.UserRole + 1)
        
        self.lbl_filename.setText(os.path.basename(path))
        
        tags = self.db.get_tags_for_image(img_id)
        for t in tags:
            self.info_tag_list.addItem(f"{t['name']} ({t['confidence']:.2f})")

    # ================= 分页逻辑 =================

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_image_list()

    def next_page(self):
        total_pages = (self.total_images + self.page_size - 1) // self.page_size
        if self.current_page < total_pages:
            self.current_page += 1
            self.refresh_image_list()

    def on_page_size_change(self):
        self.page_size = int(self.cmb_page_size.currentText())
        self.current_page = 1
        self.refresh_image_list()

    def jump_to_page(self):
        val = self.spin_page.value()
        if val != self.current_page:
            self.current_page = val
            self.refresh_image_list()

    # ================= 导入与打标 =================

    def open_import_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片目录")
        if not folder: return

        dialog = ImportDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            self.start_import(folder, data)

    def start_import(self, folder, options):
        self.import_worker = ImportWorker(self.db_path, [folder], options['recursive'])
        self.import_worker.status_signal.connect(self.lbl_status.setText)
        self.import_worker.progress_signal.connect(lambda c, t: self.lbl_status.setText(f"已导入: {c}"))
        
        # 传递 auto_tag 选项给 finish 回调
        self.import_worker.finished_signal.connect(lambda ids: self.on_import_finished(ids, options))
        
        self.lbl_status.setText("开始扫描...")
        self.import_worker.start()

    def on_import_finished(self, new_ids, options):
        self.lbl_status.setText("导入完成")
        self.load_folders_list()
        self.refresh_image_list()
        
        # 自动打标逻辑
        if options['auto_tag'] and new_ids:
            reply = QMessageBox.question(self, "自动打标", f"导入了 {len(new_ids)} 张图片，是否立即开始 AI 打标?", 
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.start_tagging_task(new_ids, 'ai', None, options['tag_mode'])

    def open_batch_tag_dialog(self):
        selected_items = self.image_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选择要打标的图片")
            return
            
        ids = [item.data(Qt.UserRole) for item in selected_items]
        
        dialog = BatchTagDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            self.start_tagging_task(ids, data['method'], data['regex'], data['mode'])

    def get_ai_engine(self):
        if self.ai_engine: return self.ai_engine
        
        # 延迟加载
        from ai_tagger import TaggerEngine
        model_path = os.path.join(self.models_dir, "model.onnx")
        tags_path = os.path.join(self.models_dir, "tag_mapping.json")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError("Model files missing")
            
        self.ai_engine = TaggerEngine(model_path, tags_path)
        return self.ai_engine

    def start_tagging_task(self, ids, method, regex, mode):
        engine = None
        if method == 'ai':
            try:
                self.lbl_status.setText("正在加载 AI 模型...")
                QApplication.processEvents()
                engine = self.get_ai_engine()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"AI 模型加载失败: {e}")
                return

        self.tag_worker = TaggerWorker(self.db_path, ids, mode=method, ai_engine=engine, 
                                       regex_pattern=regex, tag_action=mode)
        
        self.tag_worker.status_signal.connect(self.lbl_status.setText)
        self.tag_worker.progress_signal.connect(lambda c, t: self.progress_bar.setValue(int(c/t*100)))
        self.tag_worker.finished_signal.connect(self.on_tagging_finished)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.tag_worker.start()

    def on_tagging_finished(self):
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("打标任务完成")
        QMessageBox.information(self, "完成", "批量打标已完成")
        self.load_tags_list()
        # 刷新右侧信息
        self.on_image_selected()

    def open_viewer(self, item):
        current_id = item.data(Qt.UserRole)
        
        # 收集当前页数据
        current_page_images = []
        found_index = 0
        
        for i in range(self.image_list_widget.count()):
            list_item = self.image_list_widget.item(i)
            img_id = list_item.data(Qt.UserRole)
            img_path = list_item.data(Qt.UserRole + 1)
            
            current_page_images.append({'id': img_id, 'file_path': img_path})
            if img_id == current_id:
                found_index = i
        
        self.viewer = ImageViewerWindow(current_page_images, found_index)
        self.viewer.show()