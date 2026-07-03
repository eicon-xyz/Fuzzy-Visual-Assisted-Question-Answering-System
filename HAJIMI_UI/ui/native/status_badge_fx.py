"""Status badge breathing animation — aligned with style_preview_demo pulse."""
from __future__ import annotations

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QWidget


class BadgeBreathController:
    """Opacity pulse for top-bar status badge during processing."""

    def __init__(self, badge: QWidget, parent: QWidget | None = None):
        self._badge = badge
        self._fx = QGraphicsOpacityEffect(badge)
        badge.setGraphicsEffect(self._fx)
        self._fx.setOpacity(1.0)

        fade_in = QPropertyAnimation(self._fx, b"opacity", parent or badge)
        fade_in.setDuration(1200)
        fade_in.setStartValue(0.72)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutSine)

        fade_out = QPropertyAnimation(self._fx, b"opacity", parent or badge)
        fade_out.setDuration(1200)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.72)
        fade_out.setEasingCurve(QEasingCurve.InOutSine)

        self._group = QSequentialAnimationGroup(parent or badge)
        self._group.addAnimation(fade_in)
        self._group.addAnimation(fade_out)
        self._group.setLoopCount(-1)

    def start(self) -> None:
        if self._group.state() != QSequentialAnimationGroup.Running:
            self._group.start()

    def stop(self) -> None:
        if self._group.state() == QSequentialAnimationGroup.Running:
            self._group.stop()
        self._fx.setOpacity(1.0)
