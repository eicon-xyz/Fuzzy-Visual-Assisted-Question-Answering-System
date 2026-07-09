# -*- coding: utf-8 -*-
"""生成《HAJIMI 用户手册》所需的非截图示意图（白底，面向普通用户，尽量少术语）。"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

for name in ["Microsoft YaHei", "SimHei", "SimSun"]:
    try:
        matplotlib.rcParams["font.family"] = name; break
    except Exception:
        continue
matplotlib.rcParams["axes.unicode_minus"] = False
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(OUT, exist_ok=True)

INK = "#243b53"; BLUE = "#2563eb"; GREEN = "#16a34a"; AMBER = "#d97706"
RED = "#dc2626"; GRAY = "#6b7280"; LINE = "#94a3b8"


def save(fig, n):
    p = os.path.join(OUT, n)
    fig.savefig(p, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig); print("saved", n)


def step_flow(name, title, steps, colors=None):
    n = len(steps)
    fig, ax = plt.subplots(figsize=(11, 2.9)); ax.set_xlim(0, 11); ax.set_ylim(0, 2.9); ax.axis("off")
    ax.text(5.5, 2.66, title, ha="center", color=INK, fontsize=14, fontweight="bold")
    if colors is None:
        colors = [BLUE, GREEN, AMBER, "#0891b2", "#7c3aed"][:n]
    w = 1.85; gap = (11 - 0.6 - n * w) / max(1, n - 1); x = 0.3; y = 0.75
    cx = []
    for i, s in enumerate(steps):
        c = colors[i % len(colors)]
        ax.add_patch(FancyBboxPatch((x, y), w, 1.15, boxstyle="round,pad=0.02,rounding_size=0.1",
                     fc="white", ec=c, lw=2))
        # 圆形序号
        ax.add_patch(plt.Circle((x + 0.35, y + 0.9), 0.16, color=c))
        ax.text(x + 0.35, y + 0.9, str(i + 1), ha="center", va="center", color="white",
                fontsize=11, fontweight="bold")
        ax.text(x + w / 2, y + 0.42, s, ha="center", va="center", color=INK, fontsize=10.5,
                wrap=True)
        cx.append(x + w); x += w + gap
    for i in range(n - 1):
        ax.add_patch(FancyArrowPatch((cx[i], y + 0.6), (cx[i] + gap, y + 0.6),
                     arrowstyle="-|>", mutation_scale=18, color=LINE, lw=2))
    save(fig, name)


# 三步上手
step_flow("fig_quickstart.png", "三步上手",
          ["打开 HAJIMI\n桌面助手", "用一句话说出\n你想做的事", "跟着屏幕提示\n完成操作"])

# 智能指引流程
step_flow("fig_guide.png", "智能指引：我来告诉你点哪里",
          ["输入你的问题\n如“怎么设置Wi-Fi”", "助手查看\n当前屏幕", "屏幕上出现\n箭头与高亮编号", "照着提示\n一步步操作"])

# 自动执行流程
step_flow("fig_auto.png", "自动执行：交给我来做",
          ["切换到\n自动执行", "输入要完成\n的任务", "确认弹出的\n安全提示", "助手自动\n点击输入", "查看完成\n结果"],
          colors=[BLUE, GREEN, AMBER, RED, "#0891b2"])

# 安全提示说明
def safety():
    fig, ax = plt.subplots(figsize=(10, 3.4)); ax.set_xlim(0, 10); ax.set_ylim(0, 3.4); ax.axis("off")
    ax.text(5, 3.15, "安全护栏：重要操作会先征求你的同意", ha="center", color=INK, fontsize=14, fontweight="bold")
    def box(x, y, w, h, t, c, fc):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                     fc=fc, ec=c, lw=2))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", color=INK, fontsize=11, fontweight="bold")
    box(0.4, 1.2, 2.7, 1.1, "普通操作\n直接执行", GREEN, "#dcfce7")
    box(3.65, 1.2, 2.7, 1.1, "重要操作\n弹窗请你确认", AMBER, "#fef3c7")
    box(6.9, 1.2, 2.7, 1.1, "危险操作\n直接拒绝", RED, "#fee2e2")
    ax.text(5, 0.5, "你可以随时点“停止”，或把鼠标快速移到屏幕左上角来紧急中止",
            ha="center", color=GRAY, fontsize=10.5)
    save(fig, "fig_safety.png")


safety()
print("ALL DONE")
