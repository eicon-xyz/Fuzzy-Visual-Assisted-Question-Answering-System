"""Status badge breathing animation — aligned with style_preview_demo pulse."""
from __future__ import annotations

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QWidget


class BadgeBreathController:
    """Opacity pulse for top-bar status badge during processing."""

    def __init__(self, badge: QWidget, parent: QWidget | None = None):
        self._badge = badge
        self._parent = parent or badge
        self._fx: QGraphicsOpacityEffect | None = None
        self._group: QSequentialAnimationGroup | None = None

    def _ensure_effect(self) -> QGraphicsOpacityEffect:
        if self._fx is None:
            self._fx = QGraphicsOpacityEffect(self._badge)
            self._badge.setGraphicsEffect(self._fx)
            self._fx.setOpacity(1.0)
        return self._fx

    def _ensure_group(self) -> QSequentialAnimationGroup:
        if self._group is not None:
            return self._group
        fx = self._ensure_effect()
        fade_in = QPropertyAnimation(fx, b"opacity", self._parent)
        fade_in.setDuration(1200)
        fade_in.setStartValue(0.72)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutSine)

        fade_out = QPropertyAnimation(fx, b"opacity", self._parent)
        fade_out.setDuration(1200)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.72)
        fade_out.setEasingCurve(QEasingCurve.InOutSine)

        group = QSequentialAnimationGroup(self._parent)
        group.addAnimation(fade_in)
        group.addAnimation(fade_out)
        group.setLoopCount(-1)
        self._group = group
        return group

    def start(self) -> None:
        group = self._ensure_group()
        if group.state() != QSequentialAnimationGroup.Running:
            group.start()

    def stop(self) -> None:
        if self._group is not None and self._group.state() == QSequentialAnimationGroup.Running:
            self._group.stop()
        self._badge.setGraphicsEffect(None)
        self._fx = None
        self._group = None
