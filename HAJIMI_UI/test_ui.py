#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_ui.py - HAJIMI UI + Parser 集成测试脚本

运行前请确保：
1. 已安装所有依赖（PyQt5, replicate, PIL, mss, opencv-python 等）
2. 已设置环境变量 REPLICATE_API_TOKEN
3. 当前工作目录为项目根目录（包含 ui/ 和 core/ 文件夹）

用法：
    python test_ui.py [--no-gui]   # 不加参数则显示GUI窗口，加 --no-gui 则仅控制台测试
"""

import sys
import os
import argparse
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, Qt
from ui.main_widget import MainWidget
from core.ui_parser import UIParserThread

# 测试用例
TEST_QUERIES = [
    "怎么安装微信？",
    "如何保存这个文档？",
    "帮我自动点击抢票",  # 应触发红线
]

class Tester:
    def __init__(self, gui_mode=True):
        self.gui_mode = gui_mode
        self.app = QApplication(sys.argv)
        self.app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        self.app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        if gui_mode:
            self.main_widget = MainWidget()
            self.main_widget.show()
            # 连接主窗口的信号以打印日志
            self.connect_signals()
            # 启动后自动执行第一个测试用例
            QTimer.singleShot(1000, self.run_test_case)
        else:
            # 无GUI模式：仅测试解析器本身
            self.test_parser_only()

    def connect_signals(self):
        """连接MainWidget内部信号以打印调试信息"""
        # 获取内部的 parser_thread 和 bridge
        if hasattr(self.main_widget, 'parser_thread'):
            parser = self.main_widget.parser_thread
            parser.sig_parse_success.connect(lambda elems, _, __, ___: print(f"[测试] 解析成功，元素数: {len(elems)}"))
            parser.sig_parse_error.connect(lambda err: print(f"[测试] 解析错误: {err}"))
            parser.sig_redline_triggered.connect(lambda msg: print(f"[测试] 红线触发: {msg}"))

        # 也可连接bridge信号
        if hasattr(self.main_widget, 'bridge'):
            bridge = self.main_widget.bridge
            bridge.sig_add_message.connect(lambda text, typ: print(f"[测试] 添加消息: {text[:30]}... (类型:{typ})"))
            bridge.sig_update_steps.connect(lambda steps, idx: print(f"[测试] 更新步骤: {len(steps)}步, 当前索引:{idx}"))

    def run_test_case(self, index=0):
        """按顺序执行测试用例"""
        if index >= len(TEST_QUERIES):
            print("[测试] 所有测试用例执行完毕，5秒后退出")
            QTimer.singleShot(5000, self.app.quit)
            return

        query = TEST_QUERIES[index]
        print(f"\n>>> 执行测试用例 {index+1}/{len(TEST_QUERIES)}: {query}")

        # 直接通过 bridge 发送用户输入（替代原先的 self.main_widget.user_input）
        if hasattr(self.main_widget, 'bridge'):
            self.main_widget.bridge.sendUserInput(query)
        else:
            print("[错误] bridge 不存在，无法发送测试用例")

        # 等待4秒后执行下一个用例
        QTimer.singleShot(4000, lambda: self.run_test_case(index+1))

    def test_parser_only(self):
        """无GUI模式：直接测试UIParserThread"""
        print("=== 无GUI模式：直接测试UIParserThread ===")
        parser = UIParserThread()
        parser.sig_parse_success.connect(self.on_parser_success)
        parser.sig_parse_error.connect(self.on_parser_error)
        parser.sig_redline_triggered.connect(self.on_redline)
        parser.sig_progress.connect(lambda prog, status: print(f"[进度] {prog}%: {status}"))

        # 测试红线检测
        print("测试红线检测...")
        parser.request_parse("帮我自动点击抢票")
        # 由于是异步，需要启动事件循环等待
        QTimer.singleShot(5000, self.app.quit)
        self.app.exec_()

    def on_parser_success(self, elements, som_base64, element_map, fingerprint):
        print(f"[成功] 元素数: {len(elements)}")
        print(f"[成功] 指纹: {fingerprint}")
        print(f"[成功] 前3个元素: {elements[:3]}")
        # 也可以保存som图片到文件
        # import base64
        # with open("som.png", "wb") as f:
        #     f.write(base64.b64decode(som_base64))
        self.app.quit()

    def on_parser_error(self, err):
        print(f"[错误] {err}")
        self.app.quit()

    def on_redline(self, msg):
        print(f"[红线] {msg}")
        self.app.quit()

    def run(self):
        if not self.gui_mode:
            return  # 已在test_parser_only中启动事件循环
        self.app.exec_()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 HAJIMI UI 和解析器")
    parser.add_argument("--no-gui", action="store_true", help="不使用GUI，仅测试解析器")
    args = parser.parse_args()

    tester = Tester(gui_mode=not args.no_gui)
    tester.run()