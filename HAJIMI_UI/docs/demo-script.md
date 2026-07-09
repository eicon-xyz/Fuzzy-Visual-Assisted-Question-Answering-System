# HAJIMI 演示视频任务脚本

## 可用工具矩阵

| 类别 | 工具 | 说明 |
|------|------|------|
| 桌面应用 | `launch_app` | 系统级启动，L1映射表(60+应用) → L2 PATH查找 → L3 Win+搜索 |
| 桌面操作 | `click` / `double_click` / `type_text` / `press_key` / `scroll` / `wait` | 基于OmniParser元素检测的精确操作 |
| 浏览器 | `browser_navigate` / `browser_snapshot` / `browser_click` / `browser_type` / `browser_scroll` / `browser_screenshot` / `browser_close` | Playwright/CDP DOM级精确控制 |
| 意向识别 | 内置管线 | 9类意图分类(SetFit+关键词) + 红线安全检查(23条) + L2/L3复杂度路由 |
| 自动记忆 | 内置管线 | 3层记忆(用户画像/成功模式/失败教训) + embedding检索 + 去重合并 |

## 配置参数

| 参数 | 值 |
|------|-----|
| MAX_TOOL_CALL_ROUNDS | 50 |
| STEP_RETRY_LIMIT | 3 |

---

## 场景一：AI辅助内容创作（办公场景）

**用户指令**：
> 打开记事本，写一篇500字关于人工智能的短文，标题为"AI改变生活"，写完保存到桌面

**现实场景**：用户需要快速起草文档、会议纪要、邮件草稿，AI直接操作编辑器完成。

**展示能力点**：应用启动映射表、中文文本输入、键盘快捷键、多步协同

**预期步骤**：
1. launch_app("记事本") — 映射表命中notepad.exe
2. type_text(输入框, 短文内容) — 剪贴板粘贴中文
3. press_key("ctrl+s") — 触发保存对话框
4. type_text(文件名输入框, "AI改变生活.txt")
5. 选择桌面路径，确认保存

**录制要点**：展示记事本自动打开并开始输入中文内容，最后桌面出现保存好的文件。

---

## 场景二：网页信息采集与整理（研究场景）

**用户指令**：
> 打开浏览器访问 GitHub Trending Python 页面，浏览前三个项目，记录每个项目的名称、Star数、简介，最后用记事本整理成表格保存到桌面

**现实场景**：开发者日常需要追踪热门开源项目、技术选型调研、竞品分析。

**展示能力点**：浏览器DOM操作、页面导航、结构化信息提取、跨应用数据流转

**预期步骤**：
1. browser_navigate("https://github.com/trending/python?since=daily")
2. browser_snapshot() → 获取页面可交互元素列表
3. browser_click(第一个项目链接) → 进入详情页
4. browser_snapshot() → 提取Star数、简介
5. 重复处理第二、第三个项目
6. launch_app("记事本")
7. type_text(输入框, Markdown格式表格)
8. press_key("ctrl+s") → 保存到桌面

**录制要点**：浏览器自动导航、页面快照、元素点击提取信息，最终记事本出现整理好的数据表格。

---

## 场景三：多应用协同工作流（生产场景）

**用户指令**：
> 帮我从百度搜索"2025年人工智能发展趋势"，把搜索结果里的前三条关键信息复制到记事本，然后保存到桌面

**现实场景**：用户日常的"搜索→阅读→摘录→整理"工作流，AI一次性完成。

**展示能力点**：搜索引擎操作、文本输入、页面滚动、内容提取、跨应用协同

**预期步骤**：
1. browser_navigate("https://www.baidu.com")
2. browser_type(搜索框, "2025年人工智能发展趋势")
3. browser_press_key("Enter")
4. browser_snapshot() → 获取搜索结果
5. browser_click(第一个结果链接)
6. browser_screenshot() → 截取页面内容
7. browser_snapshot() → 提取关键信息
8. launch_app("记事本")
9. type_text(输入框, 提取的关键信息)
10. press_key("ctrl+s") → 保存

**录制要点**：从搜索到摘录到保存的完整自动化流程，展现"一句话完成半小时工作"的价值。

