import os

# 支持的图片格式 (确保包含点号，且全部小写)
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.gif', 
    '.webp', '.tiff', '.tif', '.ico'
}

def is_image_file(filename: str) -> bool:
    """检查文件后缀是否为图片"""
    ext = os.path.splitext(filename)[1].lower()
    # print(f"[DEBUG] Checking file: {filename} | Ext: {ext}") # 如果文件太多可以注释这行
    return ext in IMAGE_EXTENSIONS

def scan_directory_generator(root_dir: str, recursive: bool = True):
    """
    生成器：扫描目录下的图片文件
    """
    root_dir = os.path.normpath(root_dir)
    print(f"[DEBUG] Scanning Root: {root_dir} | Recursive: {recursive}")
    
    if not os.path.exists(root_dir):
        print(f"[ERROR] Path does not exist: {root_dir}")
        return

    if recursive:
        for root, dirs, files in os.walk(root_dir):
            print(f"[DEBUG] Walking: {root} | Found {len(files)} files")
            for file in files:
                if is_image_file(file):
                    full_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(full_path)
                        print(f"[DEBUG] YIELD: {file}")
                        yield full_path, file, root, size
                    except OSError as e:
                        print(f"[ERROR] Cannot read size: {file} - {e}")
                else:
                    # print(f"[DEBUG] Skipped (ext): {file}") 
                    pass
    else:
        # 仅当前目录
        print(f"[DEBUG] Scanning single dir: {root_dir}")
        for file in os.listdir(root_dir):
            full_path = os.path.join(root_dir, file)
            if os.path.isfile(full_path):
                if is_image_file(file):
                    print(f"[DEBUG] YIELD: {file}")
                    yield full_path, file, root_dir, os.path.getsize(full_path)
                else:
                    print(f"[DEBUG] Skipped (ext): {file}")