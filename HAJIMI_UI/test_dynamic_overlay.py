# test_dynamic_overlay.py
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from ui.overlay_anno import OverlayAnnoWindow  # 确保导入路径正确


def simulate_ai_behavior():
    app = QApplication(sys.argv)

    # 1. 实例化你的覆盖层
    overlay = OverlayAnnoWindow()

    # 2. 准备几组不同的模拟坐标数据（模拟鼠标在不同位置时的识别结果）
    frame_data = [
        [{"type": "box", "rect": [100, 100, 300, 300], "label": "A"}],
        [
            {"type": "box", "rect": [200, 200, 400, 400], "label": "B"},
            {"type": "arrow", "from": [100, 100], "to": [200, 200]}
        ],
        [{"type": "box", "rect": [400, 100, 700, 500], "label": "C"}],
        []  # 空数据，测试一键清空
    ]

    state = {"current_frame": 0}

    # 3. 使用 QTimer 模拟每隔 1.5 秒，AI 传回一帧新数据
    def trigger_next_frame():
        idx = state["current_frame"] % len(frame_data)
        print(f"正在模拟刷新第 {idx + 1} 帧 AI 数据...")

        # 调用你的核心方法
        overlay.update_annotations(frame_data[idx])

        state["current_frame"] += 1

    timer = QTimer()
    timer.timeout.connect(trigger_next_frame)
    timer.start(1500)  # 1500 毫秒 = 1.5 秒

    # 初次触发
    trigger_next_frame()

    # 💡 错误在这里：请把 exec_p() 改为 exec_()
    sys.exit(app.exec_())


if __name__ == "__main__":
    simulate_ai_behavior()