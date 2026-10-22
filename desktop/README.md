# HAJIMI Desktop（Electron B 端）

HAJIMI 桌面助手的新版 B 端：Electron + Vite + Vue 3 + TypeScript + Pinia。
对接唯一后端 **L5 Sidecar（`server_A/`，`http://127.0.0.1:8011`）**；本目录不含任何后端逻辑。

> 迁移期与 PyQt5 旧端（`../HAJIMI_UI`）**并存**：旧端零改动、恒为回归门禁；Windows 实测验收后再切换根目录启动链。

## 架构约定（重构计划 §一）

- **渲染层零网络权限**：对 Sidecar 的 HTTP/SSE 全部收敛在主进程；渲染层只经 `preload` 的 contextBridge 白名单（`types/ipc.d.ts` 为契约类型单一来源）。
- `electron/` = 主进程/preload 接线（可 import electron）；
- `core/` = 主进程纯逻辑（**禁止 import electron**，vitest 直接测；红线归一化/SSE 解析/envSync 等 M1/M2 陆续落此）；
- `src/` = Vue 渲染层。
- 安全：`contextIsolation: true`、`nodeIntegration: false`、`sandbox: true`、CSP 收紧（index.html）。

## 开发

```bash
pnpm install          # 前置：Node.js 20+ 与 pnpm（corepack enable pnpm）
pnpm dev              # electron-vite dev（HMR）
pnpm build            # 产物：out/{main,preload,renderer}
pnpm test             # vitest（core/ 纯逻辑 + golden parity）
pnpm typecheck        # vue-tsc + tsc
pnpm run dist:win     # Windows：electron-builder portable+nsis → release/
```

Windows 一键：仓根 `安装桌面版.bat`（install+build）→ `启动桌面版.bat`。
验收：`python HAJIMI_UI/scripts/verify_all.py` 会检查 `out/main/main.mjs`（`--require-desktop` 强制）。
Linux/无显示环境可完成 build/vitest 门禁，GUI 手测仅 Windows。

## 与旧 PyQt 端共存

- `%LOCALAPPDATA%\HAJIMI\user_settings.json`：**同文件同 schema**（M2 起）；请勿同时运行两端。
- `server_A/server/.env`：模型 key 唯一存放处；本端 envSync 保持「空值不覆盖」语义。
- X-Demo-Key 等环境变量口径与 `../HAJIMI_UI/config.py` 一致（L5_API_URL / HAJIMI_DEMO_KEY 等）。
