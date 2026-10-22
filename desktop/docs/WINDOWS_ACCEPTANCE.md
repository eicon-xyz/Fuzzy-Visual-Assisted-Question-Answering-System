# HAJIMI Desktop — Windows 实测验收 checklist（M4）

> 目的：Electron 新端在真实 Windows 上与 PyQt 旧端功能对齐确认。**全部通过后才执行“切换启动链”commit**（根 .bat 默认指 Electron）。任何一项失败：记录现象 + `server_A/server/` 日志 + 提交 issue 到 front 分支迭代，不切换。

## 前置
- [ ] Node.js 20+ 已装（`node -v`）；`corepack enable pnpm` 成功或 pnpm 已在 PATH
- [ ] 仓库根双击 `安装桌面版.bat`：pnpm install + build 全绿（产物 `desktop/out/main/main.mjs`）

## 一、核心执行链
- [ ] `启动桌面版.bat`（或 desktop 内 `pnpm dev`）：主窗出现（无边框、暗色、托盘有图标）
- [ ] 首次提交弹「L5 知情确认」；勾选不再提示 → 同意
- [ ] 输入「打开记事本」→ 执行：Sidecar 未启动时自动拉起（状态条从"拉起中"→"就绪"），步骤时间线逐条出现，记事本真的打开
- [ ] 步骤行显示 action_summary；done 步骤有「证据」行（P0 evidence）
- [ ] 执行中点「停止」→ 任务终止（task_cancelled，时间线收起为已取消）
- [ ] 含敏感词指令（如「帮我自动点击抢购」）→ 指令被第一层改写（聊天区出现"指令已按 L5 规范改写"提示），改写后仍能提交
- [ ] 「帮我扫描硬盘里所有的照片」→ 隐私红线原样提交 → Sidecar 第二层拦截（task_failed 带 REDLINE）
- [ ] 关掉 Sidecar 进程再提交 → 自动重新拉起并执行成功
- [ ] 网页类任务（「用浏览器打开 baidu.com」）→ browser_* 工具事件在时间线可折叠查看

## 二、设置与账号
- [ ] 设置页（标题栏 ⚙）：填 DEEPSEEK key → 保存 → 提示已同步 → `server_A/server/.env` 内 LLM_API_KEY 更新且**旧空字段未被清空**
- [ ] 保存后 Sidecar 自动重启（进程 pid 变化），健康状态恢复"就绪"
- [ ] 清空 api_key 再保存 → .env 原 key 保留（空值不覆盖）
- [ ] 登录：新装（无 auth_session.json）启动弹登录框；错误密码→显示 Sidecar 返回的 message；admin/demo123 在 Sidecar 停机时可离线进入（local-demo 会话）
- [ ] `%LOCALAPPDATA%\HAJIMI\user_settings.json`：Electron 修改后，PyQt 旧端读取不报错（双端同文件兼容）
- [ ] 反向：PyQt 改过的设置，Electron 能读到（llm/consent 字段）

## 三、桌面体验
- [ ] 标题栏 ▁ 切紧凑条：窗口缩为一行；✦ 点回常规模式
- [ ] 拖动/缩放后退出重开：位置尺寸恢复；拔掉副屏后启动不漂移（居中重开）
- [ ] 托盘：双击唤起；右键菜单 显示/隐藏、退出
- [ ] 关主窗 → 隐藏到托盘（进程不死）；托盘退出 → Sidecar 一并清理（`HAJIMI_STOP_SERVICES_ON_EXIT=1` 时 8011 端口释放）
- [ ] 设置开「全局停止快捷键」→ 重启后任意界面 Ctrl+Alt+J 停止任务（可选功能，非 PyQt 回归项）
- [ ] 主题切 variant_luxury → 黑金底生效
- [ ] step_done 步骤 TTS 播报（语音开关控制；系统无中文语音包时静默不报错）

## 四、回归门禁（切换前 CI）
- [ ] `python HAJIMI_UI/scripts/verify_all.py --require-l5`：全 PASS 且 `check_desktop_build PASS`
- [ ] HAJIMI_UI `pytest tests -q`：35 passed / 6 预存失败不变
- [ ] desktop `pnpm test`：全绿（normalize parity golden 27 条在内）
- [ ] `python HAJIMI_UI/scripts/dev/check_bat_parens.py`：flagged 0

## 五、切换 commit 内容（实测全过后才做）
- 根 `启动全栈.bat` 改为起 Sidecar + Electron（PyQt 路径保留为 `启动全栈_legacy_pyqt.bat` 或删除，届时拍板）
- `安装全栈.bat` 增补 desktop 段
- AGENTS.md/CLAUDE.md 目录结构描述同步 Electron
- session-memory 更新「B 端已切 Electron」
