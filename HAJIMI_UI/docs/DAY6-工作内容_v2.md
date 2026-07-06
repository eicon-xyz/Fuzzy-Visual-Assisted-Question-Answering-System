# HAJIMI 实训 DAY6 工作内容（v2）

> **日期**：实训第 6 天（对照 [`HAJIMI-六天冲刺计划.md`](HAJIMI-六天冲刺计划.md) Day 6）  
> **角色**：B 端（前端 / 桌面应用）为主；全员验收  
> **文档版本**：v2 · 2026-07-04（补录）

---

## 一、DAY6 目标

| 路线阶段 | 天数 | DAY6 对应里程碑 |
|----------|------|-----------------|
| **收尾** | 第 6 天 | P0/P1 Bug 清零；文档完善；演示准备；全员验收 |
| **B 端实际重点** | 第 6 天 | **窗口蒙版/顶栏回归修复** + **DAY1–6 文档补全** + **演示就绪检查** |

**DAY6 核心目标**：

1. 修复影响演示的 P0 UI 问题（小窗圆角、顶栏遮挡、模式切换蒙版）  
2. 补全实训 DAY1–6 工作文档，形成可提交材料  
3. 按六天计划验收清单走通 Demo 主路径  

---

## 二、DAY6 任务清单

### 2.1 P0/P1 Bug 清零（B 端 UI）

| # | 问题 | 修复 | 涉及文件 | 状态 |
|---|------|------|----------|------|
| 1 | compact 切换动画中间态 pill mask 大弧线裁剪 | `_should_use_pill_mask` 守卫 | `ui/main_widget.py` | ✅ |
| 2 | 中窗 HAJIMI 被 StatusBadge 背景遮挡 | topbar layout + badge 固定宽 + clamp 宽 | `topbar_layout.py`, `medium_panel.py` | ✅ |
| 3 | 小窗底边圆角发平 | compact 禁用 drop shadow | `ui/native/shell_renderer.py` | ✅ |
| 4 | 抽屉遮罩模式切换残留 | `force_dismiss_drawer` | `medium_panel.py` | ✅ |
| 5 | BadgeBreath  idle 仍挂 opacity effect | 按需挂载/移除 | `status_badge_fx.py` | ✅ |
| 6 | 设置 round-trip 圆角/缩放宽 | geometry settled + window_clip | `main_widget.py` | ✅ |
| 7 | `_refresh_status_badge` 初始化顺序 | defer + hasattr | `medium_panel.py` | ✅ |

### 2.2 UI 细节打磨

| # | 任务 | 状态 |
|---|------|------|
| 1 | 中窗默认 400×520 + 10px 圆角 mask | ✅ |
| 2 | 小窗 320×52 pill，无 shadow | ✅ |
| 3 | 顶栏 narrowMin 动态计算 | ✅ |
| 4 | 窄窗隐藏 `· 操作指引` | ✅ |
| 5 | 壳层空白区可拖窗 | ✅ |
| 6 | 模式切换 250ms 动画 | ✅ |

### 2.3 文档完善

| # | 交付物 | 路径 | 状态 |
|---|--------|------|------|
| 1 | DAY1 工作总结 | `docs/DAY1-工作内容.md` | ✅ |
| 2 | DAY2 工作总结 | `docs/DAY2-工作内容.md` | ✅ 已有 |
| 3 | DAY3 工作总结 v2 | `docs/DAY3-工作内容_v2.md` | ✅ 已有 |
| 4 | DAY4 工作总结 v2 | `docs/DAY4-工作内容_v2.md` | ✅ |
| 5 | DAY5 工作总结 v2 | `docs/DAY5-工作内容_v2.md` | ✅ |
| 6 | DAY6 工作总结 v2 | `docs/DAY6-工作内容_v2.md` | ✅ 本文档 |
| 7 | 设计 spec 更新（Round 13+） | `docs/design-spec.md` | ✅ |
| 8 | 项目结构说明 | `docs/项目结构.md` | ✅ |

### 2.4 演示准备

| # | 任务 | 状态 |
|---|------|------|
| 1 | Demo 主路径脚本（见 §五） | ✅ 本文档 |
| 2 | 预置演示用例：软件安装 L3 | ⏳ 依赖 A 端步骤质量 |
| 3 | 预置演示用例：文档保存 L2 | ⏳ |
| 4 | 预置演示用例：红线拦截 | ⏳ A 端 redline |
| 5 | PyInstaller 打包 exe | ⏳ 可选 |
| 6 | 管理面板 + 审计演示 | ⏳ C 端 |

### 2.5 全员最终验收（六天计划 §Day 6）

| # | 验收项 | B 端 | 状态 |
|---|--------|------|------|
| 1 | 文本「怎么安装微信？」→ 标注 + 步骤 | ✅ | 需 A 端 + 网络 |
| 2 | 语音提问 | ⏳ | C 未联调 |
| 3 | 红线「帮我抢票」 | ⏳ | A redline |
| 4 | 指纹不匹配挂起 | ✅ | SuspensionDialog |
| 5 | 任务完成审计出现在管理面板 | ⏳ | C + A |
| 6 | 管理面板登录 / Dashboard | ⏳ | C |
| 7 | 挂件拖拽/折叠/resize/置顶 | ✅ | Native 双态 |
| 8 | 断网审计补传 | ⏳ | C |

---

