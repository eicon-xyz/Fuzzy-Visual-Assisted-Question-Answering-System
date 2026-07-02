# 校园 GPU 与 OmniParser 环境速查（v2）

> **用途**：汇总学校 GPU 实训平台接入、显存监控命令、OmniParser A800 环境约束，供 HAJIMI 项目联调参考。  
> **来源**：根目录 [`学生连接学校GPU实训网站操作手册.pdf`](../学生连接学校GPU实训网站操作手册.pdf)、[`GPU-显存占用率查看命令.pdf`](../GPU-显存占用率查看命令.pdf)、[`OmniParser GPU 环境交接文档.md`](../OmniParser%20GPU%20环境交接文档.md)  
> **最后更新**：2026-07-01

---

## 文档来源

| 文件 | 类型 | 用途 |
|------|------|------|
| [`学生连接学校GPU实训网站操作手册.pdf`](../学生连接学校GPU实训网站操作手册.pdf) | PDF | 如何连接学校 GPU 实训平台 |
| [`GPU-显存占用率查看命令.pdf`](../GPU-显存占用率查看命令.pdf) | PDF | Linux 下 GPU/显存监控命令速查 |
| [`OmniParser GPU 环境交接文档.md`](../OmniParser%20GPU%20环境交接文档.md) | Markdown | OmniParser v2 在 A800 容器内的已验证环境 |

---

## 一、学校 GPU 实训平台（操作手册）

### 1.1 平台架构

- 每个小组：**独立 Docker 容器 + 独立 GPU**
- 提供三种入口：**JupyterLab**、**VS Code Server**、**SSH**
- 内网宿主机 IP：`10.246.2.4` / `10.246.2.7` / `10.246.2.8`
- **必须连接校园网或学校 VPN** 才能访问；密码/Token 由指导教师单独发放，**禁止公开**

### 1.2 连接前需向教师确认

- 宿主机 IP、小组编号（group1–group4）
- SSH 端口、用户名（固定 `student`）、密码
- JupyterLab Token、VS Code Server 密码（**三者互不通用**）

### 1.3 各小组访问地址规律

端口规则（同一宿主机上，`{IP}` 替换为宿主机地址）：

| 小组 | JupyterLab | VS Code Server | SSH |
|------|------------|----------------|-----|
| group1 | `http://{IP}:18888/lab` | `http://{IP}:18080` | `ssh student@{IP} -p 12201` |
| group2 | `http://{IP}:28888/lab` | `http://{IP}:28080` | `-p 12202` |
| group3 | `http://{IP}:38888/lab` | `http://{IP}:38080` | `-p 12203` |
| group4 | `http://{IP}:48888/lab` | `http://{IP}:48080` | `-p 12204` |

示例（group1 @ 10.246.2.4）：

- JupyterLab: `http://10.246.2.4:18888/lab`
- VS Code: `http://10.246.2.4:18080`
- SSH: `ssh student@10.246.2.4 -p 12201`

### 1.4 推荐客户端

- **macOS**：Royal TSX（`royaltsx_6.4.3.1000.dmg`）
- **Windows**：MobaXterm（`MobaXterm_installer_25.2.msi`）

### 1.5 容器内标准目录

```
/workspace/code       # 代码
/workspace/datasets   # 数据集
/workspace/models     # 模型权重
/workspace/notebooks  # Notebook
```

登录后默认工作目录：`/workspace`

### 1.6 GPU 验证（必做）

JupyterLab / VS Code / SSH 中执行：

```python
import torch
print("CUDA available:", torch.cuda.is_available())
print("GPU count:", torch.cuda.device_count())
if torch.cuda.is_available():
    print("GPU name:", torch.cuda.get_device_name(0))
```

**正常**：`CUDA available: True`，`GPU count: 1`（每组只绑定 1 张 GPU，属正常现象）

或 SSH 中：`nvidia-smi`

### 1.7 SSH 隧道（浏览器无法直连时）

当 SSH 能连、浏览器不能开 Jupyter/VS Code 时，用本地端口转发。

**macOS 示例（group1 @ 10.246.2.4）**：

