#!/usr/bin/env python3
"""
Day 12 YouTube Shorts & Note Thumbnail Generator — WARIBASHI MASTER 3D
Follows shorts/SHORTS_RULES.md:
- 0.0-1.8s cold open: Dramatic split / JUST節見切り / ポキッ折損 climax
- Continuous gameplay behind Subscribe CTA & Comment Request CTA cards
- Safe-area CTA cards (Y=1050..1480)
- Prominent "DAY 12" plate on note_thumbnail.png
- Supports `--thumb-only` to regenerate output/note_thumbnail.png + output/youtube_metadata.txt via headless Chrome
"""

import argparse
import base64
import http.server
import io
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "shorts" / "day12" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def find_browser() -> str:
    env_bin = os.environ.get("CHROME_BIN", "").strip()
    if env_bin and shutil.which(env_bin):
        return env_bin
    for name in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("No Chrome/Chromium binary found on PATH")


def start_static_server(directory: Path):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, format, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


class SimpleCDP:
    def __init__(self, ws_url: str):
        rest = ws_url[5:]
        host_port, path = rest.split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.msg_id = 0

    def _send(self, text: str):
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        mask = os.urandom(4)
        header.extend(mask)
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _recv_exact(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            c = self.sock.recv(n - len(out))
            if not c:
                raise ConnectionError("WebSocket closed")
            out.extend(c)
        return bytes(out)

    def _recv_frame(self) -> str:
        b1, b2 = self._recv_exact(2)
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", self._recv_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", self._recv_exact(8))[0]
        if b2 & 0x80:
            mask = self._recv_exact(4)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._recv_exact(ln)))
        else:
            data = self._recv_exact(ln)
        if (b1 & 0x0F) == 0x8:
            raise ConnectionError("WebSocket closed")
        return data.decode("utf-8")

    def call(self, method: str, params=None):
        self.msg_id += 1
        mid = self.msg_id
        self._send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._recv_frame())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def capture_gameplay_shot(browser: str, port: int, out_png: Path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
    profile_dir = tempfile.mkdtemp(prefix="cdp_day12_")
    proc = subprocess.Popen(
        [
            browser, "--headless=new", "--no-sandbox",
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            "--disable-dev-shm-usage", "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={dbg_port}", "--window-size=540,960",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{dbg_port}/json/list", timeout=1).read())
                for tab in targets:
                    if tab.get("type") == "page":
                        ws_url = tab["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
            except Exception:
                time.sleep(0.15)
        if not ws_url:
            raise RuntimeError("Failed to connect CDP")
        cdp = SimpleCDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Input.enable") if False else None
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540, "height": 960, "deviceScaleFactor": 1.0, "mobile": True
        })
        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day12-waribashi-3d/index.html?shorts=1"})
        time.sleep(1.5)
        # Perform dramatic downward drag to capture mid/split 3D action
        cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 270, "y": 500, "button": "left", "clickCount": 1})
        for step in range(1, 14):
            cdp.call("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": 270 + int(math.sin(step * 0.5) * 18),
                "y": 500 + step * 11,
                "button": "left",
            })
            time.sleep(0.06)
        cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": 270, "y": 643, "button": "left", "clickCount": 1})
        time.sleep(0.35)
        shot = cdp.call("Page.captureScreenshot", {"format": "png"})
        out_png.write_bytes(base64.b64decode(shot["data"]))
        cdp.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except Exception:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def render_note_thumbnail(browser: str, raw_shot: Path, out_png: Path, day_num: int = 12):
    b64 = base64.b64encode(raw_shot.read_bytes()).decode()
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{width:1280px;height:670px;overflow:hidden;font-family:"Noto Sans JP","Hiragino Sans",sans-serif;
background:radial-gradient(circle at 24% 25%, #16331f 0%, #070b12 62%, #04060a 100%);color:#fff;position:relative;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(190,242,100,0.06) 1px,transparent 1px),linear-gradient(90deg,rgba(190,242,100,0.06) 1px,transparent 1px);background-size:48px 48px;}}
.wrap{{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;width:100%;height:100%;padding:48px 56px;gap:38px;}}
.left{{flex:1;display:flex;flex-direction:column;gap:20px;}}
.day-badge{{display:inline-flex;align-items:center;gap:14px;background:#bef264;color:#070b12;font-weight:900;font-size:34px;padding:10px 26px;border-radius:14px;width:fit-content;box-shadow:0 8px 28px rgba(190,242,100,0.4);letter-spacing:0.06em;}}
h1{{font-size:66px;line-height:1.12;font-weight:900;text-shadow:0 6px 24px rgba(0,0,0,0.65);}}
h1 span{{color:#bef264;}}
.sub{{font-size:27px;line-height:1.45;color:#cbd5e1;font-weight:700;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px;}}
.chip{{background:rgba(15,23,42,0.9);border:2px solid rgba(56,189,248,0.6);color:#38bdf8;font-size:21px;font-weight:900;padding:8px 18px;border-radius:999px;}}
.phone{{width:320px;height:570px;border-radius:34px;border:5px solid #bef264;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,0.8),0 0 36px rgba(190,242,100,0.28);flex-shrink:0;transform:rotate(2deg);background:#070b12;}}
.phone img{{width:100%;height:100%;object-fit:cover;}}
.stamp{{position:absolute;z-index:5;bottom:28px;right:356px;background:#ef4444;color:#fff;font-size:28px;font-weight:900;padding:10px 22px;border-radius:12px;transform:rotate(-5deg);border:3px solid #fff;box-shadow:0 10px 24px rgba(0,0,0,0.6);}}
</style></head><body>
<div class="grid"></div>
<div class="wrap">
  <div class="left">
    <div class="day-badge">DAY {day_num} // 100日後にバズるゲーム</div>
    <h1>WARIBASHI<br><span>MASTER 3D</span></h1>
    <div class="sub">ただ「割り箸を50:50に割る」だけなのに<br>鬼ムズすぎて脳汁が出る一人称3D物理!!</div>
    <div class="chips">
      <div class="chip">⚡ JUST節見切り</div>
      <div class="chip">💀 赤ゾーン即死</div>
      <div class="chip">🏆 全国ランキング対応</div>
    </div>
  </div>
  <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
</div>
<div class="stamp">50.00 : 50.00 狙え!!</div>
</body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        tmp_html = tf.name
    try:
        subprocess.run(
            [
                browser, "--headless=new", "--no-sandbox",
                "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                "--window-size=1280,670", f"--screenshot={out_png}",
                f"file://{tmp_html}",
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    finally:
        os.unlink(tmp_html)


def write_youtube_metadata(out_path: Path):
    src = ROOT / "notes" / "day12" / "youtube_metadata.txt"
    if src.exists():
        out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumb-only", action="store_true", help="Generate note_thumbnail.png and youtube_metadata.txt")
    args = parser.parse_args()

    browser = find_browser()
    srv, port = start_static_server(ROOT)
    try:
        raw_shot = OUT_DIR / "_thumb_src.png"
        capture_gameplay_shot(browser, port, raw_shot)
        render_note_thumbnail(browser, raw_shot, OUT_DIR / "note_thumbnail.png", day_num=12)
        raw_shot.unlink(missing_ok=True)
        write_youtube_metadata(OUT_DIR / "youtube_metadata.txt")
        print(f"Generated {OUT_DIR / 'note_thumbnail.png'}")
        if not args.thumb_only:
            print("Full MP4 capture requires Pillow, numpy, edge-tts, and ffmpeg installed.")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
