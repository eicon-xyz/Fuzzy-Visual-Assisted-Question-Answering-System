"""Prepare 步骤引导：情境文案 + 多预设操作。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

PrepareAction = Literal["relocate", "advance", "skip", "dismiss"]

_DEFER_KEYWORDS = ("等待", "稍候", "加载", "切换", "打开应用", "先手动")
_DESKTOP_KEYWORDS = ("桌面", "图标", "icon", "快捷方式")


@dataclass(frozen=True)
class PreparePreset:
    id: str
    label: str
    description: str
    action: PrepareAction
    primary: bool = False


@dataclass
class PrepareScene:
    scene_id: str
    title: str
    body: str
    primary_preset_id: str
    presets: List[PreparePreset] = field(default_factory=list)
    banner_prefix: str = "⏳ 未定位到目标"

    def primary_preset(self) -> Optional[PreparePreset]:
        for p in self.presets:
            if p.id == self.primary_preset_id:
                return p
        return self.presets[0] if self.presets else None

    def secondary_presets(self) -> List[PreparePreset]:
        return [p for p in self.presets if p.id != self.primary_preset_id]

    def preset_by_id(self, preset_id: str) -> Optional[PreparePreset]:
        for p in self.presets:
            if p.id == preset_id:
                return p
        return None

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "body": self.body,
            "primary_preset_id": self.primary_preset_id,
            "banner_prefix": self.banner_prefix,
            "presets": [
                {
                    "id": p.id,
                    "label": p.label,
                    "description": p.description,
                    "action": p.action,
                    "primary": p.id == self.primary_preset_id,
                }
                for p in self.presets
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PrepareScene":
        presets = [
            PreparePreset(
                id=p["id"],
                label=p["label"],
                description=p.get("description", ""),
                action=p["action"],
                primary=bool(p.get("primary")),
            )
            for p in data.get("presets") or []
        ]
        return cls(
            scene_id=data.get("scene_id", "locate_failed_first"),
            title=data.get("title", "请先完成这一步"),
            body=data.get("body", ""),
            primary_preset_id=data.get("primary_preset_id", ""),
            presets=presets,
            banner_prefix=data.get("banner_prefix", "⏳ 未定位到目标"),
        )


def _target_label(step: dict) -> str:
    return (
        step.get("target")
        or step.get("description")
        or step.get("action")
        or "目标元素"
    )


def _step_text(step: dict) -> str:
    return f"{step.get('description', '')} {step.get('action', '')} {step.get('target', '')}"


def _build_locate_failed_first(target: str) -> PrepareScene:
    presets = [
        PreparePreset(
            id="relocate",
            label="重新定位",
            description="目标已在当前画面可见",
            action="relocate",
            primary=True,
        ),
        PreparePreset(
            id="advance",
            label="我已手动完成，继续下一步",
            description="无需再定位当前步，进入下一步",
            action="advance",
        ),
        PreparePreset(
            id="switch_relocate",
            label="切换到正确窗口后再定位",
            description="先回到桌面或目标窗口，再重新定位",
            action="relocate",
        ),
        PreparePreset(
            id="skip",
            label="跳过此步",
            description="暂时跳过当前步骤",
            action="skip",
        ),
        PreparePreset(
            id="dismiss",
            label="稍后处理",
            description="关闭对话框，稍后再试",
            action="dismiss",
        ),
    ]
    return PrepareScene(
        scene_id="locate_failed_first",
        title="未能定位目标",
        body=(
            f"未能找到「{target}」。\n"
            f"若目标已在当前画面，请点击「重新定位」。"
            f"若您已手动完成本步，可展开更多选项选择「继续下一步」。"
        ),
        primary_preset_id="relocate",
        presets=presets,
        banner_prefix="⏳ 未定位到目标",
    )


def _build_locate_failed_retry(target: str, step_num: int, total_steps: int) -> PrepareScene:
    body = (
        f"仍找不到「{target}」。\n"
        f"若您已手动打开或完成本步，请继续下一步，不必反复定位。"
    )
    if total_steps > 1 and step_num < total_steps:
        body += f"\n（当前第 {step_num}/{total_steps} 步，下一步会在新画面重新定位。）"

    presets = [
        PreparePreset(
            id="advance",
            label="继续下一步",
            description="本步已手动完成，进入下一步",
            action="advance",
            primary=True,
        ),
        PreparePreset(
            id="relocate",
            label="回到目标窗口后重新定位",
            description="先切换到桌面或目标窗口，再试一次",
            action="relocate",
        ),
        PreparePreset(
            id="skip",
            label="跳过此步",
            description="暂时跳过当前步骤",
            action="skip",
        ),
        PreparePreset(
            id="dismiss",
            label="稍后处理",
            description="关闭对话框，稍后再试",
            action="dismiss",
        ),
    ]
    return PrepareScene(
        scene_id="locate_failed_retry",
        title="仍未能定位",
        body=body,
        primary_preset_id="advance",
        presets=presets,
        banner_prefix="⏳ 可尝试继续下一步",
    )


def _build_multi_step_stuck(target: str, step_num: int, total_steps: int) -> PrepareScene:
    presets = [
        PreparePreset(
            id="advance",
            label="继续下一步",
            description="本步已完成，下一步会重新定位",
            action="advance",
            primary=True,
        ),
        PreparePreset(
            id="relocate",
            label="重新定位",
            description="目标仍在当前画面，再试一次",
            action="relocate",
        ),
        PreparePreset(
            id="skip",
            label="跳过此步",
            description="暂时跳过当前步骤",
            action="skip",
        ),
        PreparePreset(
            id="dismiss",
            label="稍后处理",
            description="关闭对话框，稍后再试",
            action="dismiss",
        ),
    ]
    return PrepareScene(
        scene_id="multi_step_stuck",
        title=f"第 {step_num} 步需要您的确认",
        body=(
            f"当前是第 {step_num}/{total_steps} 步：{target}。\n"
            f"若本步已完成，进入下一步后 HAJIMI 会在新画面重新定位。"
        ),
        primary_preset_id="advance",
        presets=presets,
        banner_prefix="⏳ 可尝试继续下一步",
    )


def _build_deferred_manual(hint: str, target: str) -> PrepareScene:
    presets = [
        PreparePreset(
            id="relocate",
            label="我已完成，重新定位",
            description="在新画面中定位目标",
            action="relocate",
            primary=True,
        ),
        PreparePreset(
            id="advance",
            label="我已手动完成，继续下一步",
            description="跳过定位，直接进入下一步",
            action="advance",
        ),
        PreparePreset(
            id="dismiss",
            label="稍后处理",
            description="关闭对话框，稍后再试",
            action="dismiss",
        ),
    ]
    return PrepareScene(
        scene_id="deferred_manual",
        title="请先手动完成",
        body=f"请先完成：{hint or target}。\n完成后 HAJIMI 将在新画面定位目标。",
        primary_preset_id="relocate",
        presets=presets,
        banner_prefix="⏳ 请先手动完成",
    )


def _build_browser_desktop_mismatch(target: str, window_title: str) -> PrepareScene:
    win = window_title or "当前窗口"
    presets = [
        PreparePreset(
            id="advance",
            label="我已打开目标，继续下一步",
            description="本步目标不在浏览器窗口，可手动完成后继续",
            action="advance",
            primary=True,
        ),
        PreparePreset(
            id="switch_relocate",
            label="切换到桌面后重新定位",
            description="先最小化浏览器回到桌面，再重新定位",
            action="relocate",
        ),
        PreparePreset(
            id="relocate",
            label="在当前画面重新定位",
            description="若目标已在当前画面可见",
            action="relocate",
        ),
        PreparePreset(
            id="dismiss",
            label="稍后处理",
            description="关闭对话框，稍后再试",
            action="dismiss",
        ),
    ]
    return PrepareScene(
        scene_id="browser_desktop_mismatch",
        title="当前在浏览器窗口",
        body=(
            f"您当前前台是「{win}」，但本步需要定位桌面上的「{target}」。\n"
            f"请先切换到桌面，或使用「继续下一步」若您已手动打开目标。"
        ),
        primary_preset_id="advance",
        presets=presets,
        banner_prefix="⏳ 请切换到桌面",
    )


def resolve_prepare_scene(
    step: dict,
    *,
    relocate_fail_count: int = 0,
    current_step_index: int = 0,
    total_steps: int = 1,
    force_deferred: bool = False,
    scene_hint: Optional[str] = None,
    assist_bundle: Optional[dict] = None,
) -> PrepareScene:
    """根据步骤与失败次数解析引导场景。"""
    target = _target_label(step)
    hint = step.get("prepare_hint") or step.get("description") or target
    step_num = current_step_index + 1
    text = _step_text(step)

    if scene_hint is None and isinstance(assist_bundle, dict):
        scene_hint = (assist_bundle.get("screen") or {}).get("scene_hint")

    if scene_hint == "browser" and any(k in text for k in _DESKTOP_KEYWORDS):
        fg_title = ""
        if isinstance(assist_bundle, dict):
            fg_title = (assist_bundle.get("foreground") or {}).get("window_title") or ""
        return _build_browser_desktop_mismatch(target, fg_title)

    if force_deferred or step.get("locate_deferred"):
        return _build_deferred_manual(hint, target)

    if relocate_fail_count >= 1:
        if total_steps > 1 and step_num < total_steps:
            if any(k in text for k in _DESKTOP_KEYWORDS):
                return _build_locate_failed_retry(target, step_num, total_steps)
            return _build_multi_step_stuck(target, step_num, total_steps)
        return _build_locate_failed_retry(target, step_num, total_steps)

    return _build_locate_failed_first(target)


BANNER_PREFIX_BY_SCENE: Dict[str, str] = {
    "locate_failed_first": "⏳ 未定位到目标",
    "locate_failed_retry": "⏳ 可尝试继续下一步",
    "deferred_manual": "⏳ 请先手动完成",
    "multi_step_stuck": "⏳ 可尝试继续下一步",
    "browser_desktop_mismatch": "⏳ 请切换到桌面",
}
