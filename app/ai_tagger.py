import json 
import os
import csv
import numpy as np
from PIL import Image, ImageOps
import onnxruntime as ort

print(f"Current Working Directory: {os.getcwd()}")
print(f"File exists check: {os.path.exists('app/models/model.onnx')}")
# ==========================================
# 1. 配置参数
# ==========================================
# 这些参数取决于你的模型训练时的输入尺寸，通常是 448x448
MODEL_INPUT_SIZE = 448 
THRESHOLD_DEFAULT = 0.35 # 默认置信度阈值

class TaggerEngine:
    def __init__(self, model_path: str, tags_path: str):
        self.model_path = model_path
        self.tags_path = tags_path
        self.tags_list = []
        self.session = None
        self.input_name = None
        
        # 1. 加载标签列表
        self.load_tags()
        
        # 2. 初始化 ONNX Runtime Session (DirectML)
        self.init_session()

    def load_tags(self):
        """加载 JSON 格式的标签映射文件"""
        if not os.path.exists(self.tags_path):
            raise FileNotFoundError(f"Tags file not found: {self.tags_path}")
            
        with open(self.tags_path, 'r', encoding='utf-8') as f:
            # tag_mapping.json 可能是列表 ["tag1", "tag2", ...]
            # 或者是字典 {"0": "tag1", "1": "tag2", ...}
            # 请根据你的文件内容调整。这里假设是简单的 Tag 名称列表或字典。
            data = json.load(f)
            
            if isinstance(data, list):
                self.tags_list = data
            elif isinstance(data, dict):
                # 假设 key 是 ID (str)，value 是 Tag Name
                # 我们需要按照 ID 顺序排序构建列表
                sorted_items = sorted(data.items(), key=lambda x: int(x[0]))
                self.tags_list = [v for k, v in sorted_items]
            else:
                raise ValueError("Unexpected JSON format for tags mapping.")

    def init_session(self):
        """初始化推理引擎，优先使用 DirectML (GPU)"""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        # 指定执行提供者顺序：优先 DirectML，其次 CPU
        providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
        
        try:
            self.session = ort.InferenceSession(self.model_path, providers=providers)
        except Exception as e:
            print(f"Failed to load DirectML provider, falling back to CPU. Error: {e}")
            self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
            
        self.input_name = self.session.get_inputs()[0].name
        # 输出节点名通常不需要显式获取，run() 第一个参数传 None 即可获取所有输出

    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        图片预处理:
        1. 加载图片，转为 RGB
        2. Resize 到模型输入尺寸 (448x448)，保持长宽比并填充白边/黑边 (Letterbox)
           或者简单的 Resize (这里采用简单的 Resize + Center Crop 或直接 Resize)
           为了简化，我们使用 Resize (LANCZOS)
        3. 归一化 (Normalize)
        4. Transpose (HWC -> CHW)
        5. Add Batch Dimension (CHW -> NCHW)
        """
        try:
            image = Image.open(image_path).convert('RGB')
            # 处理 Exif 旋转
            image = ImageOps.exif_transpose(image)
            
            # 1. Resize (简单的双线性插值)
            # 注意：高质量模型通常需要保持长宽比填充，这里简化为直接缩放
            # 如果效果不好，我们可以改为 Letterbox Pad
            image = image.resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), Image.Resampling.LANCZOS)
            
            # 2. 转为 Numpy 数组
            img_np = np.array(image).astype(np.float32)
            
            # 3. 归一化 (RGB 0-255 -> BGR? RGB? 0-1?)
            # 大多数 Tag 模型 (如 WD14) 使用 BGR 顺序且像素值在 0-255 或 0-1 之间
            # WD14 v2 模型通常是 RGB, 0-1, Mean/Std 无需特殊处理或简单归一化
            # 这里假设模型需要 0-1 输入
            img_np = img_np / 255.0
            
            # 有些模型需要标准化 (Mean=[0.485, ...], Std=[0.229, ...])
            # 但 WD14 ConvNextV2 不需要，只需 0-1
            
            # 4. HWC -> CHW (Height, Width, Channel -> Channel, Height, Width)
            img_np = img_np.transpose((2, 0, 1))
            
            # 5. 增加 Batch 维度 -> (1, 3, 448, 448)
            img_np = np.expand_dims(img_np, axis=0)
            
            return img_np
            
        except Exception as e:
            print(f"Error preprocessing image {image_path}: {e}")
            return None

    def predict(self, image_path: str, threshold: float = THRESHOLD_DEFAULT):
        """
        执行推理
        返回: list of (tag_name, confidence)
        """
        input_data = self.preprocess_image(image_path)
        if input_data is None:
            return []

        # 运行推理
        # onnx run(output_names, input_feed)
        # output_names=None 表示获取所有输出
        outputs = self.session.run(None, {self.input_name: input_data})
        
        # outputs[0] 是概率分布数组 (1, Num_Tags)
        probs = outputs[0][0] 
        
        # 过滤结果
        result_tags = []
        
        # 某些模型前 4 个 tag 是 ratings (general, sensitive, questionable, explicit)
        # 我们通常只需要后面的 content tags
        # 假设从 index 4 开始 (具体看 tags.csv)
        start_index = 4 
        
        for i in range(start_index, len(probs)):
            confidence = float(probs[i])
            if confidence > threshold:
                if i < len(self.tags_list):
                    tag_info = self.tags_list[i]
                    
                    # 处理 tag_info 是字典的情况
                    if isinstance(tag_info, dict):
                        tag_name = tag_info.get('tag', 'unknown') # 获取 tag 字段
                    else:
                        tag_name = str(tag_info)
                        
                    result_tags.append((tag_name, confidence))
        
        # 按置信度降序排列
        result_tags.sort(key=lambda x: x[1], reverse=True)
        
        return result_tags

# ==========================================
# 简单测试
# ==========================================
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(current_dir, "models", "model.onnx")
    tags_path = os.path.join(current_dir, "models", "tag_mapping.json") # 修改这里！
    
    print(f"Looking for model at: {model_path}")
    print(f"Looking for tags at: {tags_path}")
    
    if os.path.exists(model_path) and os.path.exists(tags_path):
        engine = TaggerEngine(model_path, tags_path)
        print("Engine initialized.")
        
        # 测试一张图片 (请替换为真实存在的图片路径)
        test_img = r"K:\2026-02-01-190557_3134174160.png"
        if os.path.exists(test_img):
            results = engine.predict(test_img)
            print("Predictions:")
            for tag, conf in results:
                print(f"  {tag}: {conf:.2f}")
        else:
            print(f"Test image not found: {test_img}")
    else:
        print("Model files still not found.")