```bash
ssh \
  -L 18888:127.0.0.1:8888 \
  -L 18080:127.0.0.1:8080 \
  student@10.246.2.4 -p 12201
```

然后本机浏览器访问：

- JupyterLab: `http://127.0.0.1:18888/lab`
- VS Code: `http://127.0.0.1:18080`

**规律**：容器内目标端口固定（Jupyter `8888`，VS Code `8080`）；换小组只改 **SSH server IP 和 SSH port**；本机转发端口冲突时可改为 `19888`/`19080`。

### 1.8 Python 包安装建议

```bash
cd /workspace
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install 包名
```

- `/workspace` 下内容会持久化；直接装到系统环境可能在容器重建后丢失
- **禁止** `sudo rm -rf` 等高危命令；**不要**改 `/etc`、`/usr`、`/var`、`/root`

### 1.9 常见问题速查

| 现象 | 排查 |
|------|------|
| 浏览器无法访问 | 校园网/VPN → IP/端口 → 是否带 `/lab` → 试 SSH 隧道 |
| SSH 超时 | IP/端口错误、容器未启动、未连校园网 |
| Permission denied | 用户名 `student`、密码、是否误用其他组端口 |
| Token/密码无效 | Jupyter Token ≠ VS Code 密码 ≠ SSH 密码 |
| `CUDA available: False` | 先 `nvidia-smi`；失败则截图联系教师，**勿自行重启/改驱动** |

---

## 二、GPU 显存监控命令

### 2.1 最常用

```bash
nvidia-smi
```

关键字段：`Memory-Usage`（已用/总量）、`GPU-Util`（计算利用率）、`Processes`（占 GPU 进程）

### 2.2 持续刷新

```bash
watch -n 1 nvidia-smi          # 每 1 秒刷新
watch -d -n 1 nvidia-smi       # 高亮变化项
# Ctrl+C 退出
```

### 2.3 结构化查询

**显存占用**：

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv
```

**利用率 / 温度 / 功耗**：

```bash
nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit --format=csv
```

**当前占 GPU 的进程**：

```bash
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

### 2.4 实时监控工具

| 工具 | 安装 | 运行 |
|------|------|------|
| `nvidia-smi dmon` | 内置 | 持续看 sm/mem/温度/频率等 |
| `nvidia-smi pmon` | 内置 | 持续看各进程 GPU 占用 |
| `nvitop` | `pip install nvitop` | `nvitop`（类 htop，按 `q` 退出） |
| `gpustat` | `pip install gpustat` | `gpustat` / `watch -n 1 gpustat` |

### 2.5 按 PID 查进程

```bash
ps -fp <PID>
readlink -f /proc/<PID>/cwd
tr '\0' ' ' < /proc/<PID>/cmdline; echo
```

---

## 三、OmniParser GPU 环境交接

> 交接人：涂浚稷/20230353 · 适用：**A800 80GB** 学校 GPU 容器  
> 完整步骤与源码修改细节见 [`OmniParser GPU 环境交接文档.md`](../OmniParser%20GPU%20环境交接文档.md)

### 3.1 硬件与版本约束（切勿随意升级）

| 项 | 锁定值 |
|----|--------|
| GPU | NVIDIA A800-SXM4-80GB |
| Driver | 535.309.01 |
| 系统 CUDA | 12.2（向下兼容 11.8） |
| Python | 3.10.12 |
| PyTorch | **2.7.1+cu118**（不可用 cu121/cu130） |
| Transformers | **4.43.4**（新版不兼容 Florence-2） |

### 3.2 环境初始化要点

```bash
cd /workspace/code/omniparser_api
python3 -m venv .venv && source .venv/bin/activate

# HuggingFace 镜像（必须）
export HF_ENDPOINT=https://hf-mirror.com

# PyTorch cu118（上交镜像）
pip install torch==2.7.1+cu118 torchvision==0.22.1+cu118 torchaudio==2.7.1+cu118 \
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu118

# 核心依赖（严格版本）
pip install transformers==4.43.4 huggingface-hub==0.24.7
pip install paddleocr==2.8.1 paddlepaddle-gpu==2.6.1
pip install gradio==4.44.1 gradio-client==1.3.0
```

