# -*- coding: utf-8 -*-
"""
重建《HAJIMI 详细设计》4 份 docx —— 完全遵循模板
`03-《基于YOLOv5的小目标无人机检测系统》-AI样例_详细设计文档.docx` 的
七部分结构与样式（Title / Heading 3/4/5 / Normal Indent / Table Grid）。

做法：以模板文件为基底载入（继承其全部样式定义），清空正文后按 HAJIMI 内容重写。
图片：非截图类图表插入 images/*.png；界面截图类保留“图注 + 占位说明”。
"""
import os
import copy
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

BASE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(BASE, "..", "模版",
                   "03-《基于YOLOv5的小目标无人机检测系统》-AI样例_详细设计文档.docx")
IMG = os.path.join(BASE, "images")

CN = "宋体"


def new_doc():
    """以模板为基底，清空正文，返回可写文档（保留样式定义）。"""
    d = docx.Document(TPL)
    body = d.element.body
    for child in list(body.iterchildren()):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)
    return d


def _set_cn(run, size=None, bold=None, color=None):
    run.font.name = CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), CN)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def title(d, text):
    p = d.add_paragraph(text, style="Title")
    return p


def h3(d, text):
    return d.add_paragraph(text, style="Heading 3")


def h4(d, text):
    return d.add_paragraph(text, style="Heading 4")


def h5(d, text):
    return d.add_paragraph(text, style="Heading 5")


def para(d, text):
    """正文段落：Normal Indent（首行缩进 2 字符，12pt 宋体）。"""
    p = d.add_paragraph(style="Normal Indent")
    r = p.add_run(text)
    _set_cn(r, size=12)
    # 首行缩进 2 字符
    p.paragraph_format.first_line_indent = Pt(24)
    p.paragraph_format.space_after = Pt(4)
    return p


def bullet(d, text):
    """无缩进列表项（用于分点罗列）。"""
    p = d.add_paragraph(style="Normal Indent")
    r = p.add_run(text)
    _set_cn(r, size=12)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Pt(18)
    p.paragraph_format.space_after = Pt(2)
    return p


def caption(d, text):
    """图/表题注：居中，小字。"""
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    _set_cn(r, size=10.5, bold=True, color=RGBColor(0x40, 0x40, 0x40))
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    return p


def figure(d, img_name, cap, width=5.9):
    """插入生成图 + 题注；图不存在则插入占位说明。"""
    path = os.path.join(IMG, img_name) if img_name else None
    if path and os.path.exists(path):
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(path, width=Inches(width))
    else:
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("〔此处为界面截图，留待运行后补入〕")
        _set_cn(r, size=11, color=RGBColor(0x90, 0x90, 0x90))
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
    caption(d, cap)


def table(d, rows, header=True, widths=None):
    """Table Grid 表格；rows 为二维列表；首行可加粗。"""
    ncol = max(len(r) for r in rows)
    t = d.add_table(rows=0, cols=ncol)
    t.style = "Table Grid"
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci in range(ncol):
            val = row[ci] if ci < len(row) else ""
            cell = cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            r = p.add_run(str(val))
            _set_cn(r, size=10.5, bold=(header and ri == 0))
            p.paragraph_format.space_after = Pt(0)
    if widths:
        for row in t.rows:
            for ci, w in enumerate(widths):
                if ci < len(row.cells):
                    row.cells[ci].width = Inches(w)
    return t


def spacer(d):
    d.add_paragraph()


# 事务定义模板句（模板 DAO/Service 接口首格固定用语）
TX = ("事务定义 @Transactional(propagation=REQUIRED)，声明在接口名上方，表示本接口内"
      "所有方法若未单独定义事务类型，均以该类型执行：若当前无事务则新建，"
      "若已处于事务中则加入该事务。")