## 三、DAY6 交付物

| 交付物 | 路径 |
|--------|------|
| 完整 DAY1–6 文档集 | `docs/DAY1-工作内容.md` … `DAY6-工作内容_v2.md` |
| 可演示 Native Demo | `python main.py` + A 端 |
| 自动化验证 | `verify_integration.py`, `verify_theme_apply.py` |
| 演示操作脚本 | 本文档 §五 |
| 遗留问题清单 | 本文档 §七 |

---

## 四、DAY6 验收标准

### 4.1 B 端 Demo 必须通过

1. 启动 A + B → health 正常 → 输入问题 → 步骤列表 + 屏幕红框  
2. 中窗 ↔ 小窗切换无大弧线、无顶栏遮挡  
3. 小窗 pill 上下圆角完整，底边不发平  
4. 设置页保存主题 / 部署模式后重启仍生效  
5. `python scripts/verify_integration.py` + `verify_theme_apply.py` 通过  

### 4.2 文档必须通过

6. DAY1–6 文档齐全，交叉引用正确  
7. 实训报告可引用：目标 / 任务 / 交付物 / 验收 / 工作日志模板  

---

## 五、Demo 演示脚本（B 端主路径）

> 演示前：`scripts\start_all.bat` 或 内网模式已配置 A 端 URL。

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 启动 `python main.py` | 中窗 400×520（或记忆尺寸），顶栏 HAJIMI 可见 |
| 2 | 观察状态栏 | 「准备就绪」或连接状态（非遮挡标题） |
| 3 | 输入「怎么安装微信」并发送 | 进入 processing，badge 呼吸灯 |
| 4 | 等待 A 返回 | 自动保持/切换中窗，步骤列表出现 |
| 5 | 观察桌面 | 红框/箭头标注当前步骤 |
| 6 | 点击「下一步」 | 步骤高亮更新，标注移动 |
| 7 | 设置 → 立即检测当前屏幕 | 全屏青色 ~N 检验框 |
| 8 | 导航 → 系统设置 | 切换部署模式 / 主题 → 保存并应用 |
| 9 | 任务完成或手动切小窗 | 320×52 胶囊，输入可用 |
| 10 | 小窗输入后 Enter | 展开中窗继续对话 |

**备选**：A 端不可达时展示 Mock 路径（`HAJIMI_MOCK_FALLBACK=1`）— 标注为降级演示。

---

## 六、DAY1–6 文档索引

| 天数 | 文档 | 核心主题 |
|------|------|----------|
| DAY1 | [`DAY1-工作内容.md`](DAY1-工作内容.md) | 环境骨架、Mock API、截图、OmniParser |
| DAY2 | [`DAY2-工作内容.md`](DAY2-工作内容.md) | B↔A 契约、最小联调闭环 |
| DAY3 | [`DAY3-工作内容_v2.md`](DAY3-工作内容_v2.md) | 系统设置、GPU auto、水晶玻璃 |
| DAY4 | [`DAY4-工作内容_v2.md`](DAY4-工作内容_v2.md) | 主题体系、双态窗口、轻奢 |
| DAY5 | [`DAY5-工作内容_v2.md`](DAY5-工作内容_v2.md) | 集成测试、GPU 文档、可移植性 |
| DAY6 | [`DAY6-工作内容_v2.md`](DAY6-工作内容_v2.md) | Bug 清零、文档、演示（本文档） |

---

## 七、遗留问题与下次迭代

| 优先级 | 项 | 说明 |
|--------|-----|------|
| P1 | C 端 ASR/TTS 与 B GUI 联调 | `b-c-api-contract.md` |
| P1 | `/clarify` 低置信度 UI | A 端已有端点 |
| P1 | 红线检测 UI 拦截 | A 端 redline_service |
| P2 | Web 管理面板 5 页真实数据 | C 端 |
| P2 | PyInstaller 单文件 exe | 含 Vosk/OmniParser 路径 |
| P2 | L2 快路径 < 3s 验收 | A 端离线规则 |
| P3 | macOS 透明窗口兼容 | 已知 PyQt 限制 |

---

## 八、项目复盘模板（DAY6 17:00）

```markdown
## HAJIMI 六天冲刺复盘

### 完成度（计划 vs 实际）
- A 端：____
- B 端：Native UI + B↔A 闭环 ✅；C 联调 ⏳
- C 端：____

### 亮点
- 真实 OmniParser 检测 + 检验模式
- Native 主题体系 + 双态窗口
- GPU 内网部署 runbook 完整

### 遗留 P0/P1
- 

### 下次迭代建议（优先级排序）
1. 
2. 
3. 
```

---

## 九、快速命令参考

```powershell
# 演示标准启动
scripts\start_all.bat
python main.py

# 验收脚本
python scripts\verify_integration.py
python scripts\verify_theme_apply.py

# 设计对照
python -m ui.web_preview
python -m ui.style_preview_demo
```

---

## 十、参考文档

- 六天冲刺验收清单：[`HAJIMI-六天冲刺计划.md`](HAJIMI-六天冲刺计划.md) §验收标准
- 设计 spec：[`design-spec.md`](design-spec.md)
- B 端改动全记录：[`CHANGELOG-B端_v2.md`](CHANGELOG-B端_v2.md)
- B 端快速启动：[`B端-组员快速启动.md`](B端-组员快速启动.md)