**警告**：不要无版本约束地 `pip install -r requirements.txt`。

### 3.3 模型权重与软链接

```bash
hf download microsoft/OmniParser-v2.0 --local-dir /workspace/models/OmniParser-v2.0
hf download microsoft/Florence-2-large --local-dir /workspace/models/Florence-2-large

cd /workspace/code/OmniParser/weights
ln -s /workspace/models/OmniParser-v2.0/icon_detect ./icon_detect
ln -s /workspace/models/Florence-2-large ./icon_caption_florence
```

Florence-2-large 为受限模型，需 HF 网页同意协议 + `hf auth login`。

### 3.4 必须做的 4 处源码修改

不修改则无法运行（详细改法见交接文档第 4 节）：

1. **`transformers/dynamic_module_utils.py`** — 注释掉 `flash_attn` 缺失时的 `raise ImportError`
2. **`modeling_florence2.py`（HF cache）** — `is_flash_attn_2_available()` 强制返回 `False`
3. **`gradio_client/utils.py`** — `get_type` 中加 `isinstance(schema, dict)` 判断
4. **`OmniParser/util/utils.py`** — OCR 空值赋 `[]`；排序 key 兼容 dict/list

### 3.5 验证与输出

```bash
cd /workspace/code/OmniParser
# 放置 test.png 后
python test_complete.py
```

成功产出：

- `output_labeled.png`（绿框=YOLO UI 元素，红框=OCR 文本）
- `result.json`（bbox、content、source 等）

Gradio（可选）：`python gradio_demo.py` → VS Code 端口转发访问 `http://127.0.0.1:7861`

### 3.6 已知踩坑

| 问题 | 解决 |
|------|------|
| PyTorch cu130 → `cuda.is_available()` False | 改用 **cu118** |
| PaddleOCR 3.x 报 `use_dilation` | 锁定 **paddleocr==2.8.1** |
| `flash_attn` 编译失败 | 不安装，改 transformers + Florence-2 源码 |
| Gradio `bool is not iterable` | 改 `gradio_client/utils.py` |

---

## 四、与 HAJIMI 项目的关系

```
操作手册 PDF  →  连接 Jupyter / VSCode / SSH
显存命令 PDF  →  nvidia-smi / nvitop 监控
交接文档 MD   →  OmniParser v2 on A800  →  A 端 ui_detector（可选远程部署）
```

| 场景 | 说明 |
|------|------|
| 本地 Windows 开发 | RTX 50 系：`start_omniparser.bat` 会 **实测 CUDA kernel**，不支持 sm_120 时强制 **CPU**（~2–4 分钟/帧）；校园 GPU 优先内网 API |
| **OmniParser 路径** | 项目根 `OmniParser/` + 自动回退 `E:\Tools\OmniParser`；见 [`Resize指示条与OmniParser路径-技术说明.md`](Resize指示条与OmniParser路径-技术说明.md) §三 |
| **学校 A800 容器** | 按 [A端-学校GPU部署与联调指南_v2.md](../server/docs/A端-学校GPU部署与联调指南_v2.md) 部署 GPU 版；B 端选「内网 API」 |
| **B 端系统设置** | `%LOCALAPPDATA%/HAJIMI/user_settings.json`：部署模式（本地/内网）、A 端 URL、LLM/OmniParser 配置；保存后立即生效 |
| **B 端** | 仅通过 HTTP 调用 A 端 `/process`、`/inspect`；内网模式不要求本机 OmniParser |

联调相关文档：[`B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md)、[`DAY2-工作内容.md`](DAY2-工作内容.md)、[`DAY3-工作内容_v2.md`](DAY3-工作内容_v2.md)、[`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md)、[`A端-GPU容器部署详细指南-group2_v2.md`](../server/docs/A端-GPU容器部署详细指南-group2_v2.md)、[`校园gpu使用.template.md`](校园gpu使用.template.md)（无密码模板；凭据见根目录 `校园gpu使用.md`）
