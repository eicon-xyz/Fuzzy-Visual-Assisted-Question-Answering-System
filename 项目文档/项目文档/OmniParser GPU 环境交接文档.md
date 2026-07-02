# OmniParser GPU 环境交接文档

## 1. 环境概览

本项目基于微软开源的 **OmniParser v2.0**，运行于学校分配的独立 GPU 容器中。由于涉及多个视觉大模型和 OCR 引擎，依赖关系极其复杂，**请接手人严格按照本文档的版本号和源码修改步骤执行，切勿随意升级任何依赖库**。

### 1.1 硬件与系统环境
- **GPU**: NVIDIA A800-SXM4-80GB (80GB 显存)
- **NVIDIA Driver**: 535.309.01
- **系统 CUDA Version**: 12.2 (向下兼容 11.8)
- **操作系统**: Ubuntu (Docker 容器环境)

### 1.2 Python 与核心框架版本
- **Python**: 3.10.12
- **PyTorch**: 2.7.1+cu118 (**必须使用 cu118 版本，不可使用 cu121/cu130，否则驱动不支持**)
- **Transformers**: 4.43.4 (**必须降级，新版不兼容 Florence-2 模型**)

---

## 2. 环境初始化步骤

### 2.1 创建与激活虚拟环境
```bash
cd /workspace/code/omniparser_api
python3 -m venv .venv
source .venv/bin/activate
```

### 2.2 配置 HuggingFace 国内镜像（必须）
学校容器直连 HuggingFace 会超时，必须配置镜像：
```bash
export HF_ENDPOINT=https://hf-mirror.com
# 建议将此命令加入 ~/.bashrc 以便每次登录自动生效
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
```

### 2.3 安装严格锁定的依赖
**警告**：不要直接运行 `pip install -r requirements.txt` 而不加限制，必须使用以下命令确保版本正确：

```bash
pip install --upgrade pip

# 1. 安装 PyTorch (CUDA 11.8 版本)
pip install torch==2.7.1+cu118 torchvision==0.22.1+cu118 torchaudio==2.7.1+cu118 --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu118

# 2. 安装核心 AI 库 (严格锁定版本)
pip install transformers==4.43.4 huggingface-hub==0.24.7
pip install gradio==4.44.1 gradio-client==1.3.0
pip install paddleocr==2.8.1 paddlepaddle-gpu==2.6.1
pip install numpy==1.23.5 opencv-python-headless==4.13.0.92

# 3. 安装其他辅助库
pip install einops timm ultralytics Pillow python-multipart fastapi uvicorn[standard]
```

---

## 3. 模型权重下载与目录映射

OmniParser 需要 YOLO 检测模型和 Florence-2 视觉语言模型。

### 3.1 下载模型权重
```bash
mkdir -p /workspace/models
cd /workspace/models

# 下载 OmniParser 核心权重
hf download microsoft/OmniParser-v2.0 --local-dir /workspace/models/OmniParser-v2.0

# 下载 Florence-2-large (A800 显存充足，直接使用 Large 版以获得最高精度)
# 注意：此模型为受限模型，需先在 HuggingFace 网页同意协议，并使用 hf auth login 登录
hf download microsoft/Florence-2-large --local-dir /workspace/models/Florence-2-large
```

### 3.2 建立软链接 (关键)
官方代码默认在 `OmniParser/weights/` 下寻找模型，需建立软链接映射：
```bash
cd /workspace/code/OmniParser
mkdir -p weights
ln -s /workspace/models/OmniParser-v2.0/icon_detect ./weights/icon_detect
ln -s /workspace/models/Florence-2-large ./weights/icon_caption_florence
```

---

## 4. 源码级修改（核心交接点 ⚠️）

由于开源库版本冲突和官方代码的边界情况 Bug，**必须对以下 4 个文件进行手动修改**，否则程序无法运行。

### 4.1 绕过 `flash_attn` 依赖检查
**原因**：`flash_attn` 编译困难且非必须，但 `transformers` 会强制检查。
**修改文件**：`/workspace/code/omniparser_api/.venv/lib/python3.10/site-packages/transformers/dynamic_module_utils.py`
**修改位置**：约第 180 行 `check_imports` 函数内。
**修改内容**：将 `raise ImportError` 注释掉。
```python
# 修改前：
if len(missing_packages) > 0:
    raise ImportError("This modeling file requires...")

# 修改后：
if len(missing_packages) > 0:
    print(f"⚠️ 警告：检测到缺失以下包，但已强制跳过检查: {missing_packages}")
    # raise ImportError(...)  <-- 注释掉这行
```

### 4.2 禁用 Florence-2 内部的 `flash_attn` 调用
**原因**：防止模型代码内部尝试 import `flash_attn` 导致崩溃。
**修改文件**：`/home/student/.cache/huggingface/modules/transformers_modules/icon_caption_florence/modeling_florence2.py`
**修改内容**：
1. 找到 `def is_flash_attn_2_available():`，将其返回值强制改为 `False`。
2. 找到 `from flash_attn import ...`，将其注释掉，并加上 `pass`。
```python
def is_flash_attn_2_available():
    return False  # 强制禁用

if is_flash_attn_2_available():
    pass
    # from flash_attn import flash_attn_func...  <-- 注释掉
```

### 4.3 修复 Gradio 4.44.1 的 JSON Schema 解析 Bug
**原因**：Gradio 4.44.1 在处理 `additionalProperties: false` 时会报错 `TypeError: argument of type 'bool' is not iterable`。
**修改文件**：`/workspace/code/omniparser_api/.venv/lib/python3.10/site-packages/gradio_client/utils.py`
**修改位置**：约第 863 行 `get_type` 函数内。
**修改内容**：增加类型判断。
```python
# 修改前：
if "const" in schema:

# 修改后：
if isinstance(schema, dict) and "const" in schema:
```