---

## 场景四：注册表单自动填写（测试/效率场景）

**用户指令**：
> 打开浏览器访问 http://127.0.0.1:8765/registration_form.html，填写一份职业技术培训报名表，姓名张三，手机号13812345678，邮箱zhangsan@example.com，然后提交

**现实场景**：测试工程师需要反复填写表单验证功能；HR需要批量录入信息；用户频繁注册各类平台。

**展示能力点**：表单元素定位、多字段填充、提交按钮点击、DOM级精确操作

**预期步骤**：
1. browser_navigate("http://127.0.0.1:8765/registration_form.html")
2. browser_snapshot() → 获取表单元素列表
3. browser_type(姓名字段, "张三")
4. browser_type(手机号字段, "13812345678")
5. browser_type(邮箱字段, "zhangsan@example.com")
6. browser_type(培训项目字段, "Python全栈开发")
7. browser_click(提交按钮)
8. browser_snapshot() → 验证提交成功

**录制要点**：展示浏览器打开本地页面、逐字段精确填写、提交成功。

---

## 场景五：失败容错与自动恢复（鲁棒性场景）

**用户指令**：
> 用WPS打开我不存在的目录下的report.docx文件

**现实场景**：用户可能给出不存在的路径、拼写错误的文件名，AI需要优雅处理而非崩溃。

**展示能力点**：安全红线、意图分类、重试机制(3次)、失败教训记忆

**预期流程**：
1. 红线检查通过
2. 意图分类 → file_management
3. Agent尝试打开文件
4. 文件不存在 → 自动重试（变换路径、搜索文件）
5. 重试3次后放弃 → 标记失败
6. 触发 failure_lesson 记忆提取（存入 `t_memories`）

**录制要点**：展示重试日志、优雅失败提示、数据库中出现failure_lesson记录。

---

## 场景六：批量文件整理（效率场景）

**用户指令**：
> 帮我把桌面上的所有截图文件移动到 D:\Screenshots 文件夹，按日期分类存放

**现实场景**：用户桌面堆积了大量截图、下载文件，需要定期整理归档。

**展示能力点**：文件系统操作、窗口管理、批量处理

**预期步骤**：
1. launch_app("文件资源管理器")
2. press_key("win+d") → 显示桌面
3. click(桌面空白区域) → 确保焦点
4. press_key("ctrl+a") → 全选桌面文件
5. 识别截图文件（按文件名/扩展名）
6. press_key("ctrl+x") → 剪切
7. navigate_to("D:\Screenshots")
8. press_key("ctrl+v") → 粘贴
9. 按日期重命名文件夹

**录制要点**：展示从"凌乱桌面"到"自动整理"的变化。

---

## 场景七：社交媒体内容发布（营销场景）

**用户指令**：
> 打开浏览器，登录微信公众平台，新建一篇图文消息，标题写"AI工具推荐周报 #3"，正文从记事本里读取我之前写好的内容粘贴进去

**现实场景**：运营人员每天需要跨平台发布内容，AI自动完成登录和发布流程。

**展示能力点**：浏览器登录态管理、多页面切换、剪贴板联动

**预期步骤**：
1. browser_navigate("https://mp.weixin.qq.com")
2. browser_snapshot() → 检查登录状态
3. browser_click("新建图文")
4. browser_type(标题框, "AI工具推荐周报 #3")
5. launch_app("记事本")
6. press_key("ctrl+a") → press_key("ctrl+c") → 全选复制
7. 切换回浏览器
8. browser_click(正文区域)
9. press_key("ctrl+v") → 粘贴内容
10. browser_click("保存")

---

## 场景八：课程作业辅助（教育场景）

**用户指令**：
> 帮我从维基百科找到关于"深度学习"的英文页面，提取前两段内容，用必应翻译成中文，然后把中英文对照保存到记事本

**现实场景**：学生在做研究时需要查找外文资料、翻译、整理笔记。

**展示能力点**：跨站点导航、内容提取、翻译工具使用、格式化保存

