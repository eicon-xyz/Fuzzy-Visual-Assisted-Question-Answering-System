# SeeClick / YOLO 视觉检测方案评估报告

> **评估日期**：2026-07-02  
> **评估范围**：`server/services/omniparser_client.py` 当前使用的 OmniParser V2 备选/补充方案  
> **结论摘要**：在 Demo 阶段**不建议**引入 SeeClick 或 YOLO 替代 OmniParser；两者可作为未来 P2「模糊描述 / 非标准控件」级联补漏的候选，但当前 ROI 低于 GroundingDINO。

---

## 1. 评估目标

回答两个问题：

1. 是否应引入 **SeeClick** 作为当前 OmniParser V2 的替代或主检测器？
2. 是否应引入 **YOLO + UI 微调** 作为本地极速检测方案？

评估维度：检测能力、输出格式兼容性、延迟/资源消耗、数据与训练成本、与现有架构的契合度。

---

## 2. 当前基线：OmniParser V2

- **能力**：端到端输出 UI 元素 bbox、类型、OCR 文本，并生成 SoM 标注图。
- **输入**：PNG/JPG 截图。
- **输出**：`parsed_content_list` → `List[UIElement]`，可直接被 `server/services/perception/serializer.py` 消费。
- **延迟**：本地 CPU 推理约 5–30s/帧（依赖截图分辨率与硬件），GPU 可降至 <1s/帧。
- **局限**：
  - 对**非标准控件**（如自定义图标、模糊描述「圆圆的齿轮」）召回率低。
  - 需要本地部署 `omniparserserver :9800` 或 Replicate 在线调用。

> 当前架构已围绕 OmniParser 输出格式稳定运行，任何替换方案必须保持 `UIElement` schema 兼容。

---

## 3. SeeClick 评估

### 3.1 模型特点

- **来源**：论文 *SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents*（arXiv:2401.10935，2024.01）。
- **定位**：基于视觉-语言模型（VLM）的 **GUI grounding** 预训练模型。
- **强项**：根据自然语言指令在屏幕截图中定位目标元素，支持 mobile / desktop / web 跨平台。
- **弱项**：
  - **擅长单步 grounding，不擅长全量 SoM**：论文和官方仓库主要面向「给定指令 → 预测一个坐标」的任务，而非一次性输出全屏所有可交互元素的列表。
  - **无法直接替代 OmniParser**：缺少元素类型分类、OCR 文本、全量 bbox 列表等 HAJIMI 必需字段。
  - **需要大量显存**：基于 VLM 的推理通常 ≥ 12–16GB GPU 显存，高于 OmniParser 的 YOLO+Florence 组合。

### 3.2 与 HAJIMI 的契合度

| 维度 | 契合度 | 说明 |
|------|--------|------|
| 输出格式 | 低 | 输出是单点坐标或边界框，需额外包装为 `UIElement` 列表 |
| 全量检测 | 低 | 不适合作为第一级检测器，只适合「找不到元素时精确定位」 |
| 模糊描述 | 高 | 对「圆圆的齿轮」「设置按钮」等开放词汇理解能力强 |
| 资源消耗 | 中低 | 显存与延迟高于 OmniParser，不适合作为默认路径 |
| 集成成本 | 中 | 需新增模型加载、prompt 构造、结果转换逻辑 |

### 3.3 结论

**SeeClick 不适合替换 OmniParser**，但可作为未来 **P2 级联补漏** 的候选：当 OmniParser 未召回目标元素且用户用自然语言描述目标时，触发 SeeClick 做一次「指令 → 单框」的 grounding。

---

## 4. YOLO + UI 微调评估

### 4.1 方案形态

- **YOLOv8 / YOLO11**：通用目标检测 backbone，速度极快（RTX 3060 上 1080p 截图 ~200ms）。
- **UI 微调**：在 GUI 数据集（如 GUI Odyssey、Mind2Web 截图、或 OmniParser 训练数据）上微调，输出 `[button, input, icon, menu, checkbox, dropdown, text]` 等类别。

### 4.2 优势与劣势

