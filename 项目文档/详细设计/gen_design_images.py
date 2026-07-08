# -*- coding: utf-8 -*-
"""生成《HAJIMI 详细设计》所需的非截图类图表 -> images/*.png（白底，适合打印）。"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

for name in ["Microsoft YaHei", "SimHei", "SimSun"]:
    try:
        matplotlib.rcParams["font.family"] = name
        break
    except Exception:
        continue
matplotlib.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(OUT, exist_ok=True)

INK = "#1f2937"      # 主文字
LINE = "#374151"     # 连线
BLUE = "#2563eb"
CYAN = "#0891b2"
GREEN = "#16a34a"
AMBER = "#d97706"
PURPLE = "#7c3aed"
RED = "#dc2626"
GRAY = "#6b7280"
FILL = "#f3f4f6"


def save(fig, name):
    p = os.path.join(OUT, name)
    fig.savefig(p, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


def box(ax, x, y, w, h, text, ec, fc="white", tc=None, fs=11, bold=True, r=0.06):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle=f"round,pad=0.02,rounding_size={r}",
                 fc=fc, ec=ec, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            color=tc or INK, fontsize=fs, fontweight="bold" if bold else "normal")


def arw(ax, x1, y1, x2, y2, color=LINE, lw=1.6, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                 mutation_scale=16, color=color, lw=lw))


# ---- 图1 项目核心概述 ----
def fig_overview():
    fig, ax = plt.subplots(figsize=(10, 4.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 4.6); ax.axis("off")
    box(ax, 0.3, 1.1, 2.5, 2.4, "", GRAY, FILL)
    ax.text(1.55, 3.2, "目标用户与痛点", ha="center", color=GRAY, fontsize=12, fontweight="bold")
    for i, t in enumerate(["新手：找不到入口", "老年：看不清界面", "视障：读屏不够用"]):
        ax.text(1.55, 2.6 - i * 0.55, t, ha="center", color=INK, fontsize=10.5)
    box(ax, 3.4, 1.1, 3.2, 2.4, "", BLUE)
    ax.text(5.0, 3.2, "系统能力链", ha="center", color=BLUE, fontsize=12, fontweight="bold")
    for i, t in enumerate(["屏幕感知（元素检测）", "意图理解（分类+消解）", "自动执行（点击/输入）"]):
        ax.text(5.0, 2.6 - i * 0.55, t, ha="center", color=INK, fontsize=10.5)
    box(ax, 7.2, 1.1, 2.5, 2.4, "", RED)
    ax.text(8.45, 3.2, "安全边界", ha="center", color=RED, fontsize=12, fontweight="bold")
    for i, t in enumerate(["风险评分 1–5", "红线关键词拦截", "高危自动挂起确认"]):
        ax.text(8.45, 2.6 - i * 0.55, t, ha="center", color=INK, fontsize=10.5)
    arw(ax, 2.8, 2.3, 3.4, 2.3, BLUE); arw(ax, 6.6, 2.3, 7.2, 2.3, RED)
    ax.text(5.0, 0.55, "降低操作门槛 · 实时理解上下文 · 安全地自动完成任务",
            ha="center", color=GRAY, fontsize=11)
    save(fig, "fig01_overview.png")


# ---- 图2 技术架构（四层） ----
def fig_arch():
    fig, ax = plt.subplots(figsize=(10, 6)); ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
    layers = [
        ("表示层", ["PyQt5 桌面面板", "透明标注覆盖层", "Web 管理面板(Vue3)"], BLUE, 4.7),
        ("应用层", ["执行引擎", "步骤状态机", "审计代理", "配置轮询"], PURPLE, 3.5),
        ("服务层", ["FastAPI 26 端点", "LLM 规划", "风险评分", "红线检测"], AMBER, 2.3),
        ("数据层", ["SQLite 7 表", "OmniParser GPU", "多模态 LLM API"], GREEN, 1.1),
    ]
    for title, mods, col, y in layers:
        box(ax, 2.3, y, 7.4, 1.0, "", col)
        box(ax, 0.4, y, 1.6, 1.0, title, col, fc=col, tc="white")
        n = len(mods); mw = 7.2 / n
        for i, m in enumerate(mods):
            ax.text(2.45 + i * mw + mw / 2, y + 0.5, m, ha="center", va="center",
                    color=INK, fontsize=10)
    for y in [4.7, 3.5, 2.3]:
        arw(ax, 6.0, y, 6.0, y - 0.2, LINE)
    ax.text(5.0, 5.85, "图2  HAJIMI 四层逻辑架构（B/A/AI 三进程）",
            ha="center", color=INK, fontsize=12, fontweight="bold")
    ax.text(5.0, 0.55, "B 端 PyQt5  →  A 端 FastAPI:8010  →  OmniParser:9800 / 云端 LLM",
            ha="center", color=CYAN, fontsize=10.5, fontweight="bold")
    save(fig, "fig02_architecture.png")


# ---- 图3 核心控制流程（时序） ----
def fig_flow():
    fig, ax = plt.subplots(figsize=(10, 6)); ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
    ax.text(5, 5.85, "图3  核心控制流程时序", ha="center", color=INK, fontsize=12, fontweight="bold")
    actors = [("用户", 0.9, GRAY), ("B端", 2.9, BLUE), ("A端", 5.0, AMBER),
              ("OmniParser", 7.3, GREEN), ("执行引擎", 9.3, PURPLE)]
    for n, x, c in actors:
        box(ax, x - 0.7, 4.9, 1.4, 0.5, n, c, fc=c, tc="white", fs=10)
        ax.plot([x, x], [0.4, 4.9], color="#d1d5db", lw=1, ls="--")
    steps = [
        (0.9, 2.9, "① 语音/文本目标", 4.5),
        (2.9, 2.9, "② mss 全屏截图", 4.1),
        (2.9, 5.0, "③ POST /execute（指令+截图）", 3.7),
        (5.0, 7.3, "④ 解析元素 + SoM 标注", 3.3),
        (5.0, 5.0, "⑤ 风险评分+红线+LLM 规划", 2.9),
        (5.0, 2.9, "⑥ SSE /stream 推送步骤", 2.5),
        (2.9, 9.3, "⑦ pyautogui 执行动作", 2.1),
        (2.9, 5.0, "⑧ POST /audit/report", 1.7),
    ]
    for x1, x2, t, y in steps:
        if x1 == x2:
            arw(ax, x1, y + 0.04, x1 + 0.8, y + 0.04, CYAN, 1.3)
            arw(ax, x1 + 0.8, y + 0.04, x1, y - 0.1, CYAN, 1.3)
            ax.text(x1 + 0.12, y + 0.16, t, color=INK, fontsize=9.5, ha="left")
        else:
            arw(ax, x1, y, x2, y, CYAN, 1.5)
            ax.text((x1 + x2) / 2, y + 0.1, t, color=INK, fontsize=9.5, ha="center")
    save(fig, "fig03_controlflow.png")


# ---- 图: OmniParser 三模型流程 ----
def fig_omni():
    fig, ax = plt.subplots(figsize=(10, 3.2)); ax.set_xlim(0, 10); ax.set_ylim(0, 3.2); ax.axis("off")
    ax.text(5, 3.0, "屏幕感知：OmniParser 联合推理流程", ha="center", color=INK, fontsize=12, fontweight="bold")
    stages = [("截图\n(mss/PIL)", GRAY), ("YOLO\n图标检测", BLUE),
              ("Florence\n语义描述", PURPLE), ("PaddleOCR\n文本识别", AMBER),
              ("元素列表\n+SoM 标注图", GREEN)]
    w = 1.6; x = 0.3; y = 1.1
    cx = []
    for t, c in stages:
        box(ax, x, y, w, 1.0, t, c, fs=10)
        cx.append(x + w); x += w + 0.45
    for i in range(len(stages) - 1):
        arw(ax, cx[i], y + 0.5, cx[i] + 0.45, y + 0.5, LINE)
    ax.text(5, 0.5, "输出：归一化 0–1000 坐标的可交互元素集合，供 LLM 规划引用",
            ha="center", color=GRAY, fontsize=10)
    save(fig, "fig04_omniparser.png")


# ---- 图: 风险评分/安全分类 ----
def fig_safety():
    fig, ax = plt.subplots(figsize=(9, 4.3)); ax.set_xlim(0, 9); ax.set_ylim(0, 4.3); ax.axis("off")
    ax.text(4.5, 4.1, "安全分类与风险评分流程", ha="center", color=INK, fontsize=12, fontweight="bold")
    box(ax, 3.4, 3.1, 2.2, 0.7, "用户指令/步骤", GRAY)
    box(ax, 3.4, 2.0, 2.2, 0.7, "关键词+正则匹配", CYAN)
    arw(ax, 4.5, 3.1, 4.5, 2.7, LINE)
    box(ax, 0.5, 0.5, 2.3, 0.9, "红线(RED)\n直接拒绝", RED, fc="#fee2e2")
    box(ax, 3.35, 0.5, 2.3, 0.9, "黄线(YELLOW)\n评分≥4 挂起确认", AMBER, fc="#fef3c7")
    box(ax, 6.2, 0.5, 2.3, 0.9, "绿区(GREEN)\n直接执行", GREEN, fc="#dcfce7")
    arw(ax, 4.0, 2.0, 1.6, 1.4, RED); arw(ax, 4.5, 2.0, 4.5, 1.4, AMBER); arw(ax, 5.0, 2.0, 7.4, 1.4, GREEN)
    save(fig, "fig05_safety.png")


# ---- 图: 蓝图状态机 ----
def fig_state():
    fig, ax = plt.subplots(figsize=(9.5, 3.6)); ax.set_xlim(0, 9.5); ax.set_ylim(0, 3.6); ax.axis("off")
    ax.text(4.75, 3.4, "图  蓝图执行状态机", ha="center", color=INK, fontsize=12, fontweight="bold")
    st = {"generated": (0.6, 1.7, BLUE), "executing": (3.0, 1.7, AMBER),
          "completed": (6.2, 2.6, GREEN), "suspended": (6.2, 1.0, RED),
          "terminated": (8.2, 1.0, GRAY)}
    for k, (x, y, c) in st.items():
        box(ax, x, y, 1.7, 0.7, k, c, fs=10)
    arw(ax, 2.3, 2.05, 3.0, 2.05, LINE); ax.text(2.65, 2.2, "/execute", color=GRAY, fontsize=8, ha="center")
    arw(ax, 4.7, 2.2, 6.2, 2.7, GREEN); ax.text(5.4, 2.65, "全部完成", color=GREEN, fontsize=8)
    arw(ax, 4.7, 1.9, 6.2, 1.35, RED); ax.text(5.4, 1.75, "风险≥4/取消", color=RED, fontsize=8)
    arw(ax, 6.2, 1.5, 4.7, 1.75, LINE); ax.text(5.4, 1.4, "确认继续", color=GRAY, fontsize=8)
    arw(ax, 7.9, 1.35, 8.2, 1.35, GRAY)
    save(fig, "fig06_state.png")


# ---- 图: DAO/Repository 类图 ----
def fig_dao():
    fig, ax = plt.subplots(figsize=(10, 4.2)); ax.set_xlim(0, 10); ax.set_ylim(0, 4.2); ax.axis("off")
    ax.text(5, 4.0, "数据访问层（Repository）类图", ha="center", color=INK, fontsize=12, fontweight="bold")
    repos = [
        ("TaskRepository", ["create_from_response()", "update_result()", "get_stats_overview()"]),
        ("RedlineRepository", ["log()", "get_stats()"]),
        ("FeedbackRepository", ["create()"]),
        ("FailureRepository", ["create()", "list() / detail()"]),
        ("ConfigRepository", ["get_all() / get()", "set()"]),
    ]
    xs = [0.2, 2.15, 4.1, 6.05, 8.0]; w = 1.85; y = 1.0; h = 2.4
    for (name, methods), x in zip(repos, xs):
        box(ax, x, y, w, h, "", BLUE, r=0.03)
        ax.text(x + w / 2, y + h - 0.28, name, ha="center", color=BLUE, fontsize=9, fontweight="bold")
        ax.plot([x + 0.1, x + w - 0.1], [y + h - 0.5, y + h - 0.5], color="#d1d5db", lw=1)
        for i, m in enumerate(methods):
            ax.text(x + 0.12, y + h - 0.8 - i * 0.42, "+ " + m, ha="left", color=INK, fontsize=8)
    ax.text(5, 0.55, "统一基于 SQLAlchemy Session，面向 7 张表提供持久化方法",
            ha="center", color=GRAY, fontsize=10)
    save(fig, "fig07_dao_class.png")


# ---- 图: Service 类图 ----
def fig_service():
    fig, ax = plt.subplots(figsize=(10, 4.4)); ax.set_xlim(0, 10); ax.set_ylim(0, 4.4); ax.axis("off")
    ax.text(5, 4.2, "业务逻辑层（Service）类图", ha="center", color=INK, fontsize=12, fontweight="bold")
    svc = [
        ("TaskOrchestrator", ["process_query()", "evaluate_step()", "advance() / replan()"], PURPLE),
        ("MultiProviderClient", ["chat() / vision()", "parse_points()"], BLUE),
        ("BlueprintEngine", ["advance/rollback", "skip/terminate"], AMBER),
        ("RiskScorer / Safety", ["classify()", "score(1-5)"], RED),
        ("SetFitClassifier", ["classify()", "9 类意图"], GREEN),
        ("OmniParserClient", ["parse()", "ParseResult"], CYAN),
    ]
    xs = [0.2, 3.5, 6.8, 0.2, 3.5, 6.8]; ys = [2.3, 2.3, 2.3, 0.4, 0.4, 0.4]
    w = 3.0; h = 1.6
    for (name, methods, c), x, y in zip(svc, xs, ys):
        box(ax, x, y, w, h, "", c, r=0.03)
        ax.text(x + w / 2, y + h - 0.25, name, ha="center", color=c, fontsize=9.5, fontweight="bold")
        ax.plot([x + 0.1, x + w - 0.1], [y + h - 0.45, y + h - 0.45], color="#d1d5db", lw=1)
        for i, m in enumerate(methods):
            ax.text(x + 0.15, y + h - 0.75 - i * 0.38, "+ " + m, ha="left", color=INK, fontsize=8)
    save(fig, "fig08_service_class.png")


# ---- 图: 数据库 ER ----
def fig_er():
    fig, ax = plt.subplots(figsize=(10, 6.2)); ax.set_xlim(0, 10); ax.set_ylim(0, 6.2); ax.axis("off")
    ax.text(5, 6.0, "图  数据库 ER 结构（7 表）", ha="center", color=INK, fontsize=12, fontweight="bold")

    def tbl(x, y, name, cols, c):
        h = 0.34 * (len(cols) + 1)
        box(ax, x, y - h, 2.3, h, "", c, r=0.02)
        ax.add_patch(FancyBboxPatch((x, y - 0.34), 2.3, 0.34,
                     boxstyle="round,pad=0,rounding_size=0.02", fc=c, ec=c))
        ax.text(x + 1.15, y - 0.17, name, ha="center", va="center", color="white",
                fontsize=9, fontweight="bold")
        for i, col in enumerate(cols):
            ax.text(x + 0.12, y - 0.5 - i * 0.34, col, ha="left", va="center",
                    color=INK, fontsize=7.6)
        return (x, y, x + 2.3, y - h)

    u = tbl(0.3, 5.5, "t_users", ["user_id PK", "username UK", "role", "preferences"], BLUE)
    t = tbl(3.7, 5.7, "t_transactions", ["task_id PK", "user_id FK", "intent_category",
            "plan_type L2/L3", "result", "redline_triggered"], AMBER)
    s = tbl(7.4, 5.7, "t_step_logs", ["log_id PK", "task_id FK", "action",
            "target_bbox", "status", "fingerprint"], PURPLE)
    fb = tbl(3.7, 2.3, "t_feedback", ["feedback_id PK", "task_id FK", "feedback_type"], GREEN)
    fa = tbl(7.4, 2.5, "t_failures", ["failure_id PK", "task_id", "failure_type", "llm_snapshot"], RED)
    cfg = tbl(0.3, 2.6, "t_system_configs", ["config_id PK", "config_key UK", "config_value"], CYAN)
    rl = tbl(0.3, 1.1, "t_redline_logs", ["log_id PK", "category", "action"], GRAY)
    # 关系连线
    arw(ax, 2.6, 5.1, 3.7, 5.2, LINE, 1.2); ax.text(3.0, 5.35, "1..*", color=GRAY, fontsize=7)
    arw(ax, 6.0, 5.3, 7.4, 5.3, LINE, 1.2); ax.text(6.6, 5.45, "1..*", color=GRAY, fontsize=7)
    arw(ax, 4.8, 4.0, 4.8, 2.3, LINE, 1.2); ax.text(4.95, 3.1, "1..*", color=GRAY, fontsize=7)
    arw(ax, 6.0, 4.3, 7.6, 3.0, LINE, 1.2); ax.text(6.9, 3.7, "1..*", color=GRAY, fontsize=7)
    save(fig, "fig09_er.png")


# ---- 图: 部署拓扑 ----
def fig_deploy():
    fig, ax = plt.subplots(figsize=(10, 4.8)); ax.set_xlim(0, 10); ax.set_ylim(0, 4.8); ax.axis("off")
    ax.text(5, 4.6, "图  网络部署拓扑", ha="center", color=INK, fontsize=12, fontweight="bold")
    box(ax, 0.3, 2.3, 5.7, 1.9, "", BLUE, fc="#eff6ff")
    ax.text(3.15, 3.95, "本地 PC（Windows）", ha="center", color=BLUE, fontsize=10.5, fontweight="bold")
    box(ax, 0.6, 2.6, 1.6, 0.9, "B端 GUI\nPyQt5", BLUE, fs=9)
    box(ax, 2.35, 2.6, 1.6, 0.9, "A端\nFastAPI:8010", AMBER, fs=9)
    box(ax, 4.1, 2.6, 1.6, 0.9, "Web:5173\nVue3", GREEN, fs=9)
    box(ax, 3.4, 0.3, 5.9, 1.4, "", RED, fc="#fef2f2")
    ax.text(6.35, 1.45, "远程服务器（校园 GPU / 云端）", ha="center", color=RED, fontsize=10.5, fontweight="bold")
    box(ax, 3.7, 0.5, 2.4, 0.75, "OmniParser :9800 (GPU)", PURPLE, fs=8.5)
    box(ax, 6.4, 0.5, 2.6, 0.75, "多模态 LLM API (云端)", CYAN, fs=8.5)
    arw(ax, 1.4, 2.6, 4.8, 1.25, LINE); ax.text(2.6, 1.95, "SSH 隧道 :9800", color=GRAY, fontsize=8.5)
    arw(ax, 3.15, 2.6, 7.6, 1.25, LINE); ax.text(6.0, 2.2, "HTTPS", color=GRAY, fontsize=8.5)
    save(fig, "fig10_deploy.png")


if __name__ == "__main__":
    fig_overview(); fig_arch(); fig_flow(); fig_omni(); fig_safety()
    fig_state(); fig_dao(); fig_service(); fig_er(); fig_deploy()
    print("ALL DONE")
