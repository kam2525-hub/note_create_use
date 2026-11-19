#!/usr/bin/env python3
"""
Day 05 YouTube Shorts (1080x1920, 60fps, 18.0s, FULL-BLEED) + Note Thumbnail Generator.
Showcases FAKE OR FORTUNE (Underground Antique Appraiser):
- 0.0s..4.9s: 1888 Imperial Gold Pocket Watch -> X-Ray reveals modern CR2032 battery & PCB!
- 4.9s..7.4s: Slams FAKE stamp -> Forgery busted!
- 7.4s..12.6s: Ming Dragon Porcelain Vase -> UV clean -> X-Ray reveals hidden Golden Orb (Super Jackpot)!
- 12.6s..18.0s: Slams BUY stamp -> Auction rockets past ¥1.5億!
"""

import asyncio
import base64
import http.server
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
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = ROOT / "games" / "day05-fake-or-fortune"
OUT_DIR = ROOT / "shorts" / "day05" / "output"
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


class SimpleCDP:
    """Minimal pure-stdlib WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, ws_url: str):
        assert ws_url.startswith("ws://")
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

    def _send_frame(self, text: str):
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
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise ConnectionError("WebSocket closed")
            out.extend(chunk)
        return bytes(out)

    def _recv_frame(self) -> str:
        while True:
            b1, b2 = self._recv_exact(2)
            op = b1 & 0x0F
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", self._recv_exact(8))[0]
            data = self._recv_exact(ln)
            if op == 8:
                raise ConnectionError("WebSocket closed by server")
            if op == 1:
                return data.decode("utf-8", errors="replace")

    def call(self, method: str, params=None):
        self.msg_id += 1
        mid = self.msg_id
        self._send_frame(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            resp = json.loads(self._recv_frame())
            if resp.get("id") == mid:
                if "error" in resp:
                    raise RuntimeError(f"CDP error {method}: {resp['error']}")
                return resp.get("result", {})

    def eval_js(self, expr: str):
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return res.get("result", {}).get("value")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def start_static_server(directory: Path):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


NARRATION_CUES = [
    (0.10, "1888年の高級懐中時計、本物か偽物か見抜いてみる！"),
    (2.35, "X線を当ててみると…おい、中から乾電池出てきたぞ！"),
    (5.05, "即・贋作スタンプ！偽物を見抜いて報酬ゲット！"),
    (7.60, "次は明朝の大壺。UVライトは異常なし、X線で中を見ると…"),
    (10.50, "うわ！壺の底に純金の秘宝玉が封印されてる！超国宝だ！"),
    (13.10, "即買い取って闇オークションへ！1億超え落札キター！"),
]


def render_note_thumbnail(browser: str, xray_png_path: Path, out_png: Path):
    """Render a crisp 1280x670 magazine-grade note thumbnail using headless Chrome."""
    b64 = base64.b64encode(xray_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: radial-gradient(circle at 28% 35%, #2e1b10 0%, #140b06 72%, #090503 100%);
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  color:#fcf5e3;display:flex;align-items:center;justify-content:space-between;
  padding:46px 56px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2px solid rgba(218,174,88,0.45);border-radius:20px;pointer-events:none;
}}
.left{{width:720px;z-index:2;}}
.badge{{
  display:inline-block;padding:8px 20px;border-radius:999px;
  background:linear-gradient(90deg,#f59e0b,#fde047);color:#1c0f06;
  font-weight:900;font-size:22px;letter-spacing:0.06em;margin-bottom:20px;
  box-shadow:0 6px 20px rgba(245,158,11,0.4);
}}
h1{{
  font-size:66px;line-height:1.12;font-weight:900;letter-spacing:-0.01em;
  background:linear-gradient(180deg,#fff9db 0%,#f5c547 55%,#c48216 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin-bottom:16px;filter:drop-shadow(0 6px 14px rgba(0,0,0,0.65));
}}
.sub{{
  font-size:34px;font-weight:900;color:#fff7e6;line-height:1.35;margin-bottom:28px;
}}
.sub span{{color:#38bdf8;}}
.chips{{display:flex;gap:14px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(16,42,32,0.92);
  border:1.5px solid rgba(218,174,88,0.55);font-size:20px;font-weight:800;color:#fde68a;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #d4a853;
  box-shadow:0 24px 60px rgba(0,0,0,0.85), 0 0 40px rgba(56,189,248,0.28);
  transform:rotate(2.2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:24px;left:-26px;transform:rotate(-11deg);
  padding:10px 24px;border-radius:12px;background:rgba(185,28,28,0.94);
  border:4px solid #fecaca;color:#fff1f2;font-weight:900;font-size:28px;
  box-shadow:0 10px 26px rgba(0,0,0,0.6);
}}
</style></head><body>
  <div class="left">
    <div class="badge">GAME DAY 05 ｜ 無料ブラウザゲーム</div>
    <h1>FAKE OR FORTUNE</h1>
    <div class="sub">指1本で<span>X線＆UV透視</span>！<br>1億円の国宝か偽物か見抜け！</div>
    <div class="chips">
      <div class="chip">🩻 X線レントゲン</div>
      <div class="chip">🟣 UVブラックライト</div>
      <div class="chip">🔨 億超えオークション</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">真作？贋作？</div>
  </div>
</body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        tmp_html = tf.name
    try:
        subprocess.run(
            [
                browser, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--window-size=1280,670", f"--screenshot={out_png}",
                f"file://{tmp_html}",
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    finally:
        os.unlink(tmp_html)


def main():
    browser = find_browser()
    srv, port = start_static_server(ROOT)
    dbg_port = 9235
    proc = subprocess.Popen(
        [
            browser, "--headless=new", "--no-sandbox", "--disable-gpu",
            f"--remote-debugging-port={dbg_port}", "--window-size=540,960",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)

    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    fps = 60
    total_sec = 18.0
    total_frames = int(fps * total_sec)

    try:
        targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{dbg_port}/json").read())
        ws_url = [t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page"][0]
        cdp = SimpleCDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540, "height": 960, "deviceScaleFactor": 2, "mobile": True
        })

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day05-fake-or-fortune/index.html?shorts=1"})
        time.sleep(1.0)
        cdp.eval_js("window.__manualStep = true;")

        thumb_only = os.environ.get("THUMB_ONLY") == "1"
        if thumb_only:
            cdp.eval_js("for(let i=0;i<234;i++) window.__stepFrame(1/60);")
            res = cdp.call("Page.captureScreenshot", {"format": "png"})
            snap_path = OUT_DIR / "_thumb_src.png"
            snap_path.write_bytes(base64.b64decode(res["data"]))
            render_note_thumbnail(browser, snap_path, OUT_DIR / "note_thumbnail.png")
            snap_path.unlink(missing_ok=True)
            print("Generated thumbnail:", OUT_DIR / "note_thumbnail.png")
            cdp.close()
            return

        for f in range(total_frames):
            cdp.eval_js("window.__stepFrame(1/60);")
            res = cdp.call("Page.captureScreenshot", {"format": "png"})
            (frames_dir / f"frame_{f:04d}.png").write_bytes(base64.b64decode(res["data"]))

        # Build thumbnail from dramatic X-Ray battery frame (frame 234 = 3.9s)
        render_note_thumbnail(browser, frames_dir / "frame_0234.png", OUT_DIR / "note_thumbnail.png")

        out_mp4 = OUT_DIR / "day05_fake_or_fortune_shorts.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%04d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                str(out_mp4),
            ],
            check=True,
        )
        print("Generated Shorts MP4:", out_mp4)
        cdp.close()
    finally:
        proc.terminate()
        srv.shutdown()


if __name__ == "__main__":
    main()
