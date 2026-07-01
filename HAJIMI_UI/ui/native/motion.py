"""Shared motion helpers — easing aligned with index.html --ease-out-cubic."""
from PyQt5.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QRect,
    QAbstractAnimation,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QWidget, QStackedWidget


ANIM_SWITCH_MS = 250
ANIM_COMPACT_RESIZE_MS = 320
ANIM_BACKDROP_MS = 200
FADE_OUT_MS = 120
FADE_IN_MS = 200


def out_cubic() -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.BezierSpline)
    curve.addCubicBezierSegment(0.33, 1.0, 0.68, 1.0, 1.0, 1.0)
    return curve


def in_out_cubic() -> QEasingCurve:
    return QEasingCurve(QEasingCurve.InOutCubic)


def _opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        return effect
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    return effect


def animate_fade_in(widget: QWidget, parent: QWidget, duration: int = ANIM_SWITCH_MS):
    """Opacity 0→1 with OutCubic (mode switch)."""
    effect = _opacity_effect(widget)
    effect.setOpacity(0.0)
    anim = QPropertyAnimation(effect, b"opacity", parent)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def cleanup():
        widget.setGraphicsEffect(None)
        widget.update()

    anim.finished.connect(cleanup)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def animate_fade_out(
    widget: QWidget,
    parent: QWidget,
    duration: int = FADE_OUT_MS,
    on_finished=None,
):
    effect = _opacity_effect(widget)
    effect.setOpacity(1.0)
    anim = QPropertyAnimation(effect, b"opacity", parent)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(in_out_cubic())

    def done():
        if on_finished:
            on_finished()

    anim.finished.connect(done)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def animate_backdrop(backdrop: QWidget, show: bool, parent: QWidget):
    """Fade nav backdrop 0↔1."""
    effect = backdrop.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(backdrop)
        backdrop.setGraphicsEffect(effect)
    if show:
        backdrop.show()
        effect.setOpacity(0.0)
    start = effect.opacity()
    end = 1.0 if show else 0.0
    anim = QPropertyAnimation(effect, b"opacity", parent)
    anim.setDuration(ANIM_BACKDROP_MS)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    if not show:
        anim.finished.connect(backdrop.hide)

    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def resize_keep_bottom_right(
    window: QWidget,
    width: int,
    height: int,
    parent: QWidget,
    duration: int = ANIM_COMPACT_RESIZE_MS,
    animated: bool = True,
    easing: QEasingCurve = None,
    on_finished=None,
):
    """Resize window while keeping bottom-right corner fixed."""
    geo = window.geometry()
    new_x = geo.x() + geo.width() - width
    new_y = geo.y() + geo.height() - height
    target = QRect(new_x, new_y, width, height)
    if not animated or duration <= 0:
        window.setGeometry(target)
        if on_finished:
            on_finished()
        return None
    anim = QPropertyAnimation(window, b"geometry", parent)
    anim.setDuration(duration)
    anim.setStartValue(geo)
    anim.setEndValue(target)
    anim.setEasingCurve(easing or in_out_cubic())
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def animate_mode_transition(
    window: QWidget,
    stack: QStackedWidget,
    outgoing: QWidget,
    incoming: QWidget,
    target_width: int,
    target_height: int,
    parent: QWidget,
    on_complete=None,
):
    """Fade out → InOutCubic resize → switch stack → fade in."""

    def after_resize():
        stack.setCurrentWidget(incoming)
        animate_fade_in(incoming, parent, duration=FADE_IN_MS)
        if on_complete:
            on_complete()

    def after_fade_out():
        resize_keep_bottom_right(
            window,
            target_width,
            target_height,
            parent,
            duration=ANIM_COMPACT_RESIZE_MS,
            animated=True,
            easing=in_out_cubic(),
            on_finished=after_resize,
        )

    animate_fade_out(outgoing, parent, duration=FADE_OUT_MS, on_finished=after_fade_out)


def animate_mode_switch_nudge(window: QWidget, parent: QWidget, duration: int = ANIM_SWITCH_MS):
    """Subtle translateY nudge (8px up) while fading — premium mode switch."""
    geo = window.geometry()
    start = QRect(geo.x(), geo.y() + 8, geo.width(), geo.height())
    group = QParallelAnimationGroup(parent)
    move = QPropertyAnimation(window, b"geometry", parent)
    move.setDuration(duration)
    move.setStartValue(start)
    move.setEndValue(geo)
    move.setEasingCurve(QEasingCurve.OutCubic)
    group.addAnimation(move)
    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group
