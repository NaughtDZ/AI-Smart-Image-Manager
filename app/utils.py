import os

# 支持的图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

def is_image_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS

def scan_directory_generator(root_dir: str, recursive: bool = True):
    """
    生成器：扫描目录下的图片文件
    yields: (full_path, file_name, dir_path, file_size)
    """
    root_dir = os.path.normpath(root_dir)
    
    if recursive:
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if is_image_file(file):
                    full_path = os.path.join(root, file)
                    yield full_path, file, root, os.path.getsize(full_path)
    else:
        # 仅当前目录
        if os.path.exists(root_dir):
            for file in os.listdir(root_dir):
                full_path = os.path.join(root_dir, file)
                if os.path.isfile(full_path) and is_image_file(file):
                    yield full_path, file, root_dir, os.path.getsize(full_path)