# ══════════════════════════════════════════════════════════════════
# 文档 01 —— 引言与总体设计（第一~三部分）
# ══════════════════════════════════════════════════════════════════
def build_01():
    d = new_doc()
    caption(d, "《HAJIMI 自动操作助手》 详细设计文档  V2.2")
    spacer(d)

    title(d, "第一部分 引言")

    h3(d, "一、编写目的")
    para(d, "编写本设计文档的目的，是准确阐述 HAJIMI 自动操作助手的具体实现思路与方法，"
            "即系统的详细架构与实现逻辑，主要包括程序系统的层次结构以及各层次中每个模块的"
            "设计考虑。文档在概要设计的基础上进一步细化，为后续的编码、联调、测试与运行维护"
            "提供依据。预期读者为项目全体成员，包括开发人员、集成人员、测试人员与运行维护人员。")

    h3(d, "二、项目背景")
    bullet(d, "系统名称：HAJIMI 自动操作助手（模糊视觉辅助问答系统）")
    bullet(d, "任务提出者：2026 年重庆大学赋能实训项目组（第 32 组）")
    bullet(d, "开发者：潘振喆（A 端 后端/AI）、杨名（B 端 前端/桌面）、涂浚稷（C 端 集成/语音/管理端）")
    bullet(d, "用户与运行环境：面向个人桌面用户，运行于 Windows 平台；算法推理依托远程 GPU 服务器。")

    h3(d, "三、术语与定义")
    h4(d, "1、技术类")
    para(d, "PyQt5：Qt 框架的 Python 语言绑定，用于构建跨平台桌面图形界面。本系统的悬浮面板、"
            "透明标注覆盖层等桌面端界面均基于 PyQt5 实现。")
    para(d, "FastAPI：一个基于 Python 类型注解的高性能 Web 框架，内置数据校验与自动接口文档。"
            "本系统的服务端（A 端）采用 FastAPI 对外提供 REST 与 SSE 接口。")
    para(d, "OmniParser：微软开源的界面解析视觉模型，联合 YOLO 图标检测、Florence 语义描述与"
            "OCR 文本识别，能够将一张屏幕截图解析为带坐标的可交互元素集合，并生成 SoM（Set-of-Mark）标注图。")
    para(d, "多模态 LLM：可同时理解图像与文本的大语言模型（如 Qwen、GPT、DeepSeek 等）。"
            "本系统用其结合截图与元素列表进行操作步骤规划与目标坐标定位。")
    para(d, "SSE：Server-Sent Events，一种基于 HTTP 的服务器单向流式推送技术。本系统用其将"
            "任务执行进度实时推送至桌面端。")
    para(d, "pyautogui：跨平台的桌面自动化库，可模拟鼠标点击、键盘输入等系统级操作，是本系统"
            "自动执行能力的落地手段。")
    para(d, "mss：高性能屏幕截图库，用于按物理像素快速抓取全屏图像。")

    h4(d, "2、业务类")
    para(d, "屏幕感知：系统对当前屏幕内容进行截取与解析，识别出界面上有哪些可点击、可输入的"
            "元素及其位置的过程。")
    para(d, "意图理解：将用户的自然语言指令归类到既定意图域，并对指令中的模糊指代进行消解，"
            "从而明确用户真实目标的过程。本系统划分了通用操作指引、元素认知、错误诊断等九类意图域。")
    para(d, "指代消解：对“那个按钮”“右上角”等模糊表述结合屏幕元素进行定位的处理。")
    para(d, "自动执行：系统在明确目标与步骤后，直接代替用户完成点击、输入、双击、快捷键、拖拽、"
            "滚动等操作，而非仅给出文字或箭头指引。")
    para(d, "风险评分：对每一条待执行的指令或步骤按危险程度给出 1—5 级评分，作为是否放行、"
            "是否需要用户确认的依据。")
    para(d, "红线检测：对涉及物理操作、隐私侵入等的高危指令进行关键词与正则匹配，命中即直接拒绝。")
    para(d, "SoM 标注：Set-of-Mark，在截图上为每个被识别元素叠加编号标记，便于 LLM 与用户按编号引用。")

    h3(d, "四、参考资料")
    para(d, "列出有关的参考资料如下：")
    bullet(d, "《智能桌面指引系统——里程碑计划》")
    bullet(d, "《智能桌面指引助手 项目需求说明书 V2.5》")
    bullet(d, "《HAJIMI 概要设计文档 V3.8》")
    bullet(d, "《HAJIMI 图表与 UML 描述 V2.0》（UML_diagrams）")
    bullet(d, "《HAJIMI 统一接口文档》及 A-B / A-C / B-C 接口契约")

    spacer(d)
    title(d, "第二部分 项目概述")
    para(d, "随着桌面软件功能日益丰富，界面层级与操作路径也越来越复杂。对于初次使用某款软件的"
            "新手用户、视力衰退的老年用户以及依赖读屏工具的视障用户而言，“知道要做什么、却找不到"
            "在哪里操作”成为普遍困扰。传统的应对方式是查阅教程、按 F1 求助或在多个窗口间反复切换，"
            "既费时又容易出错，教程与真实界面对不上的情况也屡见不鲜。因此，构建一套能够理解屏幕、"
            "理解意图并代为操作的桌面助手，具有明确的现实意义。")
    para(d, "基于上述背景，本项目构建 HAJIMI 自动操作助手。系统以多模态视觉理解为核心，主要包含"
            "两大能力：一是屏幕理解与操作规划，用户通过语音或文本下达目标后，系统截取屏幕、解析"
            "界面元素、结合大模型规划出带坐标的操作步骤；二是安全的自动执行，系统在安全边界内直接"
            "完成点击、输入、双击等操作，并将执行过程实时反馈至界面。除核心功能外，系统还提供意图"
            "分类、复杂度分级的快慢双路径、执行审计与可视化管理面板等辅助能力。")
    para(d, "构建 HAJIMI 的目标，是通过“看得懂屏幕、听得懂指令、帮得上忙”的方式显著降低桌面软件的"
            "操作门槛，同时借助风险评分与红线检测在自动执行的便利性与操作安全性之间取得平衡，"
            "满足快速、准确、可控的使用要求。")
    figure(d, "fig01_overview.png", "图1  HAJIMI 项目核心概述")

    spacer(d)
    title(d, "第三部分 总体设计")

    h3(d, "一、技术架构设计")
    figure(d, "fig02_architecture.png", "图2  技术架构设计图")
    para(d, "系统整体采用分层的客户端—服务端（C/S）架构，自上而下划分为表示层、应用层、服务层与"
            "数据层四层，并在运行时表现为 B 端桌面客户端、A 端服务端、AI 服务三个相互协作的进程。"
            "这一划分借鉴了经典的分层设计思想——将界面显示、业务处理与数据存取相互隔离，使得在"
            "改进界面或调整交互时无需改动底层逻辑，各层职责清晰、便于独立演进与测试。")
    para(d, "在表示层，系统构建了两类前端界面：一是由 PyQt5 实现的桌面客户端，包含常驻桌面的悬浮"
            "面板与全屏透明标注覆盖层；二是由 Vue3 实现的 Web 管理面板，供运营与开发人员查看统计"
            "与配置。表示层通过 HTTP/SSE 访问服务层提供的接口以获取数据并呈现，同时对用户的非法"
            "操作进行必要的前端约束。")
    para(d, "在应用层，系统封装了真正“动手”的执行引擎（基于 pyautogui 完成点击、输入等系统级操作）、"
            "维护任务推进的步骤状态机，以及负责脱敏与批量上报的审计代理、负责下发变更的配置轮询等模块。")
    para(d, "在服务层，A 端以 FastAPI 对外提供 26 个接口，内部完成 LLM 操作规划、风险评分与红线检测"
            "等核心业务逻辑，是连接前端与 AI 能力的中枢。")
    para(d, "在数据层，系统以 SQLite 持久化用户、任务、步骤、反馈、失败、配置与红线七类数据；"
            "屏幕解析能力由部署在远程 GPU 上的 OmniParser 提供，操作规划能力由云端多模态 LLM 提供。")

    h3(d, "二、核心控制流程")
    h4(d, "1、核心控制流程图")
    figure(d, "fig03_controlflow.png", "图3  核心控制流程图")
    h4(d, "2、核心控制流程说明")
    para(d, "结合上图，针对一次完整的自动操作请求，按消息的请求/回复顺序作如下说明。")
    table(d, [
        ["编号", "消息名称", "消息说明"],
        ["1", "Query", "用户以语音或文本方式向 B 端下达操作目标"],
        ["2", "Capture", "B 端通过 mss 截取全屏图像并做本地红线预检"],
        ["3", "Execute", "B 端将指令与截图 POST 至 A 端 /api/demo/execute"],
        ["4", "Parse", "A 端调用 OmniParser 解析元素并生成 SoM 标注图"],
        ["5", "Plan", "A 端执行风险评分、红线检测，并由 LLM 规划带坐标的步骤"],
        ["6", "Stream", "A 端通过 SSE /stream 将步骤与进度实时推回 B 端"],
        ["7", "Act", "B 端执行引擎依步骤调用 pyautogui 完成点击/输入等操作"],
        ["8", "Audit", "B 端将执行结果 POST 至 /api/audit/report 归档"],
    ])

    out = os.path.join(BASE, "01-详细设计-引言与总体设计.docx")
    d.save(out)
    print("saved", os.path.basename(out))


