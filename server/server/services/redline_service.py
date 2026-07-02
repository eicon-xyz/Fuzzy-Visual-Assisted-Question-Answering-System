"""
红线检测模块（REDLINE）

在用户输入进入意图理解前，进行关键词+语义双重匹配。
拦截三类违规请求，返回标准话术并终止流程。

参考：设计文档 §4.2.4、§6.6 三条红线
"""
import re
from dataclasses import dataclass, field
from typing import Optional, List


# ────────────────────────── 红线类别 ──────────────────────────

@dataclass
class RedlineResult:
    """红线检测结果。triggered=False 表示通过检测。"""
    triggered: bool = False
    category: str = ""          # physical_operation | personal_privacy | realtime_dynamic
    message: str = ""           # 返回给用户的标准话术
    action: str = "reject"      # reject | guided_reject | degrade


# ────────────────────────── 物理操作红线 ──────────────────────────

_PHYSICAL_OPERATION_PATTERNS = [
    # 直接替操作
    (re.compile(r"帮我(自动|执行|点击|操作|下载|安装|删除|打开|关闭|运行)"), 0.95),
    (re.compile(r"(自动|替我|帮我)(点击|操作|执行|抢|刷|签到|打卡)"), 0.95),
    (re.compile(r"(代我|替我|帮我).{0,4}(操作|点击|执行|下载)"), 0.92),
    # 自动化脚本行为
    (re.compile(r"((全|自)动|批量|循环|不停|一直|持续)(点击|抢|刷|操作)"), 0.95),
    (re.compile(r"(脚本|外挂|辅助|破解|刷量)"), 0.98),
    # 连续自动化意图
    (re.compile(r"(每\s*[0-9零一二三四五六七八九十]+\s*(秒|分|小时|天)).{0,6}(执行|点击|操作)"), 0.95),
    (re.compile(r"(定时|自动|循环|重复).{0,4}(执行|点击|发送|提交)"), 0.93),
]

PHYSICAL_OPERATION_REJECT_MSG = (
    "抱歉，我只能为您标注位置和提供文字步骤，无法直接操控您的电脑。"
    "请您根据屏幕上的指引（箭头+高亮框）手动完成操作。"
)


# ────────────────────────── 个人隐私红线 ──────────────────────────

_PRIVACY_PATTERNS = [
    # 扫描/遍历文件系统
    (re.compile(r"(扫描|遍历|搜索|查找).{0,4}(硬盘|磁盘|电脑|所有|全部).{0,4}(文件|照片|图片|视频|文档)"), 0.95),
    (re.compile(r"(找出|找到|列出).{0,4}(所有|全部|整个).{0,4}(文件|照片|图片|视频|密码)"), 0.93),
    # 访问他人私密数据
    (re.compile(r"(查看|读取|偷看|获取).{0,4}(聊天记录|微信|QQ|短信|邮件|消息|通话记录)"), 0.95),
    (re.compile(r"(破解|获取|提取|盗取).{0,8}(密码|账号|密钥|token|cookie)"), 0.98),
    # 监控行为
    (re.compile(r"(监控|监视|记录|跟踪).{0,4}(屏幕|键盘|输入|操作|桌面)"), 0.95),
    (re.compile(r"(截取|捕获).{0,4}(别人|他人|对方).{0,4}(屏幕|聊天|画面)"), 0.93),
]

PRIVACY_GUIDED_REJECT_MSG = (
    "我无法访问您的个人文件或他人隐私内容。如果您需要查找自己的文件，"
    "可以打开「此电脑」或「文件资源管理器」后手动搜索。"
    "我可以指引您如何操作文件管理器。"
)


# ────────────────────────── 实时动态红线 ──────────────────────────

_DYNAMIC_CONTENT_PATTERNS = [
    (re.compile(r"(直播|视频|电影|电视剧|球赛|行情).{0,2}(画面|屏幕|内容|中)"), 0.90),
    (re.compile(r"(正在|实时|动态).{0,2}(播放|直播|刷新|更新)"), 0.88),
    (re.compile(r"(股票|期货|外汇|加密货币).{0,2}(行情|走势|K线)"), 0.92),
]

DYNAMIC_CONTENT_DEGRADE_MSG = (
    "检测到屏幕内容可能持续刷新，我的指引可能滞后于画面变化。"
    "我只能基于当前静态截图给出操作建议，无法持续跟踪动态内容。"
)


# ────────────────────────── 统一入口 ──────────────────────────

def check_redline(query: str) -> RedlineResult:
    """
    对用户输入执行红线检测。

    检测顺序：物理操作 → 个人隐私 → 实时动态
    命中即返回，不继续后续检测。

    Args:
        query: 用户原始查询文本

    Returns:
        RedlineResult — triggered=False 表示通过检测
    """
    q = query.strip()
    if not q:
        return RedlineResult()

    # 1) 物理操作红线
    for pattern, threshold in _PHYSICAL_OPERATION_PATTERNS:
        if pattern.search(q):
            return RedlineResult(
                triggered=True,
                category="physical_operation",
                message=PHYSICAL_OPERATION_REJECT_MSG,
                action="reject",
            )

    # 2) 个人隐私红线
    for pattern, threshold in _PRIVACY_PATTERNS:
        if pattern.search(q):
            return RedlineResult(
                triggered=True,
                category="personal_privacy",
                message=PRIVACY_GUIDED_REJECT_MSG,
                action="guided_reject",
            )

    # 3) 实时动态红线
    for pattern, threshold in _DYNAMIC_CONTENT_PATTERNS:
        if pattern.search(q):
            return RedlineResult(
                triggered=True,
                category="realtime_dynamic",
                message=DYNAMIC_CONTENT_DEGRADE_MSG,
                action="degrade",
            )

    return RedlineResult()
