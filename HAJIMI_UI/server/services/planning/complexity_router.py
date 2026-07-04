"""
复杂度评分与二级路由（L2/L3）

L2（快路径）：复杂度 < 30，模板规则生成，不调用 LLM，<3s
L3（慢路径）：复杂度 ≥ 30，完整 OmniParser + LLM 流水线

参考：设计文档 §4.3.2、§6.1
"""
import re
from typing import List, Optional, Tuple

from server.models.schemas import UIElement


# ────────────────────────── 复杂度评分 ──────────────────────────

# 跨应用关键词 — 命中则 +10 分
_CROSS_APP_KEYWORDS = [
    "微信", "QQ", "浏览器", "Word", "Excel", "PPT", "PS",
    "网页", "网站", "下载", "安装", "上传", "发送", "邮件",
    "打印", "导出", "导入", "另存为", "转换", "压缩",
]

# 常见操作动词 — 用于动词计数
_ACTION_VERBS = [
    "安装", "下载", "打开", "关闭", "保存", "删除", "移动",
    "复制", "粘贴", "设置", "修改", "创建", "添加", "切换",
    "登录", "注册", "搜索", "查找", "截屏", "截图", "录屏",
    "压缩", "解压", "发送", "上传", "分享", "打印", "扫描",
]


def score_complexity(query: str) -> int:
    """
    对用户查询进行复杂度评分。

    公式：len(query) * 0.3 + n_verbs * 8 + cross_app_count * 10
    阈值：<  15 → 极简（单步模板）
          <  30 → L2 快路径
          >= 30 → L3 慢路径
    """
    q = query.strip()
    if not q:
        return 0

    # 长度因子
    length_score = len(q) * 0.3

    # 动词因子
    verb_count = sum(1 for v in _ACTION_VERBS if v in q)
    verb_score = verb_count * 8

    # 跨应用因子
    cross_count = sum(1 for k in _CROSS_APP_KEYWORDS if k in q)
    cross_score = cross_count * 10

    return int(length_score + verb_score + cross_score)


def route_complexity(query: str) -> str:
    """
    返回路由结果："L2" 或 "L3"
    """
    s = score_complexity(query)
    return "L2" if s < 30 else "L3"


# ────────────────────────── L2 模板规则生成 ──────────────────────────

# L2 步骤模板库：(匹配模式, [(action, description)])
_L2_TEMPLATES: List[Tuple[re.Pattern, List[Tuple[str, str]]]] = [
    # 打开应用
    (re.compile(r"打开\s*[\"「]?(\S+?)[\"」]?\s*$"), [
        ("找到{0}", "在桌面或开始菜单找到 {0} 的图标"),
        ("双击打开{0}", "双击 {0} 图标启动应用"),
    ]),
    (re.compile(r"(启动|运行)\s*[\"「]?(\S+?)[\"」]?\s*$"), [
        ("找到{0}", "在桌面或开始菜单找到 {0}"),
        ("双击打开{0}", "双击启动 {0}"),
    ]),
    # 保存文件
    (re.compile(r"保存\s*(文件|文档|当前|这个)?"), [
        ("点击文件菜单", "在窗口左上角找到「文件」菜单并点击"),
        ("点击保存", "在下拉菜单中选择「保存」（或按 Ctrl+S）"),
    ]),
    # 截图
    (re.compile(r"(截.{0,1}(图|屏)|屏幕截|snip)", re.IGNORECASE), [
        ("打开截图工具", "按下 Win + Shift + S 打开系统截图工具"),
        ("选择截图区域", "拖动鼠标选择要截取的区域"),
        ("保存截图", "截图完成后点击通知预览并保存"),
    ]),
    # 复制粘贴
    (re.compile(r"(复制|拷贝).{0,6}(粘贴|黏贴)"), [
        ("选中内容", "用鼠标拖选要复制的内容"),
        ("复制", "按 Ctrl+C 复制选中内容"),
        ("粘贴", "在目标位置按 Ctrl+V 粘贴"),
    ]),
    # 关闭窗口/应用
    (re.compile(r"(关闭|退出)\s*(窗口|应用|程序|这个)?"), [
        ("点击关闭按钮", "点击窗口右上角的 ✕ 按钮"),
        ("确认关闭", "如有提示，确认关闭"),
    ]),
    # 查找设置
    (re.compile(r"(设置|配置|选项|偏好)"), [
        ("打开设置", "点击开始菜单 → 齿轮图标打开「设置」"),
        ("找到对应选项", "在搜索框中输入关键词查找对应设置项"),
    ]),
    # 重启/关机
    (re.compile(r"(重启|关机|注销|休眠|睡眠)"), [
        ("打开电源菜单", "点击开始菜单 → 电源图标"),
        ("选择操作", "在弹出菜单中选择需要的操作"),
    ]),
    # 文件搜索
    (re.compile(r"(找|搜索|查找)\s*(到|一下)?.{0,4}(文件|文档|图片|文件夹)"), [
        ("打开文件资源管理器", "点击任务栏文件夹图标或按 Win+E"),
        ("使用搜索", "在右上角搜索框中输入文件名关键词"),
    ]),
    # 连接WiFi
    (re.compile(r"(连.{0,2}网|WiFi|wifi|无线|网络连接)"), [
        ("打开网络面板", "点击任务栏右下角网络图标"),
        ("选择网络", "在列表中选择目标 Wi-Fi"),
        ("输入密码连接", "输入密码后点击「连接」"),
    ]),
    # 调节音量
    (re.compile(r"(音量|声音|静音|扬声器)"), [
        ("点击音量图标", "点击任务栏右下角扬声器图标"),
        ("调节音量", "拖动滑块调整到合适音量"),
    ]),
]


def _extract_template_match(query: str) -> Optional[List[dict]]:
    """尝试用模板匹配查询，返回步骤列表或 None"""
    q = query.strip()
    for pattern, template_steps in _L2_TEMPLATES:
        m = pattern.search(q)
        if m:
            # 取第一个捕获组作为参数（如应用名），没有捕获组则用空字符串
            arg = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            steps = []
            for i, (action_tpl, desc_tpl) in enumerate(template_steps):
                steps.append({
                    "action": action_tpl.format(arg) if "{0}" in action_tpl else action_tpl,
                    "description": desc_tpl.format(arg) if "{0}" in desc_tpl else desc_tpl,
                    "target_element_id": "",
                })
            return steps
    return None


def generate_l2_steps(query: str, elements: Optional[List[UIElement]] = None) -> Optional[List[dict]]:
    """
    L2 快路径步骤生成 — 纯本地模板匹配，不调用 LLM。

    Args:
        query: 用户查询
        elements: UI 元素列表（L2 场景下用于 element_id 绑定，暂简化处理）

    Returns:
        步骤列表，或 None（无法匹配时降级到 L3）
    """
    return _extract_template_match(query)
