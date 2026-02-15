# 🖼️ AI Smart Image Manager (本地 AI 图片管理工具)

一个基于 **Python + PySide6 + SQLite** 构建的轻量级、高性能本地图片管理软件。
它利用 **ONNX Runtime (DirectML)** 进行 GPU 加速的 AI 自动打标，无需复杂的 CUDA 配置，支持 NVIDIA/AMD/Intel 显卡。

> **核心理念**：不移动、不复制源文件，仅通过数据库管理元数据，保障您的文件归档结构不受干扰。

<img width="1954" height="1322" alt="image" src="https://github.com/user-attachments/assets/df57d3cc-1631-485a-a3b3-7f8d978be82d" />


## ✨ 主要特性

*   **📂 非破坏性管理**：通过文件路径索引图片，不修改、移动或重命名您的原始文件。
*   **🚀 AI 自动打标**：
    *   集成 `cl-tagger` (WD14) ONNX 模型。
    *   使用 **DirectML** 加速推理，支持 Windows 下主流显卡 (NVIDIA/AMD/Intel)。
    *   支持批量打标、追加/覆盖/去重模式。
*   **⚡ 高性能浏览**：
    *   **分页加载**机制，轻松处理数万张图片库。
    *   **多线程**异步生成缩略图，界面流畅不卡顿。
    *   自动检测并清理已删除文件的数据库记录。
*   **🔍 强大的筛选**：
    *   多标签组合筛选 (AND 逻辑)。
    *   按文件夹目录筛选。
    *   文件名关键词搜索。
*   **🛠️ 灵活的元数据提取**：
    *   支持通过 **正则表达式** 从文件名批量提取标签。
    *   支持导入时自动打标。
*   **🎨 内置看图器**：
    *   支持滚轮缩放、拖拽平移。
    *   支持键盘左右键翻页查看筛选结果。

## 🛠️ 技术栈

*   **语言**: Python 3.10+
*   **GUI 框架**: PySide6 (Qt for Python)
*   **数据库**: SQLite3
*   **AI 推理**: ONNX Runtime DirectML
*   **图像处理**: Pillow (PIL)

## 📥 安装与运行

本项目设计为“绿色版”运行，无需复杂的系统安装。

### 前置要求
*   Windows 10/11 (x64)
*   Python 3.10 或更高版本 (需添加到系统 PATH)

### 1. 克隆项目
```bash
git clone https://github.com/yourusername/AI-Image-Manager.git
cd AI-Image-Manager
```


### 2. 准备模型文件 (重要!)
由于模型文件较大，未包含在仓库中。请前往 HuggingFace 下载兼容 wd14-tagger 的 ONNX 模型。

特别感谢更好的cl-tagger和下载地址：https://huggingface.co/cella110n/cl_tagger

下载 .onnx 模型文件 (例如 wd-v1-4-convnextv2-tagger-v2.onnx)。
下载对应的标签映射文件 (通常是 selected_tags.csv 或 JSON 格式)。
将它们重命名并放入 app/models/ 目录：
模型文件 -> app/models/model.onnx
标签文件 -> app/models/tag_mapping.json (如果是 csv，请确保代码中适配或转换为 json)
### 3. 一键启动
双击项目根目录下的 start.bat。
脚本会自动检测并创建 venv 虚拟环境。
自动安装所需的依赖库 (requirements.txt)。
启动主程序。

## 📖 使用指南
### 1. 导入图片
点击左上角 “导入” 按钮。
选择包含图片的文件夹。
选项：
递归扫描：是否包含子文件夹。
自动打标：是否在导入时立即运行 AI 识别 (耗时较长，建议初次导入少量测试)。
### 2. 筛选与浏览
标签筛选：在左侧“标签”页签中选择一个或多个 Tag。
目录筛选：在左侧“文件夹”页签中选择特定目录。
查看大图：双击右侧缩略图进入大图模式，使用 滚轮 缩放，← → 键翻页。
### 3. 批量操作
批量打标：
在网格中框选或 Ctrl+Click 多选图片。
点击 “批量打标”。
选择 AI 识别 或 正则表达式。
选择写入模式：
追加：保留旧标签，添加新标签。
覆盖：清空旧标签，写入新标签。
仅添加不重复：只添加不存在的标签。
### 4. 移除文件夹
在左侧“文件夹”列表中，右键点击某个目录，选择“从数据库移除”。(这只会删除数据库记录，不会删除您的硬盘文件)。📁 目录结构

```
AI-Image-Manager/
├── app/
│   ├── models/            # [需手动放入] model.onnx 和 tag_mapping.json
│   ├── ai_tagger.py       # AI 推理核心
│   ├── database.py        # SQLite 数据库操作
│   ├── gui_main.py        # 主界面逻辑
│   ├── gui_viewer.py      # 大图查看器
│   ├── main.py            # 程序入口
│   ├── utils.py           # 工具函数
│   ├── workers.py         # 多线程任务 (导入/缩略图/AI)
│   └── requirements.txt   # 依赖列表
├── venv/                  # (自动生成) 虚拟环境
├── start.bat              # 一键启动脚本
└── README.md              # 说明文档

```

## 🤝 贡献
欢迎提交 Issue 或 Pull Request 来改进此项目！

## 📄 许可证
CC0-Free
