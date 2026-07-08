# core/ui_parser.py
import sys
import hashlib
import time
import base64
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
from PIL import Image, ImageGrab
import mss
import cv2
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
import replicate
import os


class UIParserThread(QThread):
    sig_parse_success = pyqtSignal(list, str, dict, str)
    sig_parse_error = pyqtSignal(str)
    sig_redline_triggered = pyqtSignal(str)
    sig_progress = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self._stop = False
        self.query = ""
        self.screenshot = None

        # 缓存
        self.cache = {}
        self.cache_max_size = 20

        # 红线关键词
        self.redline_keywords = [
            "自动点击", "帮我执行", "替我操作", "自动抢票",
            "扫描硬盘", "查看聊天记录", "找出所有照片",
            "跟踪动态", "监控屏幕"
        ]

        # 检查环境变量
        if not os.environ.get("REPLICATE_API_TOKEN"):
            print("[警告] 未设置 REPLICATE_API_TOKEN，API 调用将失败")

    def stop(self):
        self.mutex.lock()
        self._stop = True
        self.condition.wakeAll()
        self.mutex.unlock()

    def request_parse(self, query: str, screenshot: Optional[Image.Image] = None):
        self.query = query
        self.screenshot = screenshot
        self.start()

    def run(self):
        try:
            self.sig_progress.emit(10, "捕获屏幕...")
            screenshot = self.screenshot if self.screenshot else self._capture_screen()
            if screenshot is None:
                self.sig_parse_error.emit("屏幕捕获失败")
                return

            if self._check_redline(self.query):
                self.sig_redline_triggered.emit("您的请求涉及安全红线，系统无法执行。")
                return

            fingerprint = self._compute_fingerprint(screenshot)
            if fingerprint in self.cache:
                cached = self.cache[fingerprint]
                self.sig_progress.emit(100, "命中缓存")
                self.sig_parse_success.emit(
                    cached["elements"],
                    cached["som_base64"],
                    cached["element_map"],
                    fingerprint
                )
                return

            self.sig_progress.emit(30, "调用 OmniParser...")
            elements = self._parse_ui(screenshot)
            if not elements:
                self.sig_parse_error.emit("未检测到任何 UI 元素")
                return

            self.sig_progress.emit(60, "生成 SoM 标注图...")
            som_image, element_map = self._generate_som(screenshot, elements)
            som_base64 = self._pil_to_base64(som_image)

            self._update_cache(fingerprint, elements, som_base64, element_map)

            self.sig_progress.emit(100, "解析完成")
            self.sig_parse_success.emit(elements, som_base64, element_map, fingerprint)

        except Exception as e:
            self.sig_parse_error.emit(f"解析异常: {str(e)}")

    # ---------- 核心方法 ----------
    def _capture_screen(self) -> Optional[Image.Image]:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                return img
        except Exception as e:
            print(f"[CAP] 截图失败: {e}")
            try:
                return ImageGrab.grab()
            except:
                return None

    def _compute_fingerprint(self, img: Image.Image) -> str:
        resized = img.resize((64, 64))
        import hashlib
        return hashlib.sha256(resized.tobytes()).hexdigest()[:16]

    def _check_redline(self, query: str) -> bool:
        q_lower = query.lower()
        for kw in self.redline_keywords:
            if kw in q_lower:
                return True
        return False

    def _parse_ui(self, img: Image.Image) -> List[Dict[str, Any]]:
        """
        调用 Replicate API 的 OmniParser V2
        """
        try:
            # 将 PIL 转为字节流
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            img_bytes = buffer.getvalue()

            output = replicate.run(
                "microsoft/omniparser-v2:49cf3d41b8d3aca1360514e83be4c97131ce8f0d99abfc365526d8384caa88df",
                input={
                    "image": img_bytes,
                    "imgsz": 640,
                    "box_threshold": 0.05,
                    "iou_threshold": 0.1
                },
                timeout=30
            )

            # 解析返回结果（根据实际返回结构调整）
            # 先尝试常见字段
            if isinstance(output, dict):
                parsed = output.get("parsed_content") or output.get("boxes")
            else:
                parsed = output

            if not parsed:
                print("[OmniParser] 返回数据为空")
                return []

            # 转换为统一格式
            elements = []
            for i, item in enumerate(parsed):
                if isinstance(item, dict):
                    bbox = item.get("bbox")
                    if not bbox:
                        continue
                    elements.append({
                        "id": i + 1,
                        "bbox": bbox,
                        "type": item.get("type", "unknown"),
                        "text": item.get("text", ""),
                        "confidence": item.get("confidence", 0.0)
                    })
            return elements

        except replicate.exceptions.ReplicateError as e:
            print(f"[OmniParser API 错误] {e}")
            return []
        except Exception as e:
            print(f"[OmniParser] 未知异常: {e}")
            return []

    def _generate_som(self, img: Image.Image, elements: List[Dict]) -> Tuple[Image.Image, Dict]:
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        element_map = {}

        color_map = {
            "button": (0, 0, 255),
            "input": (0, 255, 0),
            "icon": (0, 255, 255),
            "menu": (255, 0, 255),
            "checkbox": (255, 255, 0),
            "dropdown": (255, 128, 0)
        }

        for elem in elements:
            elem_id = elem["id"]
            x1, y1, x2, y2 = elem["bbox"]
            color = color_map.get(elem.get("type", "button"), (0, 0, 255))

            cv2.rectangle(cv_img, (x1, y1), (x2, y2), color, 2)

            label = f"~{elem_id}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            label_x = x1
            label_y = y1 - th - 6
            if label_y < 0:
                label_y = y2 + 6
            cv2.rectangle(cv_img, (label_x, label_y - th - 4), (label_x + tw + 4, label_y + 4), (255,255,255), -1)
            cv2.putText(cv_img, label, (label_x + 2, label_y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)

            center = ((x1+x2)//2, (y1+y2)//2)
            element_map[elem_id] = {
                "bbox": elem["bbox"],
                "type": elem["type"],
                "text": elem["text"],
                "center": center
            }

        pil_img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))
        return pil_img, element_map

    def _pil_to_base64(self, img: Image.Image) -> str:
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _update_cache(self, fingerprint: str, elements: list, som_base64: str, element_map: dict):
        if len(self.cache) >= self.cache_max_size:
            first_key = next(iter(self.cache))
            del self.cache[first_key]
        self.cache[fingerprint] = {
            "elements": elements,
            "som_base64": som_base64,
            "element_map": element_map
        }