**预期步骤**：
1. browser_navigate("https://en.wikipedia.org/wiki/Deep_learning")
2. browser_snapshot() → 提取前两段文本
3. browser_navigate("https://www.bing.com/translator")
4. browser_type(输入框, 提取的英文文本)
5. browser_snapshot() → 获取翻译结果
6. launch_app("记事本")
7. type_text("深度学习 (Deep Learning) - 中英文对照\n\n[英文原文]\n...[中文翻译]\n...")
8. press_key("ctrl+s") → 保存

---

## 场景九：自动化邮件处理（商务场景）

**用户指令**：
> 打开浏览器登录Gmail，找到最新一封来自boss@company.com的邮件，阅读内容后帮我用记事本写一封回复草稿

**现实场景**：商务人士每天处理大量邮件，AI可以辅助阅读和起草回复。

**展示能力点**：邮箱登录态管理、邮件定位与提取、智能回复生成

**预期步骤**：
1. browser_navigate("https://mail.google.com")
2. browser_snapshot() → 确认登录状态
3. browser_type(搜索框, "from:boss@company.com")
4. browser_press_key("Enter")
5. browser_click(第一封邮件)
6. browser_snapshot() → 提取邮件内容
7. launch_app("记事本")
8. type_text(输入框, 生成的回复草稿)
9. press_key("ctrl+s") → 保存

---

## 场景十：记忆系统完整展示

**演示能力**：3层自动记忆系统 — 用户画像、成功模式、失败教训

### 10A — 记忆检索注入

1. 先执行场景一："打开记事本写短文"（系统自动提取：记事本、剪贴板输入、Ctrl+S保存）
2. 再执行："帮我写篇日记保存"
3. **关键对比**：第二次Planner prompt中自动注入了 `[相关记忆] 1. 该用户习惯用记事本编写文档，使用Ctrl+S保存到桌面`

### 10B — 去重合并

1. 连续执行5次"打开浏览器搜索Python项目"
2. 展示数据库：`t_memories` 表中只有 **1条** 活跃记录（其余4条 `is_active=False`）

### 10C — 失败教训自动消解

1. 先触发场景五的失败（文件不存在）
2. DB出现 `failure_lesson`
3. 再次成功完成同类文件操作
4. DB中失败教训自动标记 `is_active=False`（`resolved_count=1`）

### 数据库展示（录制结尾）

```sql
SELECT memory_type, category, is_active, summary FROM t_memories;

success_pattern | task_workflow     | 1 | [记事本] 写短文并Ctrl+S保存到桌面
success_pattern | task_workflow     | 0 | [记事本] 写短文并保存    ← 已被覆盖
failure_lesson  | failure_avoidance | 0 | 无法找到文件路径        ← 已被消解
success_pattern | task_workflow     | 1 | [记事本] 写日记保存到桌面
success_pattern | task_workflow     | 1 | [Chrome] 浏览GitHub提取项目信息
success_pattern | task_workflow     | 1 | [Chrome] 填写注册表单
```

---

## 录制建议

| 场景 | 时长 | 核心卖点 |
|------|------|---------|
| 场景一 | 45s | AI写文章——文字工作者效率提升10倍 |
| 场景二 | 90s | AI做调研——开发者省去手动浏览GitHub |
| 场景四 | 60s | AI填表单——测试工程师告别重复劳动 |
| 场景九 | 60s | AI处理邮件——商务人士的虚拟助理 |
| 场景十 | 90s | AI越用越聪明——记忆系统是核心壁垒 |

**录制总时长**：约 5-6 分钟

### 录制设置

- 分辨率: 1920×1080
- 同时录制: HAJIMI B端界面 + Windows桌面 + 终端(实时日志)
- 终端窗口放在右侧展示 agent 工具调用日志
- DB查询用独立窗口，切换过去展示 `t_memories` 表数据变化
- 用OBS同时录制两个显示器/窗口，后期做画中画

### 叙事线索

1. **冷启动** → 第一次执行任务，展示完整管线
2. **复杂任务** → 多应用协同、浏览器自动化
3. **失败处理** → 优雅降级、重试机制
4. **记忆生效** → 同样任务第二次明显更快、更准
5. **数据证明** → 切到数据库展示记忆系统的实际数据
