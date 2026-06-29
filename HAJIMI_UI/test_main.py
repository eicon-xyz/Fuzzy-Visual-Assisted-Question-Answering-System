import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

# 确保能正确导入你的 ui 模块
# 如果目录结构严格按照你提到的，可以使用绝对导入
from ui.main_widget import MainWidget


def simulate_ai_backend(window):
    """
    模拟后台 core/ui_parser.py 动态向前端推送 OmniParser 解析数据的过程
    """
    print("\n[测试] ⏳ 3秒已到，开始模拟后台向前端推送数据...")

    # 模拟数据 1：触发网页自带的 injectUseCase 动效，插入一个新任务
    mock_data_1 = {
        "step": 1,
        "title": "正在通过 OmniParser V2 识别屏幕元素...",
        "status": "loading"
    }
    window.send_step_to_web(mock_data_1)

    # 模拟数据 2：在 2 秒后让网页切换到中等/紧凑模式（测试你网页里的窗体大小切换逻辑）
    # 你网页里暴露了 window.switchToCompact 等方法，可以通过 Python 直接执行
    def trigger_resize():
        print("[测试] ⏳ 尝试让网页切换至紧凑(Compact)视图...")
        window.browser.page().runJavaScript("if(window.switchToCompact){ window.switchToCompact(); }")
        # 同步调整 PyQt5 宿主窗口大小以适应网页紧凑布局
        window.resize(320, 120)

    QTimer.singleShot(2000, trigger_resize)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 1. 实例化你的主挂件
    widget = MainWidget()

    # 2. 监听来自网页按钮的信号（测试 Web -> Python 是否打通）
    widget.bridge.start_perception_signal.connect(lambda: print("[测试成功] ✅ Python 成功捕获到网页点击：开始感知！"))
    widget.bridge.pause_perception_signal.connect(lambda: print("[测试成功] ✅ Python 成功捕获到网页点击：暂停！"))
    widget.bridge.reset_perception_signal.connect(lambda: print("[测试成功] ✅ Python 成功捕获到网页点击：重置！"))

    # 3. 显示窗口
    widget.show()
    print("[测试] 🚀 挂件已启动。当前处于无边框透明置顶状态。")
    print("[测试] 👉 请尝试：1. 按住网页空白处拖动它； 2. 点击网页内的'开始'或'暂停'按钮观察控制台。")

    # 4. 设置一个定时器，3秒后模拟后台推送
    QTimer.singleShot(3000, lambda: simulate_ai_backend(widget))

    sys.exit(app.exec_())