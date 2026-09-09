# HAJIMI 模糊视觉辅助问答系统（32组）

## 项目概览

HAJIMI 是一款 AI 驱动的桌面自动化助手，当前**仅保留 L5 自动执行模式**：
用户用自然语言输入指令 → B 端（PyQt5 桌面应用）红线归一化 + 知情确认 → L5 Sidecar（`server_A`，FastAPI，`127.0.0.1:8011`）LLM 规划并经 Windows UIA 控件绑定 / Playwright DOM **自动执行**点击、输入、启动应用等操作 → SSE 实时回传步骤进度。

```
B端 (HAJIMI_UI) ──HTTP + SSE──▶ L5 Sidecar (:8011) ──▶ UIA / Playwright 自动执行
C端语音 (client/) 与 Web 管理面板 (web-admin/) 同样连接 :8011
```

> L4 指引模式（OmniParser 视觉标注、A 端 :8010、GPU 隧道、内网联调、Mock 演示）已于 2026-09 整体移除；运行环境唯一后端为 `server_A` Sidecar :8011。

## 快速开始（Windows）

1. 双击 `安装全栈.bat`（创建 2 个 venv：`HAJIMI_UI/.venv` + `server_A/server/.venv`）
2. 在 `server_A/server/.env` 填入模型 key（`DEEPSEEK_API_KEY` / `LLM_*`）
3. 双击 `启动全栈.bat`（自动拉起 L5 Sidecar :8011 + B 端两个窗口）
4. 在 B 端「操作指引」输入指令 → 确认 L5 知情提示 → 观察「步骤列表」时间线自动执行（快捷键 `H` 批准 / `P` 暂停 / `J` 停止）
5. 验收：`验收.bat`；停止：`stop_all.bat`

详见 `启动指南.md`、`部署文档.md`、`用户手册.md`、`api-reference.md`、`项目结构速查.md`。

## 技术栈

1. 多模态视觉问答: CLIP、BLIP/ BLIP-2<br>2. 机器视觉处理: OpenCV、图像增强与目标区域处理<br>3. 语音交互: 语音识别ASR、语音合成TTS<br>4. 深度学习开发: PyTorch、Transformers、NumPy、pandas<br>5. 后端服务: FastAPI / Flask, RESTful API<br>6. 前端展示: Vue / Streamlit, 图像上传与问答交互
