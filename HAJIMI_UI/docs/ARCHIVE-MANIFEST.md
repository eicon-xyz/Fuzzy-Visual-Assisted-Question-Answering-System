# 归档与忽略清单

> **日期**：2026-07-06  
> **策略**：**不物理删除**任何文件；本文档仅记录「建议归档 / 打包忽略 / 勿作参考」项。  
> **执行状态**：截至本文档创建时，**未执行** `git mv` 至 `_archive/`；所有路径仍保持原位。

---

## 1. 原则

| 原则 | 说明 |
|------|------|
| 不删除 | demo、重复 test、垃圾文件均保留在仓库或本地，仅标记 |
| 先文档后移动 | 若日后归档，使用 `git mv` 至 `_archive/`，并在本节追加「已移动」记录 |
| 生产优先 | 新 AI 以 [`FILE-MAP.md`](FILE-MAP.md) 中 `[PRODUCTION]` 为准 |
| 历史文档不改 | DAY1–6 日志不 retro-edit；新内容写入 DAY7+ |

---

## 2. 建议归档（`[LEGACY]` → 未来 `_archive/`）

以下路径**当前仍在原位置**；确认后可整体移至 `_archive/` 对应子目录。

| 原路径 | 建议目标 | 原因 | 生产替代 |
|--------|----------|------|----------|
| `ui/demo/maodiao/` | `_archive/demo-maodiao/` | 橘猫 UI 原型，与生产重复 | `ui/native/orange_cat/` |
| `ui/demo/luxury_icons.py` | `_archive/demo-luxury/` | Luxury 原型片段 | `ui/native/luxury/` |
| `ui/demo/luxury_title.py` | 同上 | 同上 | 同上 |
| `ui/demo/luxury_paint.py` | 同上 | 同上 | 同上 |
| `docs/test_ui.py` | `_archive/docs-legacy-tests/` | 早期手测，非 pytest | `scripts/verify_integration.py` |
| `docs/test_main.py` | 同上 | 同上 | 同上 |
| `docs/test_dynamic_overlay.py` | 同上 | 同上 | 同上 |
| `docs/test_parse_local.py` | 同上 | 与根目录重复 | `test_parse_local.py`（根） |
| `docs/api-contract-demo.yaml` | `_archive/contracts/` | OpenAPI v1 | `docs/api-contract-demo_v2.yaml` |

**未列入移动（仍有用）**：

- `ui/style_preview_demo.py` — `[DEMO]` 主题设计对照，README 仍引用
- `ui/web/` — Web 回退路径（`HAJIMI_NATIVE_UI=0`）仍可用
- `test_parse_local.py`（根）— `[DIAGNOSE]` GPU 隧道探测

---

## 3. 打包时忽略（`[IGNORE]`）

**不要**复制到根项目交付包：

| 路径 | 类型 |
|------|------|
| `.venv/` | B 端虚拟环境 |
| `server/.venv/` | A 端虚拟环境 |
| `**/__pycache__/` | Python 缓存 |
| `.pytest_cache/` | pytest 缓存 |
| `server/.env` | 密钥（保留 `server/.env.example`） |
| `docs/校园gpu使用.md` | 含 SSH 密码等（.gitignore） |
| `OmniParser.zip` | 与 `OmniParser/` 目录重复 |
| `Royal TSX.app` | macOS 无关应用 |
| `.DS_Store`, `.background`, `.fseventsd` | macOS 元数据 |
| `新建 文本文档.txt` | 临时文件 |
| `Applications/`（若存在） | 非项目目录 |

**用户机器本地（不在仓库内）**：

- `%LOCALAPPDATA%\HAJIMI\user_settings.json`

---

## 4. 重复 / 易混淆文档

| 文档 | 标记 | 说明 |
|------|------|------|
| `docs/校园GPU-B端联调清单_v2.md` | **主读** | GPU B 端集成首选 |
| `docs/GPU-API远程接入手册.md` | 补充 | 与上重叠，按需查 |
| `docs/GPU OmniParser API — SSH 本地端口转发接入手册（最终版）.md` | 补充 | SSH 隧道细节 |
| `docs/OmniParser GPU API 本地开发接入指南（SSH 隧道版最终最终版）.md` | 补充 | 同上，更长版 |
| `server/README.md` vs `server/README_v2.md` | 查 CHANGELOG | 以 `server/docs/CHANGELOG-A端_v2.md` 为准 |

---

## 5. 已删除项（历史记录，无法归档）

| 项 | 说明 |
|----|------|
| `server2/` | 已移除，统一用 `server/` |
| `ui/native/themes/variant_b/`、`variant_c/` | DAY7 删除；代码内 `migrate_appearance_settings` 兼容旧 ID |

---

## 6. 变更记录

| 日期 | 操作 | 说明 |
|------|------|------|
| 2026-07-06 | 创建本文档 | 仅文档标记，**零文件移动、零删除** |
| — | （待定） | 若执行 `_archive/` 迁移，在此追加 git mv 列表 |

### 迁移模板（日后使用）

```text
# 示例（未执行）：
git mv ui/demo/maodiao _archive/demo-maodiao
# 然后在「变更记录」追加一行
```

---

## 7. 相关文档

- 文件分级：[`FILE-MAP.md`](FILE-MAP.md)
- 根 AI 索引：[`HANDOFF.md`](../HANDOFF.md)
- 详细手册：[`AI-操作指南.md`](AI-操作指南.md)
