# Win+Search 启动通道 — 设计文档

## 目标

放弃不可靠的"桌面图标视觉识别"，改用 **Win键→开始菜单搜索→OmniParser OCR匹配→点击结果** 启动应用。

## 根本原因

当前 icon_stitch 方案：LLM 看图识别 19 个放大到 200px 的桌面图标 → 返回 element_id。
实测结果：NetEase 映射到 ~56（面积 155412 的巨大误检区），5 个 target 中 3 个映射到同一 false ID。
**Qwen2.5-VL-7B 在小图标识别上不可靠，且不可修复。**

## 新管道设计

```
用户指令 "打开网易云音乐，放首歌"
    │
    ▼
阶段1: 应用启动（Win+Search 通道）
    │
    ├─ press_keys('win')           # 打开开始菜单
    ├─ pyperclip + ctrl+v 粘贴搜索词   # 绕过输入法干扰
    ├─ sleep(800ms)                 # 等待搜索结果渲染
    ├─ mss 截图 → OmniParser        # 检测搜索结果区域
    ├─ 遍历 OCR text 字段           # 匹配 "网易云"/"netease" 等
    ├─ 取匹配 bbox → click_at()     # 启动应用
    └─ sleep(3s) 等待应用打开
    │
    ▼
阶段2: 应用内操作（OmniParser 检测 UI 元素）
    │
    ├─ 截图 → OmniParser            # 检测已打开应用的 UI
    ├─ LLM 看图规划接下来的步骤     # 生成 "点击搜索框→输入歌名→点播放" 等
    ├─ 每步：OmniParser 定位 → click
    └─ 每步：截图验证
```

## 模块修改

### 新增: `server/services/launcher.py`
```python
def launch_app(app_name: str) -> dict:
    """
    Win+Search 通道启动应用。
    1. press Win
    2. Paste app_name via clipboard
    3. Wait 800ms
    4. Screenshot → OmniParser
    5. Match OCR text → find bbox
    6. Click
    Returns: {"success": True, "app_name": str, "clicked": (x,y)}
    """

def _match_ocr_to_app(ocr_items: list, app_name: str) -> Optional[dict]:
    """
    将 OmniParser OCR 文本匹配到目标应用名。
    支持: 精确匹配 → 模糊匹配 → 拼音匹配
    Returns: {"bbox": [...], "text": "..."} or None
    """
```

### 修改: `server/services/planning/router.py` `process_query()`
- **移除** icon_stitch 的 identify_from_strips 调用
- **替换为** `launcher.launch_app()` 调用
- 启动成功后，第二阶段用现有 LLM 规划后续操作

### 删除: `server/services/icon_stitch.py`
不再需要

### 保留: `server/services/executor/` (engine, clicker, safety)
不变

### 保留: `server/services/omniparser_client.py`
不变

### 保留: `core/screen_capture.py`
不变

## 验收标准

1. `launch_app("NetEase Cloud Music")` → 成功打开网易云音乐
2. `launch_app("Calculator")` → 成功打开计算器
3. `launch_app("Notepad")` → 成功打开记事本
4. 全管道: "打开网易云音乐，放首歌" → 应用打开 + 后续操作规划执行
5. 30 tests passed