| 维度 | 优势 | 劣势 |
|------|------|------|
| 速度 | 本地 GPU 推理极快，适合实时预览 | 纯 YOLO 无 OCR 文本，需额外接 PaddleOCR |
| 全量检测 | 可一次性输出全屏 proposals | 需大量标注数据训练，通用性受限 |
| 资源 | 比 VLM 轻量 | 需要训练自己的 checkpoint |
| 文本元素 | 目标检测对纯文字按钮召回差 | 必须做 OCR 后融合 |

### 4.3 与 HAJIMI 的契合度

- 当前 OmniParser 内部本身就使用了 YOLO（微软 OmniParser V2 使用 YOLOv8 + Florence-2 做检测与描述）。
- 单独使用 YOLO + UI 微调相当于**把 OmniParser 中的检测模块拆出来**，但会丢失 Florence-2 的图标描述能力和 OCR 融合逻辑。
- 若只是为了**降低延迟**，优先优化 OmniParser 的推理参数（分辨率、NMS 阈值、批量）更划算。

### 4.4 结论

**YOLO + UI 微调在 Demo 阶段不具性价比**。除非后续出现明确的延迟瓶颈且 OmniParser 无法优化，否则不建议自行训练 YOLO UI 检测器。

---

## 5. 与 P2 GroundingDINO 级联补漏的关系

`参考方案优先级与实施路线图.md` 将 **GroundingDINO 级联补漏** 列为 P2。本评估认为：

- **GroundingDINO 比 SeeClick 更适合当前架构**：
  - 同样支持开放词汇定位（「齿轮」「设置按钮」）。
  - 输出的是边界框，无需像 SeeClick 那样处理 VLM 的文本输出。
  - 与 PaddleOCR 组合可快速补全 OmniParser 漏检的文本/非标准控件。
- **SeeClick 可作为 GroundingDINO 的语义增强备选**：若 GroundingDINO 对复杂自然语言描述理解不足，再考虑引入 VLM-based grounding（SeeClick 或 Qwen-VL）。

---

## 6. 综合建议

| 方案 | 建议 | 优先级 | 下一步动作 |
|------|------|--------|-----------|
| **SeeClick** | 不替换 OmniParser；未来作为 GroundingDINO 的语义增强备选 | P2/P3 | 保持关注，暂不入代码 |
| **YOLO + UI 微调** | 不单独实施；OmniParser 内部已含 YOLO | P3 以后 | 若延迟成为瓶颈，先优化 OmniParser 参数 |
| **GroundingDINO 级联补漏** | 继续按 P2 推进 | P2 | 见 `参考方案优先级与实施路线图.md` §P2 |

### 对检测器路线图的更新

| 方案 | 状态 | 说明 |
|------|------|------|
| **Replicate OmniParser V2** | ✅ 可选 | 全量 SoM，2–5s，需 `REPLICATE_API_TOKEN` |
| **内网 OmniParser** | ✅ 当前 | `OMNIPARSER_URL=http://127.0.0.1:9800`，CPU 5–30s |
| **SeeClick** | 🔬 评估完成 | 擅长单步 grounding，不擅长全量 SoM；**暂不入主链路** |
| **YOLO + UI 微调** | 🔬 评估完成 | 本地极速但需训练；OmniParser 已覆盖，**暂不单独实施** |
| **GroundingDINO 级联** | 🔬 待实施 | 首选开放词汇补漏方案，P2 推进 |
| **Rasa NLU** | ❌ 不适用 | 仅文本意图，无 bbox |

---

## 7. 风险与备选

- **风险**：如果 OmniParser 推理延迟或显存占用持续不可接受，YOLO + UI 微调可能被重新提上日程。
- **备选**：可考虑用 **OmniParser 的轻量模式**（如降低输入分辨率、只检测图标不接 Florence-2 描述）作为快速路径，而非自训练 YOLO。

---

## 8. 附录：参考资源

- SeeClick 论文：arXiv:2401.10935，https://github.com/njucckevin/SeeClick
- GUI Element Detection Using SOTA YOLO Deep Learning Models：arXiv:2408.03507
- 项目内参考文档：`项目文档/参考方案优先级与实施路线图.md`、`项目文档/设计文档V2.md`
