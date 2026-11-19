#!/usr/bin/env python3
"""
Day 05 YouTube Shorts (1080x1920, 60fps, 14.0s pure dopamine showcase) + Note Thumbnail Generator.
Showcases CROWD x999 (Fake-Ad Multiplier Gate Shooter/Runner made real!):
- Shoots Red -8 gate into Blue + -> busts 3WAY barrel -> slams x3 gate -> summons Golden Giants
- Slams x4 gate into a 200+ blue tsunami -> melts 145 enemy horde & Giant Boss -> Victory!
"""

import base64
import http.server
import json
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
                raise ConnectionError("WebSocket closed")
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


def render_note_thumbnail(browser: str, game_png_path: Path, out_png: Path):
    b64 = base64.b64encode(game_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: linear-gradient(135deg, #0284c7 0%, #0369a1 45%, #0f172a 100%);
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  color:#ffffff;display:flex;align-items:center;justify-content:space-between;
  padding:46px 56px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2.5px solid rgba(255,255,255,0.28);border-radius:22px;pointer-events:none;
}}
.left{{width:725px;z-index:2;}}
.badge{{
  display:inline-block;padding:8px 22px;border-radius:999px;
  background:linear-gradient(90deg,#f59e0b,#fde047);color:#0f172a;
  font-weight:900;font-size:22px;letter-spacing:0.06em;margin-bottom:18px;
  box-shadow:0 8px 24px rgba(0,0,0,0.3);
}}
h1{{
  font-size:74px;line-height:1.05;font-weight:900;letter-spacing:0.01em;
  color:#ffffff;margin-bottom:18px;
  text-shadow:0 8px 24px rgba(15,23,42,0.55);
}}
h1 span{{color:#fde047;}}
.sub{{
  font-size:34px;font-weight:900;color:#e0f2fe;line-height:1.35;margin-bottom:26px;
}}
.sub strong{{color:#fde047;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(15,23,42,0.78);
  border:2px solid rgba(253,224,71,0.6);font-size:20px;font-weight:800;color:#ffffff;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #ffffff;
  box-shadow:0 24px 60px rgba(0,0,0,0.65), 0 0 42px rgba(56,189,248,0.45);
  transform:rotate(2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:28px;left:-32px;transform:rotate(-8deg);
  padding:10px 24px;border-radius:14px;background:linear-gradient(90deg,#f59e0b,#ef4444);
  border:3.5px solid #ffffff;color:#ffffff;font-weight:900;font-size:28px;
  box-shadow:0 12px 28px rgba(0,0,0,0.5);
}}
</style></head><body>
  <div class="left">
    <div class="badge">GAME DAY 05 ｜ 無料ブラウザゲーム</div>
    <h1>CROWD <span>×999</span></h1>
    <div class="sub">あの広告の<strong>増殖ゲート</strong>を<br>詐欺なし＆脳汁全振りでガチ神ゲー化！</div>
    <div class="chips">
      <div class="chip">🔴→🔵 撃って反転</div>
      <div class="chip">🔱 3WAY＆巨人召喚</div>
      <div class="chip">🌊 ×4ゲート大津波</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">×4 大増殖!!</div>
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
    dbg_port = 9265
    proc = subprocess.Popen(
        [
            browser, "--headless=new", "--no-sandbox", "--disable-gpu",
            f"--remote-debugging-port={dbg_port}", "--window-size=540,960",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.2)

    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    fps = 60
    total_sec = 14.0
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

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day05-crowd-999/index.html?shorts=1"})
        time.sleep(0.7)
        cdp.eval_js("window.__manualStep = true;")

        if os.environ.get("THUMB_ONLY") == "1":
            cdp.eval_js("for(let i=0;i<470;i++) window.__stepFrame(1/60);")
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

        render_note_thumbnail(browser, frames_dir / "frame_0470.png", OUT_DIR / "note_thumbnail.png")

        out_mp4 = OUT_DIR / "day05_crowd_999_shorts.mp4"
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