# ══════════════════════════════════════════════════════════════════
# 文档 02 —— 界面和业务界面设计（第四部分）
# ══════════════════════════════════════════════════════════════════
def build_02():
    d = new_doc()
    title(d, "第四部分 界面和业务界面设计")
    para(d, "系统采用 PyQt5 桌面端 + Web 端两种界面模式。其中 PyQt5 是 Qt 框架的 Python 实现，"
            "提供了完善的窗口控件集合，适合构建常驻桌面、需与系统深度交互的可视化界面；Web 端主要"
            "采用 Vue3 进行开发，它是一套构建用户界面的渐进式框架，数据双向绑定、组件化程度高、"
            "接口简洁，适合构建面向运营与开发的管理后台。")
    para(d, "PyQt5 桌面端主要用于终端用户的日常使用场景：以悬浮面板承载指令输入与步骤反馈，"
            "以透明覆盖层在真实界面上叠加标注。Web 端主要用于管理场景，包括登录、总览仪表盘、"
            "失败归因、数据流监控、系统配置与健康监控等页面。")

    h3(d, "一、Web 端页面布局设计")
    h4(d, "1、登录界面")
    para(d, "登录界面分为上中下三个部分：最上方是系统标题与 Logo；中间是用户名与密码的表单输入框，"
            "并包含登录按钮；最下方是版本与版权信息。用户提交后由后端签发 JWT，校验通过即进入总览页。")
    h4(d, "2、总览仪表盘")
    para(d, "总览页用于呈现系统运行的整体态势，顶部为一行关键指标（KPI）卡片，展示任务总量、"
            "成功率、平均耗时、红线拦截数与反馈量；下方为图表区，包含反馈分布饼图、L2/L3 复杂度"
            "占比饼图与近 24 小时任务趋势折线图，帮助管理者快速掌握系统健康度。")
    h4(d, "3、失败归因页")
    para(d, "失败归因页用于定位问题任务。页面上部为失败类型柱状图与失败趋势图，中部为失败任务列表，"
            "点击任意条目会弹出详情抽屉（Drawer），展示该任务的步骤日志与当时的 LLM 快照，"
            "便于开发人员复盘失败原因。")
    h4(d, "4、系统配置页")
    para(d, "系统配置页用于查看与热部署运行参数。页面以分区表单组织各项配置，支持 JSON 方式编辑，"
            "保存后即时下发至服务端并记录部署日志，无需重启服务即可生效。")

    h3(d, "二、业务界面风格展示")
    h4(d, "1、PyQt5 桌面端界面")
    h5(d, "a、主界面（悬浮面板）")
    para(d, "主界面为常驻桌面右下角的悬浮面板（约 480×520 像素）。最上方为标题栏，含 Logo、风格切换"
            "与折叠/关闭按钮；中部自上而下依次为指令输入栏、任务进度标题、步骤卡片列表，以及底部的"
            "截图预览与执行日志分栏；最下方为开始、暂停、恢复、停止四枚控制按钮。步骤卡片以图标与"
            "颜色区分“待执行、执行中、已完成、失败、被拦截、跳过”六种状态，并在每步旁标注操作类型"
            "与风险评分圆点。")
    figure(d, None, "图4  B 端主界面（悬浮面板）")
    h5(d, "b、紧凑模式与标注覆盖层")
    para(d, "紧凑模式将面板收拢为一条约 320×52 像素的浮动条，仅保留输入框、执行按钮与状态图标，"
            "便于在不遮挡工作区的情况下随时调用。标注覆盖层是一层全屏透明窗口，用红色箭头、虚线"
            "高亮框与白底红字编号标签，将“下一步应操作的位置”直接叠加绘制在真实界面之上。")
    figure(d, None, "图5  紧凑模式与屏幕标注覆盖层")

    h4(d, "2、Web 端界面")
    h5(d, "a、总览页面")
    para(d, "总览页面以卡片与图表组合呈现核心运营指标，配色克制、信息密度适中，支持时间范围切换。")
    figure(d, None, "图6  Web 端总览页面")
    h5(d, "b、失败归因页面")
    para(d, "失败归因页面通过“图表概览—列表下钻—详情抽屉”的三段式结构，引导使用者由宏观到微观定位问题。")
    figure(d, None, "图7  Web 端失败归因页面")
    h5(d, "c、数据流监控页面")
    para(d, "数据流页面以桑基图展示各链路的调用流向，以双轴折线展示 QPS 与成功率，以饼图展示版本分布。")
    figure(d, None, "图8  Web 端数据流监控页面")
    h5(d, "d、健康监控页面")
    para(d, "健康监控页面以状态灯呈现各组件在线情况，列出资源占用与告警信息，并支持导出 CSV。")
    figure(d, None, "图9  Web 端健康监控页面")

    out = os.path.join(BASE, "02-详细设计-界面设计.docx")
    d.save(out)
    print("saved", os.path.basename(out))


