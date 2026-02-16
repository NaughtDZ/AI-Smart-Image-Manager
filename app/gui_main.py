import os
import sys
import subprocess
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
    QMenu { background-color: #333; border: 1px solid #555; }
    QMenu::item { padding: 5px 20px; }
    QMenu::item:selected { background-color: #0078d7; }
"""

# ================= 对话框类 =================

class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入选项")
        self.resize(400, 350)
        self.layout = QVBoxLayout(self)
        
        self.chk_recursive = QCheckBox("递归扫描子目录")
        self.chk_recursive.setChecked(True)
        self.layout.addWidget(self.chk_recursive)
        
        self.group_tag = QCheckBox("导入后立即自动打标")
        self.layout.addWidget(self.group_tag)
        
        self.tag_options = QWidget()
        self.tag_layout = QVBoxLayout(self.tag_options)
        
        self.lbl_mode = QLabel("打标模式:")
        self.tag_layout.addWidget(self.lbl_mode)
        self.btn_group_mode = QButtonGroup(self)
        
        self.rb_append = QRadioButton("追加 (Append)")
        self.rb_append.setChecked(True)
        self.rb_overwrite = QRadioButton("覆盖 (Overwrite)")
        self.rb_unique = QRadioButton("仅添加不重复 (Unique)")
        self.rb_skip = QRadioButton("跳过已有标签 (Skip)") # [NEW]
        
        self.btn_group_mode.addButton(self.rb_append, 0)
        self.btn_group_mode.addButton(self.rb_overwrite, 1)
        self.btn_group_mode.addButton(self.rb_unique, 2)
        self.btn_group_mode.addButton(self.rb_skip, 3) # [NEW]
        
        self.tag_layout.addWidget(self.rb_append)
        self.tag_layout.addWidget(self.rb_overwrite)
        self.tag_layout.addWidget(self.rb_unique)
        self.tag_layout.addWidget(self.rb_skip)

        self.lbl_type = QLabel("注意：导入时仅支持 AI 自动打标")
        self.tag_layout.addWidget(self.lbl_type)

        self.layout.addWidget(self.tag_options)
        
        self.group_tag.toggled.connect(self.tag_options.setVisible)
        self.tag_options.setVisible(False)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("开始导入")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        self.layout.addLayout(btn_layout)

    def get_data(self):
        # [NEW] 映射增加 skip
        mode_map = {0: 'append', 1: 'overwrite', 2: 'unique', 3: 'skip'}
        return {
            'recursive': self.chk_recursive.isChecked(),
            'auto_tag': self.group_tag.isChecked(),
            'tag_mode': mode_map[self.btn_group_mode.checkedId()]
        }

class BatchTagDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量打标")
        self.resize(400, 400)
        self.layout = QVBoxLayout(self)
        
        self.cmb_method = QComboBox()
        self.cmb_method.addItem("AI 自动识别", "ai")
        self.cmb_method.addItem("正则表达式 (文件名)", "regex")
        self.layout.addWidget(QLabel("打标方式:"))
        self.layout.addWidget(self.cmb_method)
        
        self.regex_widget = QWidget()
        self.regex_layout = QVBoxLayout(self.regex_widget)
        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText("例如: (.*?)_image")
        self.regex_layout.addWidget(QLabel("正则表达式:"))
        self.regex_layout.addWidget(self.regex_input)
        self.layout.addWidget(self.regex_widget)
        self.regex_widget.setVisible(False)
        
        self.cmb_method.currentIndexChanged.connect(self.on_method_change)

        self.layout.addWidget(QLabel("写入模式:"))
        self.btn_group = QButtonGroup(self)
        
        self.rb_append = QRadioButton("追加 (Append)")
        self.rb_append.setChecked(True)
        self.rb_overwrite = QRadioButton("覆盖 (Overwrite)")
        self.rb_unique = QRadioButton("仅添加不重复 (Unique)")
        self.rb_skip = QRadioButton("跳过已有标签 (Skip)") # [NEW]
        
        self.btn_group.addButton(self.rb_append, 0)
        self.btn_group.addButton(self.rb_overwrite, 1)
        self.btn_group.addButton(self.rb_unique, 2)
        self.btn_group.addButton(self.rb_skip, 3) # [NEW]
        
        self.layout.addWidget(self.rb_append)
        self.layout.addWidget(self.rb_overwrite)
        self.layout.addWidget(self.rb_unique)
        self.layout.addWidget(self.rb_skip)
        
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
        mode_map = {0: 'append', 1: 'overwrite', 2: 'unique', 3: 'skip'}
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
        
        self.current_page = 1
        self.page_size = 50
        self.total_images = 0
        self.current_filters = {}
        self.ai_engine = None 
        
        self.init_ui()
        self.refresh_all_data()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        tool_layout = QHBoxLayout()
        btn_import = QPushButton("导入")
        btn_import.clicked.connect(self.open_import_dialog)
        btn_batch = QPushButton("批量打标")
        btn_batch.clicked.connect(self.open_batch_tag_dialog)
        tool_layout.addWidget(btn_import)
        tool_layout.addWidget(btn_batch)
        left_layout.addLayout(tool_layout)
        
        # [NEW] 搜索栏 + 重置按钮
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件名...")
        self.search_input.returnPressed.connect(self.apply_filters)
        
        btn_reset = QPushButton("重置筛选")
        btn_reset.setToolTip("清除所有筛选条件 (关键词、标签、目录)")
        btn_reset.clicked.connect(self.clear_all_filters)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_reset)
        left_layout.addLayout(search_layout)
        
        self.left_tabs = QTabWidget()
        
        # 标签页
        tab_tags = QWidget()
        tags_layout = QVBoxLayout(tab_tags)
        tags_layout.setContentsMargins(0, 5, 0, 0)
        self.tag_search = QLineEdit()
        self.tag_search.setPlaceholderText("筛选标签...")
        self.tag_search.textChanged.connect(self.filter_tag_list)
        tags_layout.addWidget(self.tag_search)
        self.tag_list_widget = QListWidget()
        self.tag_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.tag_list_widget.itemSelectionChanged.connect(self.apply_filters)
        tags_layout.addWidget(self.tag_list_widget)
        self.left_tabs.addTab(tab_tags, "标签")
        
        # 文件夹页
        tab_folders = QWidget()
        folders_layout = QVBoxLayout(tab_folders)
        folders_layout.setContentsMargins(0, 5, 0, 0)
        self.folder_search = QLineEdit()
        self.folder_search.setPlaceholderText("筛选文件夹...")
        self.folder_search.textChanged.connect(self.filter_folder_list)
        folders_layout.addWidget(self.folder_search)
        self.folder_list_widget = QListWidget()
        self.folder_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_list_widget.customContextMenuRequested.connect(self.show_folder_menu)
        self.folder_list_widget.itemClicked.connect(self.on_folder_clicked)
        folders_layout.addWidget(self.folder_list_widget)
        self.left_tabs.addTab(tab_folders, "文件夹")
        
        left_layout.addWidget(self.left_tabs)
        splitter.addWidget(left_panel)
        
        # 中间面板
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        
        top_bar = QHBoxLayout()
        self.lbl_status = QLabel("就绪")
        
        page_ctrl_layout = QHBoxLayout()
        page_ctrl_layout.addWidget(QLabel("每页:"))
        self.cmb_page_size = QComboBox()
        self.cmb_page_size.addItems(["30", "50", "100", "200"])
        self.cmb_page_size.setCurrentIndex(1)
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
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        center_layout.addWidget(self.progress_bar)
        
        self.image_list_widget = QListWidget()
        self.image_list_widget.setViewMode(QListWidget.IconMode)
        self.image_list_widget.setIconSize(QSize(150, 150))
        self.image_list_widget.setResizeMode(QListWidget.Adjust)
        self.image_list_widget.setSpacing(10)
        self.image_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.image_list_widget.itemDoubleClicked.connect(self.open_viewer)
        self.image_list_widget.itemSelectionChanged.connect(self.on_image_selected)
        
        self.image_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_list_widget.customContextMenuRequested.connect(self.show_image_context_menu)
        
        center_layout.addWidget(self.image_list_widget)
        
        splitter.addWidget(center_panel)
        
        # 右侧面板
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
        splitter.setSizes([250, 800, 250])

    # ================= 逻辑处理 =================

    def refresh_all_data(self):
        self.load_tags_list()
        self.load_folders_list()
        self.refresh_image_list()

    def load_tags_list(self):
        self.tag_list_widget.clear()
        tags = self.db.get_all_tags()
        for tag in tags:
            self.tag_list_widget.addItem(tag)
        self.filter_tag_list(self.tag_search.text())
            
    def load_folders_list(self):
        self.folder_list_widget.clear()
        folders = self.db.get_all_folders()
        item_all = QListWidgetItem("全部图片")
        item_all.setData(Qt.UserRole, None)
        self.folder_list_widget.addItem(item_all)
        for f in folders:
            item = QListWidgetItem(f)
            item.setData(Qt.UserRole, f)
            self.folder_list_widget.addItem(item)
        self.filter_folder_list(self.folder_search.text())

    def filter_tag_list(self, text):
        search_text = text.lower()
        for i in range(self.tag_list_widget.count()):
            item = self.tag_list_widget.item(i)
            item.setHidden(search_text not in item.text().lower())

    def filter_folder_list(self, text):
        search_text = text.lower()
        for i in range(self.folder_list_widget.count()):
            item = self.folder_list_widget.item(i)
            item.setHidden(search_text not in item.text().lower())

    # [NEW] 一键清除所有筛选
    def clear_all_filters(self):
        self.search_input.clear()
        self.tag_search.clear()
        self.folder_search.clear()
        
        # 取消列表选择（blockSignals防止触发多次refresh）
        self.tag_list_widget.blockSignals(True)
        self.tag_list_widget.clearSelection()
        self.tag_list_widget.blockSignals(False)
        
        self.folder_list_widget.blockSignals(True)
        self.folder_list_widget.clearSelection()
        # 还要重置 "全部图片" 的选中状态
        if self.folder_list_widget.count() > 0:
            self.folder_list_widget.item(0).setSelected(True)
        self.folder_list_widget.blockSignals(False)
        
        self.current_page = 1
        self.refresh_image_list()

    def refresh_image_list(self):
        self.image_list_widget.clear()
        
        filters = {}
        keyword = self.search_input.text().strip()
        if keyword:
            filters['path_keyword'] = keyword
            
        selected_tags = [item.text() for item in self.tag_list_widget.selectedItems()]
        if selected_tags:
            filters['tags'] = selected_tags

        curr_folder_item = self.folder_list_widget.currentItem()
        if curr_folder_item and curr_folder_item.data(Qt.UserRole):
            filters['exact_dir'] = curr_folder_item.data(Qt.UserRole)

        images, total_count = self.db.get_images_paginated(self.current_page, self.page_size, filters)
        self.total_images = total_count
        
        total_pages = (total_count + self.page_size - 1) // self.page_size
        if total_pages == 0: total_pages = 1
        
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(self.current_page)
        self.spin_page.setMaximum(total_pages)
        self.spin_page.blockSignals(False)
        
        self.lbl_total_page.setText(f"/ {total_pages} (Total: {total_count})")
        
        for img in images:
            item = QListWidgetItem(img['file_name'])
            item.setData(Qt.UserRole, img['id'])
            item.setData(Qt.UserRole + 1, img['file_path'])
            self.image_list_widget.addItem(item)
        # [FIX] 强制刷新布局，解决图片重叠问题
        self.image_list_widget.doItemsLayout()
        if self.image_list_widget.count() > 0:
            self.image_list_widget.scrollToItem(self.image_list_widget.item(0))

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
        self.lbl_status.setText(f"移除不存在文件: {os.path.basename(path)}")

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
        if not dir_path: return
        menu = QMenu()
        del_action = QAction(f"从数据库移除: {dir_path}", self)
        del_action.triggered.connect(lambda: self.remove_folder_from_db(dir_path))
        menu.addAction(del_action)
        menu.exec(self.folder_list_widget.mapToGlobal(pos))

    def show_image_context_menu(self, pos):
        item = self.image_list_widget.itemAt(pos)
        if not item: return
        
        file_path = item.data(Qt.UserRole + 1)
        menu = QMenu()
        
        copy_action = QAction("复制完整路径", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(file_path))
        menu.addAction(copy_action)
        
        open_dir_action = QAction("打开所在文件夹", self)
        open_dir_action.triggered.connect(lambda: self.open_file_location(file_path))
        menu.addAction(open_dir_action)
        
        menu.exec(self.image_list_widget.mapToGlobal(pos))

    def open_file_location(self, path):
        if os.path.exists(path):
            try:
                subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            except Exception as e:
                print(f"Error opening explorer: {e}")

    def remove_folder_from_db(self, dir_path):
        reply = QMessageBox.question(self, "确认删除", f"确定移除该文件夹的记录吗?\n{dir_path}\n(本地文件不会被删除)", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_images_by_dir(dir_path)
            self.load_folders_list()
            self.refresh_image_list()

    def on_image_selected(self):
        items = self.image_list_widget.selectedItems()
        self.info_tag_list.clear()
        self.lbl_filename.setText("-")
        if not items: return
        item = items[0]
        img_id = item.data(Qt.UserRole)
        path = item.data(Qt.UserRole + 1)
        self.lbl_filename.setText(os.path.basename(path))
        tags = self.db.get_tags_for_image(img_id)
        for t in tags:
            self.info_tag_list.addItem(f"{t['name']} ({t['confidence']:.2f})")

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
        self.import_worker.finished_signal.connect(lambda ids: self.on_import_finished(ids, options))
        self.lbl_status.setText("开始扫描...")
        self.import_worker.start()

    def on_import_finished(self, new_ids, options):
        if not new_ids:
            QMessageBox.warning(self, "提示", "未找到任何图片！\n请检查文件夹内是否有 .jpg/.png 等支持的图片格式。")
        else:
            self.lbl_status.setText(f"导入完成 (新增 {len(new_ids)})")
            
        self.load_folders_list()
        self.refresh_image_list()
        
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
        self.on_image_selected()

    def open_viewer(self, item):
        current_id = item.data(Qt.UserRole)
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