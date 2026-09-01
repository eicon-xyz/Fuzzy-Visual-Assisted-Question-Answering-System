"""
HAJIMI Demo API Pydantic 模型
严格对应 docs/api-contract-demo.md 中的数据定义
"""
from typing import Optional, List, Union
from pydantic import BaseModel, Field


# ────────────────────────── 基础模型 ──────────────────────────


class ChatTurn(BaseModel):
    """多轮对话上下文中的单轮记录"""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class Intent(BaseModel):
    """用户意图"""

    category: str = Field(
        ...,
        pattern="^(operation_guide|element_cognition|error_diagnosis|"
        "ui_navigation|content_cognition|file_management|"
        "proactive_alert|tutorial_generation|emotion_comfort)$",
    )
    summary: str
    reference_type: Optional[str] = Field(
        None, pattern="^(explicit|visual|deictic|fuzzy|context)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_clarification: bool


class UIElement(BaseModel):
    """截图中识别到的 UI 元素"""

    element_id: str = Field(..., description="SoM 全局唯一编号，如 ~1")
    bbox: List[int] = Field(..., min_length=4, max_length=4)
    element_type: str = Field(
        ...,
        pattern="^(button|input|icon|menu|checkbox|dropdown|text|other)$",
    )
    text: Optional[str] = ""
    confidence: float = Field(..., ge=0.0, le=1.0)
    center: Optional[List[int]] = Field(None, min_length=2, max_length=2)


class Annotation(BaseModel):
    """屏幕标注信息"""

    type: str = Field(
        ...,
        pattern="^(arrow_highlight|highlight_only|arrow_only|label_only|none)$",
    )
    arrow_from: Optional[List[int]] = Field(None, min_length=2, max_length=2)
    arrow_to: Optional[List[int]] = Field(None, min_length=2, max_length=2)
    highlight_bbox: Optional[List[int]] = Field(None, min_length=4, max_length=4)
    label_position: Optional[List[int]] = Field(None, min_length=2, max_length=2)
    label_text: Optional[str] = None


class PlanningStep(BaseModel):
    """L5 Planner 输出 — 仅意图，无坐标"""

    step_index: int = Field(..., ge=1)
    instruction: str


class ExecutedStep(BaseModel):
    """L5 Execution Agent 运行时步骤记录"""

    step_index: int = Field(..., ge=1)
    instruction: str
    action: Optional[str] = None
    target_element_id: Optional[str] = None
    params: Optional[dict] = None
    action_summary: Optional[str] = None
    status: str = Field("pending", pattern="^(pending|executing|done|failed)$")


class Step(BaseModel):
    """操作步骤"""

    step_index: int = Field(..., ge=1)
    action: str
    description: str
    target: Optional[str] = Field(
        None,
        description="Planner 生成的 UI 目标简短名称，供 Locator 使用",
    )
    target_element_id: Optional[str] = None
    status: str = Field(
        ...,
        pattern="^(pending|active|done|skipped|failed)$",
    )
    annotation: Optional[Annotation] = None
    interaction: Optional[str] = Field(
        None,
        description='步骤交互类型："keyboard" 纯快捷键，"screen" 需屏幕定位',
    )
    locate_deferred: Optional[bool] = Field(
        None,
        description="True 时本步需用户先手动完成，下一步 advance 再 Vision 定位",
    )
    prepare_hint: Optional[str] = Field(
        None,
        description="locate_deferred 时展示给用户的操作提示",
    )


class Blueprint(BaseModel):
    """任务蓝图"""

    name: str
    total_steps: int = Field(..., ge=1)
    current_step: int = Field(..., ge=1)
    state: str = Field(
        ...,
        pattern="^(generated|pending_confirm|executing|suspended|"
        "rolling_back|completed|terminated)$",
    )


class ErrorDetail(BaseModel):
    """统一错误响应"""

    code: str
    message: str
    details: Optional[dict] = {}


class ErrorResponse(BaseModel):
    """错误响应包装"""

    error: ErrorDetail


class RedlineInfo(BaseModel):
    """红线检测结果 — 嵌入 ProcessResponse，触发时不为 None"""

    triggered: bool = False
    category: str = ""
    message: str = ""
    action: str = Field(
        "reject",
        pattern="^(reject|guided_reject|degrade)$",
    )


# ────────────────────────── 请求/响应模型 ──────────────────────────


class ProcessRequest(BaseModel):
    """核心流程请求"""

    query: str = Field(..., min_length=1, max_length=500)
    image: Optional[str] = Field(
        None,
        description="Base64 截图；Demo 阶段可空，后端返回预置数据",
    )
    window_title: Optional[str] = Field(None, max_length=256)
    context: Optional[List[ChatTurn]] = Field(None, max_length=3)
    screen_fingerprint: Optional[str] = Field(
        None,
        max_length=64,
        description="B 端屏幕指纹，用于 parse 结果缓存",
    )
    capture_size: Optional[List[int]] = Field(
        None,
        description="原始截图像素 [w,h]，L4 坐标校准",
    )
    upload_size: Optional[List[int]] = Field(
        None,
        description="实际上传图像素 [w,h]",
    )
    screen_metrics: Optional[dict] = Field(
        None,
        description="B 端屏幕 DPR/逻辑尺寸，供 L4 overlay 映射",
    )
    assist_bundle: Optional[dict] = Field(
        None,
        description="B 端辅助采集包：前台窗口/场景/结构化候选",
    )


class ProcessResponse(BaseModel):
    """核心流程响应"""

    task_id: str
    success: bool
    intent: Intent
    ui_elements: List[UIElement]
    annotated_image: Optional[str] = Field(
        None, description="带 SoM 标注的截图 Base64"
    )
    blueprint: Blueprint
    steps: List[Step]
    constraints: Optional[dict] = Field(
        None, description="从用户输入提取的约束条件（如安装路径、保存位置）"
    )
    reference_resolution: Optional[List[int]] = Field(
        None, description="截图物理像素 [w, h]，供 B 端坐标映射"
    )
    detection_meta: Optional[dict] = Field(
        None, description="{latency_ms, element_count, backend}"
    )
    redline: Optional[RedlineInfo] = Field(
        None, description="红线检测结果，触发时不为 None"
    )
    goal: Optional[str] = Field(None, description="L5 任务目标摘要")


class CancelRequest(BaseModel):
    """L5 取消任务请求"""

    task_id: str = Field(..., description="任务 ID")


class StepRequest(BaseModel):
    """推进蓝图请求"""

    task_id: str
    action: str = Field(
        ...,
        pattern="^(advance|rollback|skip|terminate)$",
    )
    step_index: Optional[int] = Field(None, ge=1)
    fingerprint: Optional[str] = None
    image: Optional[str] = Field(
        None,
        description="新截图 Base64；用于无绑定步骤的动态重规划",
    )
    capture_size: Optional[List[int]] = None
    upload_size: Optional[List[int]] = None
    screen_metrics: Optional[dict] = None
    assist_bundle: Optional[dict] = None


class StepResponse(BaseModel):
    """推进蓝图响应"""

    task_id: str
    action: str = Field(
        ...,
        pattern="^(advance|rollback|skip|suspended|complete|terminated)$",
    )
    current_step: int = Field(..., ge=1)
    blueprint_state: str
    next_step: Optional[Step] = None
    message: Optional[str] = None


class ClarifyRequest(BaseModel):
    """澄清请求"""

    task_id: str
    answer: str = Field(..., min_length=1, max_length=500)


class ClarifyResponse(BaseModel):
    """澄清响应"""

    task_id: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_clarification: bool
    question: Optional[str] = None
    updated_intent: Optional[Intent] = None


class ReportRequest(BaseModel):
    """审计上报请求"""

    task_id: str
    result: Optional[str] = Field(
        None,
        pattern="^(success|fail|cancel|redirect)$",
    )
    feedback_type: Optional[str] = Field(
        None,
        pattern="^(useful|useless|neutral)$",
    )
    duration_ms: Optional[int] = Field(None, ge=0)
    comment: Optional[str] = None


class ReportResponse(BaseModel):
    """审计上报响应"""

    received: bool


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    version: str
    detector_backend: Optional[str] = None
    detector_active: Optional[str] = None
    detector_device: Optional[str] = None
    omniparser_url: Optional[str] = None
    # 纯视觉模式（无 OmniParser）下返回字符串 "not_required"
    omniparser_ready: Optional[Union[bool, str]] = None
    config_source: Optional[str] = None
    routing_mode: Optional[str] = None
    llm_configured: Optional[bool] = None
    l4_capable: Optional[bool] = None


class RelocateRequest(BaseModel):
    """重新定位请求 — 当前画面找不到目标元素时手动截图重新定位"""

    task_id: str
    step_index: int = Field(..., ge=1)
    image: str = Field(
        ...,
        description="新截图 Base64，含 data URI 前缀",
    )
    capture_size: Optional[List[int]] = None
    upload_size: Optional[List[int]] = None
    screen_metrics: Optional[dict] = None
    assist_bundle: Optional[dict] = None


class RelocateResponse(BaseModel):
    """重新定位响应 — 返回更新后的标注与全量元素"""

    success: bool = True
    task_id: str
    step_index: int
    target_element_id: Optional[str] = None
    annotation: Optional[Annotation] = None
    ui_elements: List[UIElement] = []
    reference_resolution: Optional[List[int]] = Field(
        None, description="截图物理像素 [w, h]，供 B 端坐标映射"
    )


class LocateRequest(BaseModel):
    """Per-step Vision 定位 — L4 / L3_DEFERRED 路径"""

    task_id: str
    step_index: int = Field(..., ge=1)
    image: str = Field(..., description="当前截图 Base64")
    query: Optional[str] = Field(None, description="可选覆盖原始用户目标")
    capture_size: Optional[List[int]] = None
    upload_size: Optional[List[int]] = None
    screen_metrics: Optional[dict] = None


class LocateResponse(BaseModel):
    """Vision 定位响应"""

    success: bool = True
    task_id: str
    step_index: int
    target_element_id: Optional[str] = None
    annotation: Optional[Annotation] = None
    reference_resolution: Optional[List[int]] = None
    detection_meta: Optional[dict] = None


class InspectRequest(BaseModel):
    """检验模式请求 — 立即检测当前屏幕，不生成 task/steps"""

    image: str = Field(
        ...,
        description="Base64 截图，含 data URI 前缀",
    )
    screen_width: Optional[int] = Field(
        None, description="屏幕物理宽度（像素）"
    )
    screen_height: Optional[int] = Field(
        None, description="屏幕物理高度（像素）"
    )
    screen_fingerprint: Optional[str] = Field(
        None,
        max_length=64,
        description="B 端屏幕指纹，用于 parse 结果缓存",
    )


class InspectResponse(BaseModel):
    """检验模式响应 — 全量 UI 元素 + SoM 标注图"""

    success: bool = True
    ui_elements: List[UIElement] = []
    annotated_image: Optional[str] = Field(
        None, description="带 SoM 编号标注的截图 Base64"
    )
    reference_resolution: Optional[List[int]] = Field(
        None, description="截图物理像素 [w, h]，供 B 端坐标映射"
    )
    detection_meta: Optional[dict] = Field(
        None, description="{latency_ms, element_count, backend}"
    )