# ══════════════════════════════════════════════════════════════════
# 文档 03 —— 单元模块设计（第五部分）
# ══════════════════════════════════════════════════════════════════
def build_03():
    d = new_doc()
    title(d, "第五部分 单元模块设计")

    h3(d, "一、屏幕感知与元素解析")
    h4(d, "1、屏幕采集设计")
    para(d, "屏幕采集是整条链路的输入源。桌面端通过 mss 库按物理像素抓取全屏图像，转换为 PIL 图像"
            "对象后编码为 base64 数据 URI 传输。为兼顾性能，采集结果带有约 900 毫秒的短时缓存，"
            "并在采集环节做屏幕指纹计算，用于判断界面是否发生实质变化，避免重复解析。")
    h4(d, "2、元素检测与解析")
    para(d, "元素解析由部署在远程 GPU 上的 OmniParser 完成，采用三模型联合推理：YOLO 负责图标类"
            "元素的检测，Florence 负责为元素生成语义描述，OCR（PaddleOCR）负责文本识别。三者的"
            "结果融合后，输出一份带归一化坐标的可交互元素列表，同时生成叠加了编号标记的 SoM 标注图。")
    figure(d, "fig04_omniparser.png", "图10  OmniParser 三模型联合推理流程")
    h4(d, "3、坐标映射与标注")
    para(d, "由于截图为物理像素、显示存在缩放（DPR），元素坐标统一采用 0—1000 的归一化比例表示，"
            "再由坐标映射模块结合屏幕分辨率与缩放比换算为绝对像素，最终在透明覆盖层上以逻辑像素"
            "绘制箭头、高亮框与编号，保证标注位置与真实控件对齐。")

    h3(d, "二、人工智能技术方案")
    h4(d, "1、技术路线选择")
    para(d, "面向“理解任意桌面界面并规划操作”的目标，存在两条主要技术路线：其一是训练端到端的"
            "坐标定位模型（如 SeeClick 一类），直接由截图与指令回归出点击坐标；其二是“视觉解析 + "
            "多模态大模型规划”的组合路线，先由 OmniParser 将界面结构化为元素列表，再由多模态 LLM"
            "结合截图与元素列表规划步骤并引用元素坐标。前者部署轻，但对未见界面的泛化与可解释性"
            "较弱、纠错困难；后者依赖外部模型，但泛化能力强、结果可按元素编号追溯、便于加入安全"
            "校验。综合权衡，本系统采用第二条路线。")
    h4(d, "2、规划与执行方案")
    para(d, "为兼顾响应速度与处理能力，系统按复杂度分级采用快慢双路径：对结构清晰、可套用模板的"
            "简单任务走 L2 快路径，以本地规则直接给出步骤，通常在 3 秒内完成；对复杂任务走 L3 慢"
            "路径，调用多模态 LLM 规划，耗时约 5—10 秒。任务执行由蓝图状态机驱动，在“生成—执行—"
            "完成/挂起/回退”之间转移，支持推进、回退、跳过与终止。")
    figure(d, "fig06_state.png", "图11  蓝图执行状态机")
    h4(d, "3、安全方案")
    para(d, "安全是自动执行的前提。系统采用绿/黄/红三层分类：命中红线（如涉及物理操作、隐私侵入）"
            "的指令直接拒绝；黄线指令给出 1—5 级风险评分，评分达到高危阈值（≥4）时自动挂起并等待"
            "用户确认；绿区指令方可直接执行。分类以关键词与正则规则为主，并设有绿区豁免规则以减少误判。")
    figure(d, "fig05_safety.png", "图12  安全分类与风险评分流程")

    h3(d, "三、单元 UI")
    para(d, "桌面端界面基于 PyQt5 构建。PyQt5 提供了 QObject、QWidget、QMainWindow、QDialog 等庞大"
            "的控件类体系，可跨平台运行。本系统的主要界面控件包括：标题栏 TitleBar、指令输入框"
            "QueryInput、执行按钮 ExecuteButton、步骤列表 StepList、截图预览 ScreenshotPreview、"
            "执行日志 LogOutput，以及控制栏中的开始/暂停/恢复/停止四枚按钮。透明覆盖层由独立的"
            "OverlayAnnoWindow 承载，负责绘制箭头、高亮框与编号标签。上述控件通过 PyQt 的信号—槽"
            "机制与业务控制器解耦通信。")

    h3(d, "四、数据访问层设计")
    h4(d, "1、类图设计")
    para(d, "数据访问层（Repository 层）统一基于 SQLAlchemy 的 Session 对象操作数据库，面向七张表"
            "封装持久化方法，向上为业务逻辑层提供简洁的数据接口。其类图如下所示。")
    figure(d, "fig07_dao_class.png", "图13  数据访问层类图")
    h4(d, "2、类的详细设计描述")
    h5(d, "2.1 TaskRepository 接口设计")
    para(d, "详细描述：")
    table(d, [
        [f"TaskRepository —— 任务事务持久化。{TX}"],
        ["create_from_response(resp, user_id)：由处理响应落库生成一条任务事务与其步骤日志"],
        ["update_result(task_id, result, duration_ms)：更新任务的最终结果与耗时"],
        ["get_stats_overview()：聚合统计任务总量、成功率、平均耗时等总览指标（只读）"],
    ], header=False)
    h5(d, "2.2 RedlineRepository 接口设计")
    para(d, "详细描述：")
    table(d, [
        [f"RedlineRepository —— 红线拦截日志持久化。{TX}"],
        ["log(query, category, action, message)：记录一次红线拦截事件"],
        ["get_stats()：按类别统计红线拦截分布（只读）"],
    ], header=False)
    h5(d, "2.3 FeedbackRepository 接口设计")
    para(d, "详细描述：")
    table(d, [
        [f"FeedbackRepository —— 用户反馈持久化。{TX}"],
        ["create(task_id, feedback_type, comment)：新增一条用户反馈（useful/useless/neutral）"],
    ], header=False)
    h5(d, "2.4 FailureRepository 接口设计")
    para(d, "详细描述：")
    table(d, [
        [f"FailureRepository —— 失败归因持久化。{TX}"],
        ["create(task_id, failure_type, step_index, llm_snapshot, error_detail)：记录失败详情与 LLM 快照"],
    ], header=False)
    h5(d, "2.5 ConfigRepository 接口设计")
    para(d, "详细描述：")
    table(d, [
        [f"ConfigRepository —— 系统配置持久化。{TX}"],
        ["get_all()：读取全部配置项（只读）"],
        ["get(key)：按键读取单项配置（只读）"],
        ["set(key, value, description)：写入或更新单项配置（热部署）"],
    ], header=False)
    h5(d, "2.6 Repository 汇总")
    table(d, [
        ["职责", "实现类"],
        ["任务事务", "TaskRepository"],
        ["红线日志", "RedlineRepository"],
        ["用户反馈", "FeedbackRepository"],
        ["失败归因", "FailureRepository"],
        ["系统配置", "ConfigRepository"],
    ])

    h3(d, "五、业务逻辑层设计")
    h4(d, "1、类图设计")
    para(d, "业务逻辑层封装系统的核心业务能力，调用数据访问层完成持久化，并向上为路由（接口）层"
            "提供服务。各主要服务类如下图所示。")
    figure(d, "fig08_service_class.png", "图14  业务逻辑层类图")
    h4(d, "2、类的详细设计描述")
    h5(d, "2.1 TaskOrchestrator 接口设计")
    para(d, "详细描述：")
    table(d, [
        ["TaskOrchestrator —— 任务编排状态机（单例），驱动一次任务的规划、评估与推进。"],
        ["process_query(query, image)：接收指令与截图，完成规划与定位，返回执行蓝图"],
        ["evaluate_step(context)：在一步执行后评估结果，判断成功与否"],
        ["advance() / replan()：推进到下一步，或在偏离时触发重规划"],
    ], header=False)
    h5(d, "2.2 MultiProviderClient 接口设计")
    para(d, "详细描述：")
    table(d, [
        ["MultiProviderClient —— 统一多供应商 LLM 客户端，支持 openai/claude/gemini/qwen/deepseek 等。"],
        ["chat(messages)：文本对话调用，含自适应 token 重试与 JSON 修复"],
        ["vision(image, prompt)：多模态调用，结合截图进行规划与定位"],
        ["parse_points(text)：解析 [POINT:x,y:label] 标签为结构化坐标"],
    ], header=False)
    h5(d, "2.3 BlueprintEngine 接口设计")
    para(d, "详细描述：")
    table(d, [
        ["BlueprintEngine —— 蓝图状态机，维护步骤序列的执行状态。"],
        ["advance(task_id)：推进当前步骤"],
        ["rollback(task_id)：回退一步"],
        ["skip(task_id) / terminate(task_id)：跳过当前步骤 / 终止整条蓝图"],
    ], header=False)
    h5(d, "2.4 Safety 与 RiskScorer 接口设计")
    para(d, "详细描述：")
    table(d, [
        ["Safety —— 三层安全分类与风险评分。"],
        ["classify(text)：对指令/步骤进行绿/黄/红分类"],
        ["score(text)：给出 1—5 级风险评分，供是否挂起确认的判断"],
    ], header=False)
    h5(d, "2.5 SetFitIntentClassifier 接口设计")
    para(d, "详细描述：")
    table(d, [
        ["SetFitIntentClassifier —— 意图分类（单例），SetFit 模型 + 关键词回退。"],
        ["classify(query)：返回九类意图之一及意图摘要与置信度"],
    ], header=False)
    h5(d, "2.6 OmniParserClient 接口设计")
    para(d, "详细描述：")
    table(d, [
        ["OmniParserClient —— 远程 OmniParser 的 HTTP 客户端。"],
        ["parse(image)：提交截图，返回元素列表与 SoM 标注图（ParseResult）"],
    ], header=False)
    h5(d, "2.7 业务接口实现类汇总")
    table(d, [
        ["职责", "实现类"],
        ["任务编排", "TaskOrchestrator"],
        ["LLM 调用", "MultiProviderClient"],
        ["蓝图状态机", "BlueprintEngine"],
        ["安全与风险评分", "Safety / RiskScorer"],
        ["意图分类", "SetFitIntentClassifier"],
        ["屏幕解析", "OmniParserClient"],
    ])

    out = os.path.join(BASE, "03-详细设计-单元模块设计.docx")
    d.save(out)
    print("saved", os.path.basename(out))


