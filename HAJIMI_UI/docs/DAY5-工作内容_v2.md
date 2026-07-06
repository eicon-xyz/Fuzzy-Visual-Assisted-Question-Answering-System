# HAJIMI 实训 DAY5 工作内容（v2）

> **日期**：实训第 5 天（对照 [`HAJIMI-六天冲刺计划.md`](HAJIMI-六天冲刺计划.md) Day 5）  
> **角色**：B 端（前端 / 桌面应用）为主；A 端配合联调  
> **文档版本**：v2 · 2026-07-03（补录）

---

## 一、DAY5 目标

| 路线阶段 | 天数 | DAY5 对应里程碑 |
|----------|------|-----------------|
| **集成测试** | 第 5 天 | Happy Path + 异常路径 + 管理面板路径；Bug 清单；性能基准 |
| **B 端实际重点** | 第 5 天 | **全链路联调验收** + **GPU/内网部署文档** + **可移植性优化** |

**DAY5 核心目标**：

1. 按联调清单逐条验证 B↔A 核心流程（health → process → step → inspect）  
2. 校园 GPU / 内网 API 模式文档化并可按 runbook 复现  
3. 汇总 Bug 与性能数据，为 DAY6 清零与演示做准备  

---

## 二、DAY5 任务清单

### 2.1 集成测试 — Happy Path（B↔A）

| # | 用例 | 验证方式 | 状态 |
|---|------|----------|------|
| 1 | 文本提问 → 步骤 + 红框标注 | `python main.py` 手动 | ✅ |
| 2 | health 启动探测 → 状态栏文案 | 启动 B + A | ✅ |
| 3 | 检验模式全量青色框 | 设置 → 立即检测 | ✅ |
| 4 | 分步推进 → 标注更新 | 下一步 / 上一步 | ✅ |
| 5 | `/relocate` 手动重定位 | PrepareStep 弹窗流程 | ✅ |
| 6 | 自动化脚本 | `scripts/verify_integration.py` | ✅ |

### 2.2 集成测试 — 异常路径

| # | 用例 | 说明 | 状态 |
|---|------|------|------|
| 1 | A 端未启动 → Mock 或错误提示 | `HAJIMI_MOCK_FALLBACK` | ✅ |
| 2 | 旧版 A 多开 / 僵尸端口 | `stop_all.bat` + `kill_port` | ✅ |
| 3 | HiDPI 坐标偏移 | `core/overlay_coords.py` | ✅ 2026-06-30 |
| 4 | OmniParser 超时（360s） | health `omniparser_ready` | ✅ |
| 5 | 断网内网模式 | 状态栏「A端不可达」 | ✅ |
| 6 | 红线拦截 | A 端 redline | ⏳ UI 待完整接入 |
| 7 | 指纹不匹配挂起 | SuspensionDialog | ✅ 基线 |
| 8 | 审计队列补传 | C 端 AuditAgent | ⏳ C 端 |

### 2.3 GPU / 内网联调文档

| # | 交付物 | 路径 | 状态 |
|---|--------|------|------|
| 1 | B 端联调清单（group2） | `docs/校园GPU-B端联调清单_v2.md` | ✅ |
| 2 | A 端 GPU 容器详细指南 | `server/docs/A端-GPU容器部署详细指南-group2_v2.md` | ✅ |
| 3 | 远程启服与快速测试 | `docs/校园GPU-远程启服与快速测试.md` | ✅ |
| 4 | B 端 OmniParser GPU API 部署 | `docs/B端-OmniParser-GPU-API部署文档.md` | ✅ |
| 5 | P1 可移植性指南 | `docs/P1-可移植性改动与使用指南.md` | ✅ |
| 6 | RTX 5070 Ti / sm_120 CPU 回退 | `scripts/detect_omni_device.py` | ✅ |

### 2.4 主题与 Native 回归

| # | 任务 | 涉及文件 | 状态 |
|---|------|----------|------|
| 1 | 主题 apply 自动化 | `scripts/verify_theme_apply.py` | ✅ |
| 2 | Web UI 回退验证 | `scripts/verify_web_ui_fallback.bat` | ✅ |
| 3 | 多 variant 切换无 crash | `theme_manager.py` | ✅ |
| 4 | 设置页撑高 / 恢复尺寸 | `main_widget._size_before_settings` | ✅ |

### 2.5 Bug 修复冲刺（DAY5 当日）

| # | 问题 | 修复 | 状态 |
|---|------|------|------|
| 1 | 设置 round-trip 后无法缩宽、圆角丢失 | `window_clip` + geometry anim 去重 | ✅ |
| 2 | 中窗默认宽与 topbar 最小宽不一致 | clamp narrowMin（DAY6 完善） | 🔄 |
| 3 | compact pill mask 动画中间态大弧线 | `_should_use_pill_mask` | ✅ DAY6 |
| 4 | StatusBadge 背景遮挡 HAJIMI | layout + badge 固定宽 | ✅ DAY6 |