### 4.4 修复 OmniParser 官方 OCR 空值与类型 Bug
**原因**：当截图无文字时，官方代码未做判空处理，导致 `NoneType` 和 `list indices` 报错。
**修改文件**：`/workspace/code/OmniParser/util/utils.py`
**修改内容**：
1. 找到 `no ocr bbox!!!` 打印处，增加空列表赋值：
```python
if ocr_bbox is None:
    print('no ocr bbox!!!')
    ocr_bbox = []  # 新增
    ocr_text = []  # 新增
```
2. 找到 `filtered_boxes_elem = sorted(...)` 处，修改排序逻辑以兼容字典和列表：
```python
# 修改前：
filtered_boxes_elem = sorted(filtered_boxes, key=lambda x: x['content'] is None)

# 修改后：
def safe_get_content(x):
    return x.get('content') is None if isinstance(x, dict) else True
filtered_boxes_elem = sorted(filtered_boxes, key=safe_get_content)
```

---

## 5. 日常操作说明

### 5.1 运行完整解析测试
项目根目录下提供了稳定版测试脚本 `test_complete.py`，它会调用 YOLO、PaddleOCR 和 Florence-2，并输出结构化结果。

1. **准备图片**：将需要解析的截图上传至 `/workspace/code/OmniParser/`，命名为 `test.png`。
2. **执行脚本**：
   ```bash
   cd /workspace/code/OmniParser
   python test_complete.py
   ```
3. **查看结果**：
   - 终端会打印推理进度。
   - 目录下会生成 `output_labeled.png`（带标注框的图片）。
   - 目录下会生成 `result.json`（完整的结构化 JSON 数据）。

### 5.2 启动 Gradio 可视化界面 (可选)
虽然底层模型已跑通，但 Gradio 界面在学校内网代理下可能存在 POST 请求限制。如需启动：
```bash
cd /workspace/code/OmniParser
python gradio_demo.py
```
启动后，可通过 VS Code Server 的端口转发功能访问 `http://127.0.0.1:7861`。

---

## 6. 工作过程与踩坑记录 (示例)

在配置环境的过程中，我们遇到了多个典型的“依赖地狱”问题。以下是解决过程的记录，供接手人参考：

### 示例 1：PyTorch 版本与显卡驱动不匹配
- **现象**：安装最新版 PyTorch (`cu130`) 后，运行 `torch.cuda.is_available()` 返回 `False`，报错 `The NVIDIA driver on your system is too old`。
- **原因**：学校 A800 的驱动最高支持 CUDA 12.2，而 `cu130` 需要更新的驱动。
- **解决**：卸载 PyTorch，强制安装向下兼容的 `cu118` 版本：
  `pip install torch==2.7.1+cu118 ... --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu118`

### 示例 2：PaddleOCR 3.x 废弃旧参数
- **现象**：运行时报错 `ValueError: Unknown argument: use_dilation`。
- **原因**：`pip install paddleocr` 默认安装了 3.x 版本，移除了 2.x 的参数。
- **解决**：降级到官方代码兼容的 2.8.1 版本：
  `pip install paddleocr==2.8.1 paddlepaddle-gpu==2.6.1`

### 示例 3：`flash_attn` 编译地狱
- **现象**：模型加载时报错 `ImportError: ... requires ... flash_attn`。尝试 `pip install flash_attn` 会触发 C++ 源码编译，因容器缺少 `nvcc` 编译器而失败。
- **解决**：放弃安装。通过修改 `transformers` 的 `dynamic_module_utils.py` 屏蔽依赖检查，并修改微软 Florence-2 的缓存源码 `modeling_florence2.py` 禁用其内部调用，强制使用 PyTorch 原生 Attention 机制。

### 示例 4：Gradio JSON Schema 解析崩溃
- **现象**：Gradio 启动后，访问网页报 `TypeError: argument of type 'bool' is not iterable`。
- **原因**：Gradio 4.44.1 的 `gradio_client/utils.py` 在处理 `additionalProperties: false` 时，未判断 `schema` 是否为字典，直接执行了 `in` 操作。
- **解决**：直接修改虚拟环境中的 `gradio_client/utils.py` 源码，加上 `isinstance(schema, dict)` 判断。

---

## 7. 预期成果展示

当 `test_complete.py` 成功运行后，您将获得以下成果：

### 7.1 结构化数据 (`result.json`)
JSON 文件包含图片尺寸、元素总数，以及每个 UI 元素的详细信息。每个元素包含：
- `id`: 元素唯一标识。
- `type`: 元素类型（`ui_element` 为图标/按钮，`text` 为纯文本）。
- `bbox`: 边界框坐标 `[x1, y1, x2, y2]`。
- `content`: 语义描述（如“这是一个搜索框”）或 OCR 识别出的文字。
- `source`: 来源模型（`yolo`, `paddle_ocr`）。

### 7.2 可视化标注图 (`output_labeled.png`)
- **绿色框**：YOLO 检测出的可交互 UI 元素（按钮、图标等），并附有 Florence-2 生成的简短描述。
- **红色框**：PaddleOCR 识别出的纯文本区域。

---
*文档生成日期：2026-06-29*
*适用环境：学校 GPU 实训平台 (A800 80GB)*
*交接人：[涂浚稷/20230353]*