# ══════════════════════════════════════════════════════════════════
# 文档 04 —— 数据库与部署（第六~七部分）
# ══════════════════════════════════════════════════════════════════
def build_04():
    d = new_doc()
    title(d, "第六部分 数据库设计")

    h3(d, "一、数据库整体结构图")
    para(d, "系统采用 SQLite 作为持久化存储（数据库文件位于 data/hajimi.db），共设计七张表，"
            "按业务域可分为用户管理、任务储存管理、配置管理与安全审计四类。整体 ER 结构如下图所示。")
    figure(d, "fig09_er.png", "图15  数据库 ER 整体结构图")

    h3(d, "二、用户管理")
    para(d, "用户管理表格清单：")
    table(d, [["序号", "名称", "注释"], ["1", "t_users", "用户"]])
    h4(d, "1、t_users 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "user_id", "VARCHAR(64)", "用户编号（主键，UUID）"],
        ["2", "username", "VARCHAR(128)", "用户名（唯一，索引）"],
        ["3", "password_hash", "VARCHAR(256)", "密码散列（bcrypt）"],
        ["4", "role", "VARCHAR(16)", "角色：user / admin"],
        ["5", "preferences", "JSON", "用户偏好设置"],
        ["6", "created_at", "DATETIME", "创建时间"],
        ["7", "last_login_at", "DATETIME", "最后登录时间"],
    ])

    h3(d, "三、任务储存管理")
    para(d, "任务储存管理表格清单：")
    table(d, [
        ["序号", "名称", "注释"],
        ["1", "t_transactions", "任务事务主表"],
        ["2", "t_step_logs", "步骤执行日志"],
        ["3", "t_feedback", "用户反馈"],
        ["4", "t_failures", "失败归因记录"],
    ])
    h4(d, "1、t_transactions 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "task_id", "VARCHAR(64)", "任务编号（主键，UUID）"],
        ["2", "user_id", "VARCHAR(64)", "用户编号（外键）"],
        ["3", "timestamp", "DATETIME", "创建时间（索引）"],
        ["4", "intent_category", "VARCHAR(32)", "意图类别（索引）"],
        ["5", "user_query", "VARCHAR(500)", "用户原始指令"],
        ["6", "intent_summary", "VARCHAR(256)", "意图摘要"],
        ["7", "plan_type", "VARCHAR(8)", "规划路径：L2 / L3"],
        ["8", "complexity_score", "INTEGER", "复杂度评分"],
        ["9", "blueprint_json", "JSON", "执行蓝图快照"],
        ["10", "result", "VARCHAR(16)", "结果：success/fail/cancel/rejected"],
        ["11", "duration_ms", "INTEGER", "总耗时（毫秒）"],
        ["12", "redline_triggered", "BOOLEAN", "是否触发红线"],
    ])
    h4(d, "2、t_step_logs 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "log_id", "VARCHAR(64)", "日志编号（主键，UUID）"],
        ["2", "task_id", "VARCHAR(64)", "任务编号（外键，索引）"],
        ["3", "step_index", "INTEGER", "步骤序号"],
        ["4", "action", "VARCHAR(256)", "动作类型（click/type/…）"],
        ["5", "target_element_id", "VARCHAR(16)", "目标元素编号"],
        ["6", "target_bbox", "JSON", "目标框 [x1,y1,x2,y2]"],
        ["7", "status", "VARCHAR(16)", "步骤状态"],
        ["8", "fingerprint_match", "BOOLEAN", "执行前后指纹是否一致"],
        ["9", "error_code", "VARCHAR(32)", "错误码"],
        ["10", "created_at", "DATETIME", "创建时间"],
    ])
    h4(d, "3、t_feedback 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "feedback_id", "VARCHAR(64)", "反馈编号（主键，UUID）"],
        ["2", "task_id", "VARCHAR(64)", "任务编号（外键，索引）"],
        ["3", "user_id", "VARCHAR(64)", "用户编号（外键）"],
        ["4", "feedback_type", "VARCHAR(16)", "类型：useful/useless/neutral"],
        ["5", "comment", "TEXT", "反馈内容"],
        ["6", "created_at", "DATETIME", "创建时间（索引）"],
    ])
    h4(d, "4、t_failures 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "failure_id", "VARCHAR(64)", "失败编号（主键，UUID）"],
        ["2", "task_id", "VARCHAR(64)", "任务编号（索引）"],
        ["3", "failure_type", "VARCHAR(64)", "失败类型（索引）"],
        ["4", "step_index", "INTEGER", "出错步骤序号"],
        ["5", "fingerprint_hash", "VARCHAR(64)", "出错时屏幕指纹"],
        ["6", "llm_snapshot", "TEXT", "当时的 LLM 快照"],
        ["7", "error_detail", "TEXT", "错误详情"],
        ["8", "created_at", "DATETIME", "创建时间（索引）"],
    ])
    h4(d, "5、储存管理外键清单")
    table(d, [
        ["外键名称", "父表", "父键列", "子表", "外键列", "关系", "说明"],
        ["FK_USER_TASK", "t_users", "user_id", "t_transactions", "user_id", "1..*", "一个用户可发起多个任务"],
        ["FK_TASK_STEP", "t_transactions", "task_id", "t_step_logs", "task_id", "1..*", "一个任务包含多条步骤日志"],
        ["FK_TASK_FB", "t_transactions", "task_id", "t_feedback", "task_id", "1..*", "一个任务可收到多条反馈"],
    ])

    h3(d, "四、配置管理")
    para(d, "配置管理表格清单：")
    table(d, [["序号", "名称", "注释"], ["1", "t_system_configs", "系统配置项"]])
    h4(d, "1、t_system_configs 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "config_id", "VARCHAR(64)", "配置编号（主键，UUID）"],
        ["2", "config_key", "VARCHAR(128)", "配置键（唯一，索引）"],
        ["3", "config_value", "JSON", "配置值"],
        ["4", "description", "VARCHAR(256)", "配置说明"],
        ["5", "updated_by", "VARCHAR(64)", "更新人（外键）"],
        ["6", "updated_at", "DATETIME", "更新时间"],
    ])

    h3(d, "五、安全审计")
    para(d, "安全审计表格清单：")
    table(d, [["序号", "名称", "注释"], ["1", "t_redline_logs", "红线拦截日志"]])
    h4(d, "1、t_redline_logs 表结构")
    table(d, [
        ["序号", "列名", "数据类型", "注释"],
        ["1", "log_id", "VARCHAR(64)", "日志编号（主键，UUID）"],
        ["2", "query", "VARCHAR(500)", "被拦截的指令"],
        ["3", "category", "VARCHAR(32)", "类别：物理操作/隐私/实时动态（索引）"],
        ["4", "action", "VARCHAR(16)", "处置：reject/guided_reject/degrade"],
        ["5", "message", "VARCHAR(512)", "拦截提示信息"],
        ["6", "created_at", "DATETIME", "创建时间（索引）"],
    ])

    spacer(d)
    title(d, "第七部分 补充设计和说明")

    h3(d, "一、编译运行环境设计")
    h4(d, "1. 系统环境")
    para(d, "系统环境是指软件开发与运行过程中所依赖的硬件设备、操作系统及相关基础软件。本项目的"
            "系统环境包括前后端开发环境、算法推理平台环境、服务器部署环境与客户使用环境四部分。")
    h5(d, "1.1. 前后端开发环境")
    para(d, "前后端开发环境是指在本地进行 B 端桌面客户端、A 端服务端与 Web 管理面板开发调试所用的"
            "机器配置，需能够支持三端代码运行。具体配置如下表：")
    table(d, [
        ["配置名称", "配置信息"],
        ["操作系统", "Windows 11"],
        ["CPU", "Intel Core i7 及以上"],
        ["内存", "16GB RAM 及以上"],
        ["运行时", "Python 3.11 / Node.js 16"],
        ["硬盘", "SSD 512GB 及以上"],
    ])
    h5(d, "1.2. 算法推理平台环境")
    para(d, "算法推理平台环境是指承载 OmniParser 视觉解析模型的机器配置。该模型对显存与并行计算"
            "能力有较高要求，通常部署于独立的 GPU 服务器，通过 SSH 隧道对外提供服务。具体配置如下表：")
    table(d, [
        ["配置名称", "配置信息"],
        ["操作系统", "Ubuntu 20.04 / Windows Server"],
        ["GPU", "NVIDIA RTX 3090 / 等效及以上"],
        ["显存", "24GB 及以上"],
        ["内存", "32GB RAM"],
        ["依赖", "PyTorch + CUDA、OmniParser V2 权重"],
    ])
    h5(d, "1.3. 服务器部署环境")
    para(d, "服务器部署环境指 A 端服务端与 Web 管理面板正式上线所依赖的环境。A 端为轻量 FastAPI"
            "服务，可与桌面端同机部署或部署于云主机；LLM 推理经由云端 API 完成，无需本地大算力。"
            "为控制成本，部署遵循“按需供配”的原则。参考配置如下表：")
    table(d, [
        ["配置名称", "配置信息"],
        ["服务器提供方", "云主机 / 本地工作站"],
        ["系统", "CentOS 7 / Windows"],
        ["CPU", "4 核及以上"],
        ["内存", "8GB RAM"],
        ["硬盘", "50GB"],
    ])
    h5(d, "1.4. 客户使用环境")
    para(d, "客户使用环境即终端用户使用系统时所需的配置。桌面端用户需运行 PyQt5 客户端与执行引擎，"
            "推荐配置见下表；Web 管理端用户仅需现代浏览器（推荐 Chrome/Edge 最新版）即可访问。")
    table(d, [
        ["配置名称", "最低配置", "推荐配置"],
        ["操作系统", "Windows 10", "Windows 11"],
        ["CPU", "Intel Core i5", "Intel Core i7 及以上"],
        ["内存", "8GB RAM", "16GB RAM 及以上"],
        ["网络", "可访问 A 端与云端 LLM", "稳定宽带 + SSH 隧道"],
    ])

    h4(d, "2. 运行环境")
    para(d, "运行环境是指软件实际运行时所需的软件与服务。主要包括：")
    bullet(d, "数据库：SQLite 3（文件型，随 A 端首次启动自动建表）")
    bullet(d, "服务端：Python 3.11 + FastAPI + Uvicorn，监听 8010 端口")
    bullet(d, "视觉服务：OmniParser V2，监听 9800 端口，经 SSH 隧道访问")
    bullet(d, "Web 面板：Node.js 16 + Vite，开发态监听 5173 端口")
    bullet(d, "大模型：多模态 LLM 云端 API（Qwen / DeepSeek 等，OpenAI 兼容协议）")

    h4(d, "3. 开发环境")
    para(d, "本项目使用到的开发工具主要包括：")
    bullet(d, "Python 开发：PyCharm / VS Code")
    bullet(d, "前端开发：VS Code + Vue Devtools")
    bullet(d, "数据库管理：DB Browser for SQLite")
    bullet(d, "接口调试：Postman / Swagger UI")
    bullet(d, "版本管理：Git / GitHub")

    h4(d, "4. 部署过程描述")
    para(d, "系统部署遵循“先起视觉服务、再起服务端、最后起客户端”的顺序，主要过程如下。")
    figure(d, "fig10_deploy.png", "图16  网络部署拓扑图")
    para(d, "第一步，建立 OmniParser 访问通道。在本地通过 SSH 端口转发，将远程 GPU 上的 9800 端口"
            "映射到本地：")
    table(d, [["ssh -L 9800:127.0.0.1:9800 <user>@<gpu-host>"]], header=False)
    para(d, "第二步，配置服务端环境变量。在 server/.env 中填写 LLM_API_KEY、LLM_BASE_URL、"
            "LLM_MODEL 与 OMNIPARSER_URL 等参数。")
    para(d, "第三步，启动服务端。可直接运行一键脚本，或手动启动 Uvicorn：")
    table(d, [["python -m uvicorn server.main:app --host 127.0.0.1 --port 8010"]], header=False)
    para(d, "第四步，启动桌面客户端与 Web 管理面板。桌面端由启动脚本拉起，Web 面板通过 npm 启动：")
    table(d, [["启动本地.bat        # 一键拉起 A 端 + B 端",
               "cd web-admin && npm run dev   # 启动 Web 管理面板"]], header=False)
    para(d, "第五步，联通性验证。运行连通性测试脚本，确认三端链路、审计回路与配置回路均正常，"
            "即完成部署。")
    table(d, [["python 项目文档/测试文档/demo_connectivity.py"]], header=False)

    out = os.path.join(BASE, "04-详细设计-数据库与部署.docx")
    d.save(out)
    print("saved", os.path.basename(out))


if __name__ == "__main__":
    build_01()
    build_02()
    build_03()
    build_04()
    print("ALL DOCS DONE")
