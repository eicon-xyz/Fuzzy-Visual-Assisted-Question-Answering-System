"""Check what OmniParser sees on WPS screen."""
import base64, json, io, time
from PIL import Image
import mss

# Launch WPS first
import subprocess
wps_path = r"C:\Users\86178\AppData\Local\Kingsoft\WPS Office\12.1.0.26895\office6\wps.exe"
subprocess.Popen([wps_path])
time.sleep(5)  # wait for WPS to render

# Screenshot
with mss.mss() as sct:
    monitor = sct.monitors[1]
    img = sct.grab(monitor)
    pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=70)
    image_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

# Send to OmniParser
import urllib.request
omni_url = "http://127.0.0.1:9800/parse/"
payload = json.dumps({"base64_image": image_b64}).encode()
req = urllib.request.Request(
    omni_url,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read())

elements = result.get("elements", result.get("parsed_content_list_elem", []))
print(f"Total elements detected: {len(elements)}")
print()
print("Elements with text content:")
print("-" * 80)
count = 0
for el in elements:
    text = (el.get("text") or el.get("content") or "").strip()
    if text and count < 50:
        bbox = el.get("bbox", [])
        attrs = el.get("attributes", el.get("element_type", ""))
        print(f"  [{el.get('element_id', el.get('id', '?'))}] \"{text[:80]}\"  bbox={bbox[:4] if bbox else '?'}")
        count += 1

print(f"\nAll element types: {set(el.get('attributes', el.get('element_type', '?')) for el in elements)}")
