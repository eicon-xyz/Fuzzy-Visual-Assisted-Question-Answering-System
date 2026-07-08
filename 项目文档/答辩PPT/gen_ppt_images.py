# -*- coding: utf-8 -*-
"""生成 HAJIMI 答辩 PPT 所需图表 -> images/*.png"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
from matplotlib.font_manager import FontProperties

# ---- 中文字体 ----
for name in ["Microsoft YaHei", "SimHei", "SimSun"]:
    try:
        matplotlib.rcParams["font.family"] = name
        break
    except Exception:
        continue
matplotlib.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(OUT, exist_ok=True)

# 配色
C_BG = "#0f172a"
C_CARD = "#1e293b"
BLUE = "#3b82f6"
CYAN = "#06b6d4"
GREEN = "#22c55e"
AMBER = "#f59e0b"
RED = "#ef4444"
PURPLE = "#a855f7"
SLATE = "#64748b"
WHITE = "#f8fafc"


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print("saved", path)


def rbox(ax, x, y, w, h, text, fc, tc=WHITE, fs=12, bold=True, ec="none", lw=0):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.02,rounding_size=0.08",
                 fc=fc, ec=ec, lw=lw, mutation_aspect=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            color=tc, fontsize=fs, fontweight="bold" if bold else "normal",
            wrap=True)


def arrow(ax, x1, y1, x2, y2, color=WHITE, lw=2, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                 arrowstyle=style, mutation_scale=18, color=color, lw=lw))


# ============ P02 痛点对比 ============
def p02():
    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor=C_BG)
    ax.set_xlim(0, 11); ax.set_ylim(0, 5.2); ax.axis("off")
    ax.text(5.5, 4.9, "传统操作  VS  HAJIMI 一步到位", ha="center",
            color=WHITE, fontsize=17, fontweight="bold")
    # 左：痛点
    rbox(ax, 0.3, 0.5, 4.3, 3.9, "", C_CARD, ec=SLATE, lw=1)
    ax.text(2.45, 4.05, "传统方式", ha="center", color=RED, fontsize=14, fontweight="bold")
    pains = ["找不到按钮在哪", "看不清界面入口",
             "教程和界面对不上", "反复查资料 / 切窗口", "老年 · 视障用户更吃力"]
    for i, p in enumerate(pains):
        ax.text(0.62, 3.5 - i * 0.55, "×", color=RED, fontsize=13, fontweight="bold")
        ax.text(0.95, 3.5 - i * 0.55, p, color=WHITE, fontsize=12)
    # 箭头
    arrow(ax, 4.75, 2.4, 6.25, 2.4, color=CYAN, lw=3)
    ax.text(5.5, 2.75, "一句话", ha="center", color=CYAN, fontsize=12, fontweight="bold")
    # 右：HAJIMI
    rbox(ax, 6.4, 0.5, 4.3, 3.9, "", C_CARD, ec=CYAN, lw=1.5)
    ax.text(8.55, 4.05, "HAJIMI", ha="center", color=CYAN, fontsize=14, fontweight="bold")
    goods = ["说出目标即可", "自动定位屏幕元素",
             "箭头/高亮画在界面上", "代为点击 · 输入 · 双击", "全程安全评分兜底"]
    for i, g in enumerate(goods):
        ax.text(6.72, 3.5 - i * 0.55, "√", color=GREEN, fontsize=13, fontweight="bold")
        ax.text(7.05, 3.5 - i * 0.55, g, color=WHITE, fontsize=12)
    save(fig, "P02_pain_vs_hajimi.png")


# ============ P03 能力链 ============
def p03():
    fig, ax = plt.subplots(figsize=(11, 5), facecolor=C_BG)
    ax.set_xlim(0, 11); ax.set_ylim(0, 5); ax.axis("off")
    # 安全边界顶条
    rbox(ax, 0.4, 4.0, 10.2, 0.8,
         "安全边界：风险评分(1-5)  +  红线关键词拦截  +  用户确认",
         "#7f1d1d", tc=WHITE, fs=13)
    stages = [
        ("屏幕感知", ["OmniParser 元素检测", "多模态 LLM 看图"], BLUE),
        ("意图理解", ["9 大意图域分类", "5 种指代消解"], PURPLE),
        ("自动执行", ["click / type / dblclick", "hotkey / drag / scroll"], GREEN),
    ]
    w = 3.0; gap = 0.55; x = 0.6; y = 1.4
    centers = []
    for title, items, col in stages:
        rbox(ax, x, y, w, 2.2, "", C_CARD, ec=col, lw=2)
        ax.text(x + w / 2, y + 1.75, title, ha="center", color=col,
                fontsize=15, fontweight="bold")
        for i, it in enumerate(items):
            ax.text(x + w / 2, y + 1.15 - i * 0.5, it, ha="center",
                    color=WHITE, fontsize=11)
        centers.append(x + w)
        x += w + gap
    arrow(ax, centers[0], y + 1.1, centers[0] + gap, y + 1.1, color=CYAN, lw=3)
    arrow(ax, centers[1], y + 1.1, centers[1] + gap, y + 1.1, color=CYAN, lw=3)
    ax.text(5.5, 0.6, "用户目标  →  感知  →  理解  →  执行  →  完成",
            ha="center", color=SLATE, fontsize=12)
    save(fig, "P03_capability_chain.png")


# ============ P04 四层架构 ============
def p04():
    fig, ax = plt.subplots(figsize=(11, 6.2), facecolor=C_BG)
    ax.set_xlim(0, 11); ax.set_ylim(0, 6.2); ax.axis("off")
    layers = [
        ("表示层", ["PyQt5 桌面面板", "透明覆盖层", "Web 管理面板(Vue3)"], BLUE, 4.85),
        ("应用层", ["执行引擎", "步骤状态机", "审计代理", "配置轮询"], PURPLE, 3.55),
        ("服务层", ["FastAPI 26端点", "LLM 规划", "风险评分", "红线检测"], AMBER, 2.25),
        ("数据层", ["SQLite 7表", "OmniParser GPU:9800", "多模态 LLM API"], GREEN, 0.95),
    ]
    for title, mods, col, y in layers:
        rbox(ax, 2.4, y, 8.3, 1.1, "", C_CARD, ec=col, lw=2)
        rbox(ax, 0.4, y, 1.8, 1.1, title, col, tc="#0f172a", fs=14)
        n = len(mods); mw = 8.0 / n
        for i, m in enumerate(mods):
            ax.text(2.6 + i * mw + mw / 2, y + 0.55, m, ha="center",
                    va="center", color=WHITE, fontsize=10.5)
    for y in [4.65, 3.35, 2.05]:
        arrow(ax, 6.5, y, 6.5, y - 0.2, color=WHITE, lw=2)
    ax.text(5.5, 5.9, "系统四层逻辑架构", ha="center", color=WHITE,
            fontsize=17, fontweight="bold")
    ax.text(5.5, 0.3, "三进程：B端 PyQt5  →  A端 FastAPI:8010  →  OmniParser / LLM",
            ha="center", color=CYAN, fontsize=12, fontweight="bold")
    save(fig, "P04_architecture.png")


# ============ P05 时序图 ============
def p05():
    fig, ax = plt.subplots(figsize=(11, 6.2), facecolor=C_BG)
    ax.set_xlim(0, 11); ax.set_ylim(0, 6.2); ax.axis("off")
    ax.text(5.5, 5.95, "核心业务时序", ha="center", color=WHITE, fontsize=17, fontweight="bold")
    actors = [("用户", 1.0, SLATE), ("B端", 3.3, BLUE), ("A端", 5.6, AMBER),
              ("OmniParser", 8.0, GREEN), ("执行引擎", 10.2, PURPLE)]
    for name, x, col in actors:
        rbox(ax, x - 0.75, 5.0, 1.5, 0.55, name, col, tc="#0f172a", fs=11)
        ax.plot([x, x], [0.4, 5.0], color=SLATE, lw=1, ls="--")
    steps = [
        (1.0, 3.3, "① 语音/文本目标", 4.6),
        (3.3, 3.3, "② mss 截图", 4.15),
        (3.3, 5.6, "③ POST /execute(指令+截图)", 3.7),
        (5.6, 8.0, "④ 解析元素 + SoM 标注", 3.25),
        (5.6, 5.6, "⑤ 风险评分 + 红线 + LLM 规划", 2.8),
        (5.6, 3.3, "⑥ SSE /stream 推送步骤", 2.35),
        (3.3, 10.2, "⑦ pyautogui 执行", 1.9),
        (3.3, 5.6, "⑧ POST /audit/report", 1.45),
    ]
    for x1, x2, text, y in steps:
        if x1 == x2:
            ax.add_patch(FancyArrowPatch((x1, y + 0.05), (x1 + 0.9, y + 0.05),
                         arrowstyle="-|>", mutation_scale=12, color=CYAN, lw=1.5))
            ax.add_patch(FancyArrowPatch((x1 + 0.9, y + 0.05), (x1, y - 0.12),
                         arrowstyle="-|>", mutation_scale=12, color=CYAN, lw=1.5))
            ax.text(x1 + 0.15, y + 0.18, text, color=WHITE, fontsize=10, ha="left")
        else:
            arrow(ax, x1, y, x2, y, color=CYAN, lw=1.8)
            ax.text((x1 + x2) / 2, y + 0.12, text, color=WHITE, fontsize=10, ha="center")
    save(fig, "P05_sequence.png")


# ============ P06 端点表 ============
def p06():
    fig, ax = plt.subplots(figsize=(11, 6), facecolor=C_BG)
    ax.set_xlim(0, 11); ax.set_ylim(0, 6); ax.axis("off")
    ax.text(5.5, 5.7, "A 端 · FastAPI :8010 · 共 26 端点 / 7 模块",
            ha="center", color=WHITE, fontsize=16, fontweight="bold")
    groups = [
        ("Demo (5)", ["health", "execute ★", "stream(SSE) ★", "cancel", "process"], BLUE),
        ("Admin (11)", ["overview / trend", "redline / feedback", "failures 归因",
                         "config 热部署", "metrics / session"], AMBER),
        ("审计 (2)", ["audit/report ★", "audit/feedback"], GREEN),
        ("认证 (1)", ["auth/login (JWT)"], PURPLE),
        ("数据流 (3)", ["flow/topology", "flow/metrics", "flow/versions"], CYAN),
        ("监控 (3)", ["monitor/health", "monitor/alerts", "alerts/read-all"], RED),
    ]
    positions = [(0.3, 3.0), (3.8, 3.0), (7.3, 3.0),
                 (0.3, 0.3), (3.8, 0.3), (7.3, 0.3)]
    w, h = 3.3, 2.4
    for (title, items, col), (x, y) in zip(groups, positions):
        rbox(ax, x, y, w, h, "", C_CARD, ec=col, lw=1.8)
        ax.text(x + w / 2, y + h - 0.35, title, ha="center", color=col,
                fontsize=13, fontweight="bold")
        for i, it in enumerate(items):
            ax.text(x + 0.25, y + h - 0.85 - i * 0.38, "• " + it,
                    color=WHITE, fontsize=10.5, ha="left")
    ax.text(5.5, 0.02, "★ 核心链路  ·  双密钥鉴权 X-Demo-Key / X-Admin-Key",
            ha="center", color=SLATE, fontsize=11)
    save(fig, "P06_endpoints.png")


# ============ P11 测试矩阵 ============
def p11():
    fig, ax = plt.subplots(figsize=(11, 5.6), facecolor=C_BG)
    labels = ["Web面板\n55", "联调\n48", "B-C\n36", "审计E2E\n25",
              "管理\n54", "真实接口\n18"]
    vals = [55, 48, 36, 25, 54, 18]
    cols = [BLUE, CYAN, PURPLE, GREEN, AMBER, RED]
    ax.set_facecolor(C_BG)
    bars = ax.bar(range(len(vals)), vals, color=cols, width=0.62)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.2, str(v),
                ha="center", color=WHITE, fontsize=13, fontweight="bold")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, color=WHITE, fontsize=11)
    ax.set_ylim(0, 65)
    ax.tick_params(colors=WHITE)
    for s in ax.spines.values():
        s.set_color(SLATE)
    ax.set_title("测试覆盖矩阵 · 累计 237 项全部通过",
                 color=WHITE, fontsize=16, fontweight="bold", pad=14)
    ax.text(0.5, 0.94, "覆盖 Happy Path + 异常路径（红线/澄清/指纹/断网）· 26端点全检 · Web 6页回归",
            transform=ax.transAxes, ha="center", color=SLATE, fontsize=10.5)
    save(fig, "P11_test_matrix.png")


# ============ P12 完成度 + 时间线 ============
def p12():
    fig = plt.figure(figsize=(11, 5.4), facecolor=C_BG)
    ax1 = fig.add_axes([0.04, 0.1, 0.42, 0.78]); ax1.set_facecolor(C_BG)
    ends = ["A端\n26/26", "B端\n9/11", "C端\n6/6"]
    done = [26, 9, 6]; total = [26, 11, 6]
    pct = [d / t * 100 for d, t in zip(done, total)]
    cols = [GREEN, AMBER, GREEN]
    y = range(len(ends))
    ax1.barh(y, [100] * 3, color=C_CARD, height=0.55)
    ax1.barh(y, pct, color=cols, height=0.55)
    for i, (p, e) in enumerate(zip(pct, ends)):
        ax1.text(p - 3, i, f"{p:.0f}%", va="center", ha="right",
                 color="#0f172a", fontsize=12, fontweight="bold")
    ax1.set_yticks(list(y)); ax1.set_yticklabels(ends, color=WHITE, fontsize=11)
    ax1.set_xlim(0, 100); ax1.set_xticks([])
    for s in ax1.spines.values():
        s.set_visible(False)
    ax1.set_title("三端完成度", color=WHITE, fontsize=15, fontweight="bold")

    ax2 = fig.add_axes([0.52, 0.05, 0.46, 0.9]); ax2.axis("off")
    ax2.set_xlim(0, 10); ax2.set_ylim(0, 10)
    ax2.text(5, 9.6, "后续展望", ha="center", color=WHITE, fontsize=15, fontweight="bold")
    items = [
        ("语音全链路打磨", "ASR/TTS 稳定性", CYAN),
        ("L3 规划成功率优化", "复杂任务准确率", PURPLE),
        ("多屏 / 高 DPI 适配", "坐标映射鲁棒性", BLUE),
        ("远程 GPU 部署", "SSH 隧道 + 一键启动", GREEN),
    ]
    ax2.plot([1, 1], [0.6, 8.6], color=SLATE, lw=2)
    for i, (t, d, c) in enumerate(items):
        yy = 8.0 - i * 2.0
        ax2.add_patch(Circle((1, yy), 0.18, color=c))
        ax2.text(1.6, yy + 0.15, t, color=WHITE, fontsize=12.5, fontweight="bold", va="center")
        ax2.text(1.6, yy - 0.45, d, color=SLATE, fontsize=10.5, va="center")
    save(fig, "P12_summary.png")


if __name__ == "__main__":
    p02(); p03(); p04(); p05(); p06(); p11(); p12()
    print("ALL DONE")
