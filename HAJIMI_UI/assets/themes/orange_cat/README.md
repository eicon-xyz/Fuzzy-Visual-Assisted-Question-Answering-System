# 橘猫耄耋主题资源（Demo only）

本目录仅供 `python -m ui.style_preview_demo` 使用，**不会**被生产 `main.py` 加载。

## 目录

- `photos/` — **推荐**：UI 图标 + 全屏 splash 同目录，靠文件名区分
- `icons/` — 脚本输出的预处理后图标（Demo **优先**加载）
- `sounds/` — splash 音效（默认 `start.mp3`）

Demo 控制台指定的本地文件夹与 `photos/` 规则相同：图标按规范文件名放置；splash 随机池会自动**排除** UI 图标文件名。

## Demo 顶栏样式（控制台「顶栏样式」）

| 选项 | 效果 |
|------|------|
| 橘色玻璃顶栏 | 顶栏 52px 独立橘奶油玻璃层，比对话框区略深，带顶光高光 |
| 浓橘渐隐（上¼） | 顶栏浓橘色，向下延伸至窗口高度约 25% 后渐变为对话框奶油底色 |

顶栏由 shell 层绘制，TopBar 控件保持透明；与壳层模式（Maodiao / Crystal / QSS）可任意组合。

## Demo 气质预设（控制台「气质预设」）

| 选项 | 效果 |
|------|------|
| 清新近白（默认） | 近白 shell、白用户气泡、系统气泡左橘条、薄荷 focus/hover 点缀 |
| 暖奶油（原版） | 改前奶油风，便于 A/B 对比 |
| 高饱和活力 | 实心橘发送钮、更强 StatusBadge、系统气泡高对比 |

可与「顶栏样式」「壳层模式」任意组合切换。

## 图标清单（预处理后位于 `icons/`）

| 文件名 | 用途 | 预处理后尺寸 | Demo 显示 |
|--------|------|-------------|-----------|
| `mark.png` | 小窗 CompactMark（源：`CompactMark.png`） | 160×160 | 30px |
| `menu.png` | 顶栏汉堡菜单 | 128×128 | 24px |
| `mic.png` | 输入区麦克风 | 128×128 | 24px |
| `send.png` | 发送按钮 | 128×128 | 24px |
| `badge.png` | StatusBadge processing | 96×96 | 14px |
| `avatar.png` / `ai.png` | 聊天气泡 AI 侧头像（源：`AI.png`） | 128×128 | 36px |
| `app_icon.png`（可选） | 桌面 / App 图标备选（解析同 mark 系列） | 160×160 | — |

### 侧栏 / 抽屉导航（`icons/`）

与生产 [`MediumPanel`](ui/native/medium_panel.py) 导航抽屉一致；预处理后 **128×128**，Demo 显示 **22×22**。每个键只需一个全彩 PNG，未选中态由代码降透明度（约 55%），选中态全不透明 + NavItem 高亮。

| 文件名 | 用途 | 设计概念 |
|--------|------|----------|
| `guide.png` | 操作指引 | 猫爪指向靶心 / 猫眼 compass |
| `steps.png` | 步骤列表 | 三道猫爪痕 /  paw print 列表 |
| `blueprint.png` | 任务蓝图 | 折角蓝图 + 猫耳 |
| `notifications.png` | 提醒通知 | 铃铛顶加猫耳 |
| `settings.png` | 系统设置 | 猫爪拨齿轮 / 鱼骨齿轮 |
| `compact.png` | 小窗模式 | 橘猫蜷在胶囊条里 |
| `logout.png` | 退出 | 猫尾巴伸出门框 |

**格式：** PNG 透明背景；主体居中，留 10–15% 内边距；主色 `#E89540`–`#FFB366`，描边/五官 `#3A271B`；避免纯白主体。

## Splash 清单（`photos/`，非图标文件名）

以下文件进入全屏 splash 随机池；**不会**包含上表 UI 图标文件名（如 `menu.png`）。

| 文件名 | 用途 | 建议尺寸 |
|--------|------|----------|
| `default.png` | 默认 splash（优先播放） | 1024×1024 |
| `intro_01.png` | 随机池变体 1 | 1024×1024 |
| `intro_02.png` | 随机池变体 2 | 1024×1024 |
| `intro_03.png` | 可选：任务完成向 | 1024×1024 |
| `start.jpg` | **内置默认** splash（无控制台覆盖时优先于随机池） | 任意 |