---

## 三、DAY5 交付物

| 交付物 | 路径 |
|--------|------|
| DAY5 工作总结 | `docs/DAY5-工作内容_v2.md`（本文档） |
| 联调自动化 | `scripts/verify_integration.py` |
| 主题自动化 | `scripts/verify_theme_apply.py` |
| GPU 联调清单 | `docs/校园GPU-B端联调清单_v2.md` |
| 可移植性说明 | `docs/P1-可移植性改动与使用指南.md` |
| B 端快速启动 | `docs/B端-组员快速启动.md` |
| 集成测试报告（模板） | 本文档 §六 |

---

## 四、DAY5 验收标准

### 4.1 必须通过

1. `python scripts/verify_integration.py` — health + process + step 无 FAIL（inspect 小图可 SKIP）  
2. `python scripts/verify_theme_apply.py` — ok  
3. 本地模式：OmniParser + A 端 → 检验模式桌面出现青色框  
4. 内网模式：填 A 同学 URL → health 200 → process 可用  
5. 真实截图下红框与桌面元素 **人工抽检** 基本对齐（允许 OmniParser 漏检）

### 4.2 性能参考（非硬性，记录即可）

| 指标 | 目标 | 备注 |
|------|------|------|
| `/process`（含 LLM，不含 GPU 冷启） | P95 < 15s | 视 DeepSeek 延迟 |
| GPU inspect | 明显快于 CPU | 校园 A800 |
| 截图 + 单帧 overlay 绘制 | < 200ms | B 端本地 |
| 模式切换动画 | 250ms | 无卡顿 |

---

## 五、集成测试报告模板

```markdown
## HAJIMI 集成测试报告（DAY5）

**测试人**：____  **日期**：____  **环境**：Windows 11 / Python 3.10+

### Happy Path
| # | 用例 | 结果 | 备注 |
|---|------|------|------|
| 1 | health 200 | PASS/FAIL | |
| 2 | 文本 process + 步骤 | PASS/FAIL | |
| 3 | inspect 全量框 | PASS/FAIL | |
| 4 | step 下一步 | PASS/FAIL | |
| 5 | relocate 重定位 | PASS/FAIL | |

### 异常路径
| # | 用例 | 结果 | 备注 |
|---|------|------|------|
| 6 | A 未启动提示 | PASS/FAIL | |
| 7 | 内网不可达 badge | PASS/FAIL | |
| 8 | HiDPI 框位置 | PASS/FAIL | |

### 自动化
- verify_integration.py：____
- verify_theme_apply.py：____

### Bug 清单（P0/P1/P2）
| ID | 描述 | 优先级 | 负责人 | 状态 |
|----|------|--------|--------|------|
| 1 | | P0 | | open |

### 性能记录
- process 耗时：____ s
- inspect 耗时：____ s（GPU/CPU：____）
```

---

## 六、快速命令参考

```powershell
# 全栈本地
scripts\start_all.bat

# 联调自动化
python scripts\verify_integration.py
python scripts\verify_theme_apply.py

# 停止残留进程
scripts\stop_all.bat

# 内网模式：main.py → 设置 → 内网 API → 保存并应用
curl http://<A端IP>:8010/api/demo/health
```

---

## 七、DAY5 工作日志模板（提交实训用）

```markdown
### 日期：____年__月__日（DAY5）

**今日完成**
- verify_integration / verify_theme_apply
- GPU 联调文档 / 可移植性
- 

**集成测试结果**
- Happy Path：__ / __ 通过
- 主要 Bug：

**明日计划（DAY6）**
- Bug 清零 + 演示脚本 + 文档补全
```

---

## 八、DAY6 计划（预览）

> **详见**：[`DAY6-工作内容_v2.md`](DAY6-工作内容_v2.md)

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | P0/P1 Bug 清零 | 窗口蒙版、顶栏遮挡等 |
| P0 | DAY1–6 文档补全 | 实训提交 |
| P1 | 演示脚本（安装微信场景） | 逐步操作清单 |
| P2 | PyInstaller 打包验证 | 可选 |

---

## 九、参考文档

- DAY4：[`DAY4-工作内容_v2.md`](DAY4-工作内容_v2.md)
- GPU 联调：[`校园GPU-B端联调清单_v2.md`](校园GPU-B端联调清单_v2.md)
- B 端改动：[`CHANGELOG-B端_v2.md`](CHANGELOG-B端_v2.md)
- 六天冲刺：[`HAJIMI-六天冲刺计划.md`](HAJIMI-六天冲刺计划.md)
