# -*- coding: utf-8 -*-
"""生成《HAJIMI 详细设计》所需的非截图类图表 -> images/*.png（白底，适合打印）。"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

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
    fig, ax = plt.subplots(figsize=(11, 4.6)); ax.set_xlim(0, 11); ax.set_ylim(0, 4.6); ax.axis("off")
    ax.text(5.5, 4.35, "图  蓝图执行状态机", ha="center", color=INK, fontsize=13, fontweight="bold")

    bw, bh = 2.0, 0.8
    # 主流程（上排）
    y1 = 2.7
    gen = (0.5, y1); exe = (4.0, y1); comp = (8.5, y1)
    # 分支（下排）
    y2 = 0.7
    susp = (4.0, y2); term = (8.5, y2)
    box(ax, *gen, bw, bh, "generated\n已生成", BLUE, fs=10.5)
    box(ax, *exe, bw, bh, "executing\n执行中", AMBER, fs=10.5)
    box(ax, *comp, bw, bh, "completed\n已完成", GREEN, fs=10.5)
    box(ax, *susp, bw, bh, "suspended\n已挂起", RED, fs=10.5)
    box(ax, *term, bw, bh, "terminated\n已终止", GRAY, fs=10.5)

    def cx(b): return b[0] + bw / 2
    def cy(b): return b[1] + bh / 2

    # 起始点
    ax.add_patch(Circle((0.2, cy(gen)), 0.08, color=INK))
    arw(ax, 0.28, cy(gen), gen[0], cy(gen), INK, 1.6)
    # generated -> executing
    arw(ax, gen[0] + bw, cy(gen), exe[0], cy(gen), LINE, 1.8)
    ax.text((gen[0] + bw + exe[0]) / 2, cy(gen) + 0.18, "SSE 开始", color=GRAY, fontsize=9, ha="center")
    # executing -> completed
    arw(ax, exe[0] + bw, cy(exe), comp[0], cy(comp), GREEN, 1.8)
    ax.text((exe[0] + bw + comp[0]) / 2, cy(exe) + 0.18, "全部步骤完成", color=GREEN, fontsize=9, ha="center")
    # executing -> suspended（下行，左侧箭头）
    arw(ax, cx(exe) - 0.25, exe[1], cx(susp) - 0.25, susp[1] + bh, RED, 1.6)
    ax.text(cx(exe) - 1.7, (exe[1] + susp[1] + bh) / 2, "风险≥4 / 用户取消", color=RED, fontsize=9, ha="center")
    # suspended -> executing（上行，右侧箭头）
    arw(ax, cx(susp) + 0.25, susp[1] + bh, cx(exe) + 0.25, exe[1], LINE, 1.6)
    ax.text(cx(exe) + 1.3, (exe[1] + susp[1] + bh) / 2, "确认继续", color=GRAY, fontsize=9, ha="center")
    # suspended -> terminated
    arw(ax, susp[0] + bw, cy(susp), term[0], cy(term), GRAY, 1.6)
    ax.text((susp[0] + bw + term[0]) / 2, cy(susp) + 0.18, "用户终止", color=GRAY, fontsize=9, ha="center")
    # executing 自环：回退一步
    ax.add_patch(FancyArrowPatch((cx(exe) - 0.4, exe[1] + bh), (cx(exe) + 0.4, exe[1] + bh),
                 connectionstyle="arc3,rad=-1.4", arrowstyle="-|>", mutation_scale=13, color=PURPLE, lw=1.4))
    ax.text(cx(exe), exe[1] + bh + 0.62, "回退/跳过一步", color=PURPLE, fontsize=9, ha="center")
    # 终止点
    for b, c in [(comp, GREEN), (term, GRAY)]:
        ax.add_patch(Circle((b[0] + bw + 0.25, cy(b)), 0.13, fill=False, ec=c, lw=1.8))
        ax.add_patch(Circle((b[0] + bw + 0.25, cy(b)), 0.06, color=c))
        arw(ax, b[0] + bw, cy(b), b[0] + bw + 0.12, cy(b), c, 1.6)
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
    fig, ax = plt.subplots(figsize=(12, 8)); ax.set_xlim(0, 12); ax.set_ylim(0, 8); ax.axis("off")
    ax.text(6, 7.75, "图  数据库 ER 结构（7 表）", ha="center", color=INK, fontsize=13, fontweight="bold")

    RH = 0.32     # 行高
    HH = 0.38     # 表头高
    TW = 3.0      # 表宽
    X1, X2, X3 = 0.5, 4.3, 8.1   # 三列 x

    def table(x, y_top, name, cols, c):
        """以左上角 (x, y_top) 绘制表，向下延伸。返回边界字典。"""
        body_h = RH * len(cols)
        # 表头
        ax.add_patch(FancyBboxPatch((x, y_top - HH), TW, HH,
                     boxstyle="round,pad=0.01,rounding_size=0.03", fc=c, ec=c, lw=0))
        ax.text(x + TW / 2, y_top - HH / 2, name, ha="center", va="center",
                color="white", fontsize=9.5, fontweight="bold")
        # 表体
        ax.add_patch(FancyBboxPatch((x, y_top - HH - body_h), TW, body_h,
                     boxstyle="square,pad=0", fc="white", ec=c, lw=1.3))
        for i, col in enumerate(cols):
            ax.text(x + 0.16, y_top - HH - (i + 0.5) * RH, col, ha="left", va="center",
                    color=INK, fontsize=8)
        return {"l": x, "r": x + TW, "top": y_top, "bot": y_top - HH - body_h,
                "cxx": x + TW / 2, "hmy": y_top - HH / 2}

    # 第一行：用户 / 事务 / 步骤
    u = table(X1, 7.3, "t_users",
              ["user_id PK", "username UK", "password_hash", "role", "preferences"], BLUE)
    t = table(X2, 7.3, "t_transactions",
              ["task_id PK", "user_id FK", "intent_category", "plan_type", "result", "redline_triggered"], AMBER)
    s = table(X3, 7.3, "t_step_logs",
              ["log_id PK", "task_id FK", "step_index", "action", "target_bbox", "status"], PURPLE)

    # 第二行：配置 / 反馈 / 失败
    cfg = table(X1, 4.5, "t_system_configs",
                ["config_id PK", "config_key UK", "config_value", "description", "updated_by FK"], CYAN)
    fb = table(X2, 4.5, "t_feedback",
               ["feedback_id PK", "task_id FK", "user_id FK", "feedback_type", "comment"], GREEN)
    fa = table(X3, 4.5, "t_failures",
               ["failure_id PK", "task_id", "failure_type", "step_index", "llm_snapshot", "error_detail"], RED)

    # 第三行：红线（独立表）
    rl = table(X2, 2.35, "t_redline_logs",
               ["log_id PK", "query", "category", "action", "message"], "#63666a")

    # ----- 关系连线（短直线/垂直线，互不交叉） -----
    def rel_h(a, b, label):  # 水平：a.right → b.left（表头中线）
        ax.plot([a["r"], b["l"]], [a["hmy"], b["hmy"]], color=LINE, lw=1.5)
        ax.text((a["r"] + b["l"]) / 2, a["hmy"] + 0.16, label, color=GRAY, fontsize=8, ha="center")

    def rel_v(a, b, label, dx=0.0):  # 垂直：a.bot → b.top（同列）
        x = a["cxx"] + dx
        ax.plot([x, x], [a["bot"], b["top"]], color=LINE, lw=1.5)
        ax.text(x + 0.1, (a["bot"] + b["top"]) / 2, label, color=GRAY, fontsize=8, va="center")

    rel_h(u, t, "1 : *")        # 用户→事务
    rel_h(t, s, "1 : *")        # 事务→步骤
    rel_v(t, fb, "1 : *")       # 事务→反馈
    rel_v(u, cfg, "updated_by") # 用户→配置
    # 事务→失败（斜连，任务级关联）
    ax.plot([t["r"] - 0.4, fa["cxx"]], [t["bot"], fa["top"]], color=LINE, lw=1.2, ls="--")
    ax.text(fa["cxx"] + 0.15, (t["bot"] + fa["top"]) / 2, "任务级", color=GRAY, fontsize=7.5, va="center")

    # 独立表标注
    ax.text(rl["cxx"], rl["bot"] - 0.3, "独立表（无外键约束）", color=GRAY, fontsize=8, ha="center")

    # 图例（四域分区）——置于右下空白区，竖排
    ax.text(8.2, 2.05, "四域分区", color=INK, fontsize=9, fontweight="bold")
    leg = [("业务域", AMBER), ("审计域", GREEN), ("管理域", CYAN), ("安全域", "#63666a")]
    for i, (txt, col) in enumerate(leg):
        yy = 1.65 - i * 0.34
        ax.add_patch(FancyBboxPatch((8.2, yy - 0.11), 0.3, 0.22, boxstyle="square,pad=0", fc=col, ec=col))
        ax.text(8.62, yy, txt, color=INK, fontsize=8, va="center")

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