以下头像文件仅用于聊天气泡，**不会**进入 splash 随机池：

| 文件名 | 用途 |
|--------|------|
| `AI.png` | 默认 AI / 系统侧圆形头像（中窗聊天气泡） |
| `me.gif` | 默认用户侧圆形头像（支持 GIF 动画） |
| `CompactMark.png` | 小窗 CompactMark / 桌面图标源图（**不会**进入 splash 池） |

主体约占画布 60–70%，便于全屏放大渐隐动画。

## Splash 音效（`sounds/`）

| 文件名 | 用途 |
|--------|------|
| `start.mp3` | **内置默认** splash 音效（动画开始时播放） |

Demo 控制台「选音效 / 清除」可覆盖为本地 `mp3` / `wav` / `ogg` 等；清除后恢复为 `sounds/start.mp3`。主题开启时会预加载音效；fade-out 阶段音量随画面同步淡出。

## 生图提示词

**风格基底（每条前加）：**

> Flat cartoon orange tabby cat meme style, warm soft orange palette (#FFB366 cream orange, #E89540 deep orange, #3A271B dark brown eyes), cute exaggerated expression, clean edges, minimal shading, transparent background, no text, no watermark, centered composition, mobile app icon quality, 2D sticker look

**分文件（在风格基底后追加）：**

- **mark.png** — Square app icon badge, close-up orange cat face, round cheeks, pink nose #F0A89A, smug meme vibe, 128x128
- **menu.png** — Hamburger menu OR three cat paw pads vertical, line icon, dark brown strokes, 96x96
- **mic.png** — Microphone with tiny cat ears on top, orange fill #FFB366, 96x96
- **send.png** — Paper plane / arrow send icon, cat paw pushing arrow, 96x96
- **badge.png** — Ultra-simple cat face emoji, bold for 14px, 64x64
- **avatar.png** — Circular-crop friendly cat portrait, friendly, 96x96
- **guide.png** — Bullseye target with tiny orange cat paw pointing center, operation guide metaphor, 96x96
- **steps.png** — Three horizontal cat scratch marks or paw print rows, checklist vibe, 96x96
- **blueprint.png** — Folded blueprint paper with cat ear corner, hexagon hint, task plan metaphor, 96x96
- **notifications.png** — Notification bell with cat ears on top, small orange body, 96x96
- **settings.png** — Cute gear with cat paw tab or fishbone gear teeth, 96x96
- **compact.png** — Orange cat curled inside horizontal pill capsule, minimize window metaphor, 96x96
- **logout.png** — Door frame with cat tail exiting, subtle logout arrow hint, 96x96
- **default.png** — Full meme portrait, smug/confused, head ~65% canvas, 1024x1024
- **intro_01.png** — Surprised wide eyes, mouth open, same character
- **intro_02.png** — Sleepy half-closed eyes, relaxed
- **intro_03.png** — Triumphant/proud, task completed, subtle sparkles

**负面提示词（建议每条附加）：**

> white background, gray background, photorealistic, 3D render, blurry, text, letters, logo, watermark, human, multiple cats, cluttered background, cold blue tone, pure white fur

## 替换说明

- 图标与 splash 可一并放入 `photos/`，或使用 Demo 控制台指定的本地文件夹
- 在 Demo 中可单独指定「默认 splash 图」，优先于随机池
- 在 Demo 中可单独指定 splash 音效；未指定时使用 `sounds/start.mp3`
- 请勿向 Git 提交未授权版权的梗图原图

## 资源预处理（推荐）

大图（如 2048×2048）直接放 `photos/` 会导致 Demo 运行时抠图卡顿。请先运行：

```bash
python scripts/preprocess_orange_cat_icons.py
```

脚本会：

1. 从 `photos/` 读取 UI 图标源文件（含 `CompactMark.png` → `mark` 等别名）
2. 缩略到 **128×128**（`mark` 为 **160×160**，`badge` 为 96×96）并去除白底
3. 输出真透明 PNG 到 `icons/`

Demo 加载顺序：**`icons/`（已处理）→ `photos/`（源图兜底）**。Splash 与 `start.jpg` 仍只从 `photos/` 读取。

可选参数：`--dry-run` 预览；`--source` / `--out` 自定义路径；`--size` 全局覆盖输出边长。
