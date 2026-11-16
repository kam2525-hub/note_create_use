#!/usr/bin/env python3
"""
Day 01 YouTube Shorts (1080x1920, 30fps, ~19.5s) + note.com Thumbnail Generator.
Captures live frames from games/day01-just-slash/index.html?shorts=1 via headless Chromium CDP,
renders high-impact Japanese captions, synthesizes 158 BPM hyper BGM + hit-synced SFX,
and muxes with ffmpeg.
"""

import base64
import hashlib
import http.server
import io
import json
import math
import os
import random
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = ROOT / "games" / "day01-just-slash"
OUT_DIR = ROOT / "shorts" / "day01" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def find_browser() -> str:
    for name in ("chromium", "google-chrome", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("No Chromium or Google Chrome binary found on PATH")


def find_jp_font() -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    try:
        out = subprocess.check_output(
            ["fc-match", "-f", "%{file}", "Noto Sans CJK JP:bold"], text=True
        ).strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    raise RuntimeError("Japanese Noto Sans CJK font not found")


FONT_SANS = find_jp_font()


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
            opcode = b1 & 0x0F
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            if b2 & 0x80:
                mask = self._recv_exact(4)
                data = self._recv_exact(length)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            else:
                data = self._recv_exact(length)
            if opcode == 0x8:
                raise ConnectionError("WebSocket closed")
            if opcode == 0x9:  # ping
                continue
            return data.decode("utf-8", errors="replace")

    def call(self, method: str, params=None):
        self.msg_id += 1
        cid = self.msg_id
        self._send_frame(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._recv_frame())
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(f"CDP error {method}: {msg['error']}")
                return msg.get("result", {})

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

        def log_message(self, format, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


def draw_caption_overlay(
    img: Image.Image,
    t: float,
    total_dur: float,
    top_hook: str,
    pop_text: str,
    pop_start: float,
    pop_color: tuple,
    bottom_cta: str,
    font_big,
    font_med,
    font_small,
) -> Image.Image:
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Top progress bar (dopamine retention cue)
    prog = min(1.0, max(0.0, t / total_dur))
    draw.rectangle([0, 0, W, 10], fill=(20, 24, 34))
    draw.rectangle([0, 0, int(W * prog), 10], fill=(255, 212, 0))

    # Top hook pill banner
    if top_hook:
        bbox = draw.textbbox((0, 0), top_hook, font=font_med, stroke_width=5)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx = (W - tw) // 2
        by = 275
        pad_x, pad_y = 26, 14
        draw.rounded_rectangle(
            [bx - pad_x, by - pad_y, bx + tw + pad_x, by + th + pad_y],
            radius=16,
            fill=(255, 46, 84),
        )
        draw.text(
            (bx, by),
            top_hook,
            font=font_med,
            fill=(255, 255, 255),
            stroke_width=4,
            stroke_fill=(15, 10, 18),
        )

    # Dynamic bouncing center/lower pop caption
    if pop_text:
        age = max(0.0, t - pop_start)
        scale = 1.0 + 0.25 * math.exp(-age * 16) * math.cos(age * 35)
        # Draw on temp transparent layer to scale cleanly
        tmp = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(tmp)
        bbox = tdraw.textbbox((0, 0), pop_text, font=font_big, stroke_width=10)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (W - tw) // 2
        ty = (240 - th) // 2 - bbox[1]
        # Hard drop shadow + thick stroke
        tdraw.text((tx + 6, ty + 8), pop_text, font=font_big, fill=(0, 0, 0, 220))
        tdraw.text(
            (tx, ty),
            pop_text,
            font=font_big,
            fill=pop_color,
            stroke_width=10,
            stroke_fill=(10, 12, 18),
        )
        new_w = max(1, int(W * scale))
        new_h = max(1, int(240 * scale))
        resized = tmp.resize((new_w, new_h), Image.Resampling.BICUBIC)
        px = (W - new_w) // 2
        py = int(H * 0.72) - new_h // 2
        img_rgba = img.convert("RGBA")
        img_rgba.paste(resized, (px, py), resized)
        img = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)

    # Bottom CTA pill
    if bottom_cta:
        bbox = draw.textbbox((0, 0), bottom_cta, font=font_small, stroke_width=3)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bx = (W - tw) // 2
        by = H - 150
        draw.rounded_rectangle(
            [bx - 24, by - 12, bx + tw + 24, by + th + 16],
            radius=14,
            fill=(255, 212, 0),
        )
        draw.text((bx, by), bottom_cta, font=font_small, fill=(10, 12, 18))

    return img


def generate_audio(duration: float, events: list, out_wav: Path):
    """Synthesize 158 BPM hyper electronic BGM + hit-synced sound effects."""
    sr = 48000
    n_samples = int(duration * sr)
    buf = np.zeros(n_samples, dtype=np.float64)

    bpm = 158.0
    step_sec = 60.0 / bpm / 4.0  # 16th note (~0.0949s)
    total_steps = int(duration / step_sec) + 1

    bass_seq = [65.41, 65.41, 82.41, 73.42, 87.31, 87.31, 98.00, 73.42]  # C2..G2
    arp_seq = [
        523.25, 659.25, 783.99, 1046.50,
        783.99, 659.25, 587.33, 783.99,
        523.25, 659.25, 880.00, 1046.50,
        880.00, 783.99, 659.25, 587.33,
    ]

    rng = np.random.default_rng(42)

    for s in range(total_steps):
        t0 = s * step_sec
        i0 = int(t0 * sr)
        if i0 >= n_samples:
            break

        # Kick on every quarter note (every 4 steps)
        if s % 4 == 0:
            dur_k = 0.14
            m = min(int(dur_k * sr), n_samples - i0)
            tk = np.arange(m) / sr
            freq = 150.0 * np.exp(-tk * 26.0) + 42.0
            phase = np.cumsum(2 * np.pi * freq / sr)
            env = np.exp(-tk * 18.0)
            buf[i0 : i0 + m] += 0.42 * np.sin(phase) * env

        # Snare on 4, 12 (backbeat)
        if s % 8 == 4:
            dur_s = 0.12
            m = min(int(dur_s * sr), n_samples - i0)
            ts = np.arange(m) / sr
            noise = rng.uniform(-1, 1, m)
            tone = np.sin(2 * np.pi * 210 * ts)
            env = np.exp(-ts * 24.0)
            buf[i0 : i0 + m] += (0.20 * noise + 0.14 * tone) * env

        # Crisp Hi-hat on offbeats
        if s % 2 == 1:
            dur_h = 0.045
            m = min(int(dur_h * sr), n_samples - i0)
            th = np.arange(m) / sr
            noise = rng.uniform(-1, 1, m)
            # simple high-pass diff
            hp = np.diff(noise, prepend=0)
            env = np.exp(-th * 55.0)
            buf[i0 : i0 + m] += 0.10 * hp * env

        # Saw-like pumping bass
        b_freq = bass_seq[(s // 2) % len(bass_seq)]
        dur_b = step_sec * 0.92
        m = min(int(dur_b * sr), n_samples - i0)
        tb = np.arange(m) / sr
        saw = 2.0 * ((tb * b_freq) % 1.0) - 1.0
        saw = 0.65 * saw + 0.35 * np.sin(2 * np.pi * b_freq * tb)
        # Sidechain duck on kick
        sc = 0.35 + 0.65 * min(1.0, (s % 4) * 0.5 + 0.2)
        env = np.exp(-tb * 7.0) * sc
        buf[i0 : i0 + m] += 0.18 * saw * env

        # Hyper lead arp (faster / octave up during FEVER window 5.2s..13.5s)
        a_freq = arp_seq[s % len(arp_seq)]
        if 5.2 <= t0 <= 13.5:
            a_freq *= 1.5
        dur_a = step_sec * 0.85
        m = min(int(dur_a * sr), n_samples - i0)
        ta = np.arange(m) / sr
        sq = np.sign(np.sin(2 * np.pi * a_freq * ta)) * 0.5 + np.sin(2 * np.pi * a_freq * ta) * 0.5
        env = np.exp(-ta * 14.0)
        buf[i0 : i0 + m] += 0.10 * sq * env

    # Hit-synced SFX
    scale = [523.25, 587.33, 659.25, 783.99, 880.00, 1046.50, 1174.66, 1318.51, 1567.98]
    for ev in events:
        et = ev["t"]
        kind = ev["kind"]
        i0 = int(et * sr)
        if i0 >= n_samples:
            continue
        if kind in ("god", "good"):
            combo = ev.get("combo", 1)
            f0 = scale[min(len(scale) - 1, combo - 1)]
            dur_e = 0.22
            m = min(int(dur_e * sr), n_samples - i0)
            te = np.arange(m) / sr
            sig = np.sin(2 * np.pi * f0 * te) + 0.5 * np.sin(2 * np.pi * (f0 * 1.5) * te)
            env = np.exp(-te * 14.0)
            buf[i0 : i0 + m] += 0.35 * sig * env
        elif kind == "fever":
            for k, ff in enumerate([523.25, 659.25, 783.99, 1046.50]):
                ik = i0 + int(k * 0.045 * sr)
                m = min(int(0.18 * sr), n_samples - ik)
                if m > 0:
                    te = np.arange(m) / sr
                    buf[ik : ik + m] += 0.28 * np.sin(2 * np.pi * ff * te) * np.exp(-te * 10.0)
        elif kind == "miss":
            dur_m = 0.32
            m = min(int(dur_m * sr), n_samples - i0)
            te = np.arange(m) / sr
            freq = 190.0 * np.exp(-te * 4.5)
            phase = np.cumsum(2 * np.pi * freq / sr)
            saw = 2.0 * ((phase / (2 * np.pi)) % 1.0) - 1.0
            buf[i0 : i0 + m] += 0.42 * saw * np.exp(-te * 6.0)

    # Soft limiter & normalize
    buf = np.tanh(buf * 1.15)
    pcm = np.int16(np.clip(buf, -0.98, 0.98) * 32767)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def generate_note_thumbnail(out_png: Path):
    """Generate 1280x670 eye-catching note.com thumbnail."""
    W, H = 1280, 670
    img = Image.new("RGB", (W, H), (10, 13, 19))
    draw = ImageDraw.Draw(img)

    # Diagonal dynamic accent stripes (no purple!)
    for i in range(-4, 14):
        x = i * 110
        draw.polygon([(x, 0), (x + 42, 0), (x - 190, H), (x - 232, H)], fill=(18, 24, 34))

    # Glowing target bar mockup in lower half
    bar_x, bar_y, bar_w, bar_h = 140, 470, 1000, 64
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=18, fill=(24, 30, 42))
    draw.rounded_rectangle([540, bar_y - 10, 740, bar_y + bar_h + 10], radius=12, fill=(0, 229, 255))
    draw.rounded_rectangle([615, bar_y - 16, 665, bar_y + bar_h + 16], radius=8, fill=(255, 212, 0))
    draw.rounded_rectangle([634, bar_y - 28, 646, bar_y + bar_h + 28], radius=6, fill=(255, 255, 255))

    font_tag = ImageFont.truetype(FONT_SANS, 34)
    font_title = ImageFont.truetype(FONT_SANS, 90)
    font_sub = ImageFont.truetype(FONT_SANS, 44)

    # Top badge
    badge = "DAY 01 // ブラウザで今すぐ無料プレイ"
    draw.rounded_rectangle([90, 68, 720, 132], radius=12, fill=(255, 46, 84))
    draw.text((116, 78), badge, font=font_tag, fill=(255, 255, 255))

    # Big Title
    draw.text(
        (90, 175),
        "99%が3回目でミスる",
        font=font_title,
        fill=(255, 255, 255),
        stroke_width=8,
        stroke_fill=(5, 7, 10),
    )
    draw.text(
        (90, 290),
        "0.01秒ジャスト斬り",
        font=font_title,
        fill=(255, 212, 0),
        stroke_width=8,
        stroke_fill=(5, 7, 10),
    )
    draw.text(
        (95, 405),
        "JUST SLASH 99｜BGM内蔵・脳汁コンボゲー",
        font=font_sub,
        fill=(0, 229, 255),
    )

    img.save(out_png)


def main():
    srv, port = start_static_server(GAME_DIR)
    debug_port = 9231
    browser_bin = find_browser()
    chrome_proc = subprocess.Popen(
        [
            browser_bin,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            f"--remote-debugging-port={debug_port}",
            "--window-size=540,960",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cdp = None
    try:
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list") as resp:
                    tabs = json.loads(resp.read().decode())
                    for tab in tabs:
                        if tab.get("type") == "page":
                            ws_url = tab["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                time.sleep(0.15)
        if not ws_url:
            raise RuntimeError("Failed to connect to headless Chromium CDP")

        cdp = SimpleCDP(ws_url)
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540,
            "height": 960,
            "deviceScaleFactor": 2,
            "mobile": True,
        })
        cdp.call("Page.enable")
        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/index.html?shorts=1"})
        time.sleep(1.2)

        fps = 30
        dt = 1.0 / fps
        total_dur = 19.5
        total_frames = int(total_dur * fps)

        frames_dir = OUT_DIR / "frames"
        frames_dir.mkdir(exist_ok=True)
        for old in frames_dir.glob("*.png"):
            old.unlink()

        font_big = ImageFont.truetype(FONT_SANS, 66)
        font_med = ImageFont.truetype(FONT_SANS, 44)
        font_small = ImageFont.truetype(FONT_SANS, 34)

        events = []
        # Choreographed Shorts script state
        started = False
        miss_count = 0
        cooldown = 0.0
        target_hits = 0

        # Timed caption segments: (t_start, t_end, pop_text, color)
        caption_plan = [
            (0.0, 2.2, "マジで1回やってみてｗ", (255, 255, 255)),
            (2.2, 4.8, "ど真ん中で脳汁ヤバい!!", (0, 229, 255)),
            (4.8, 7.6, "5連続でFEVER突入!!", (255, 212, 0)),
            (7.6, 10.6, "速すぎだろｗｗｗ", (255, 212, 0)),
            (10.6, 13.4, "赤は絶対押すな！！", (255, 70, 95)),
            (13.4, 16.5, "うわあああと1ミリ!!", (255, 70, 95)),
            (16.5, 19.6, "君は何点いける？ ▼", (0, 229, 255)),
        ]

        for f_idx in range(total_frames):
            t = f_idx * dt

            if not started and t >= 0.65:
                cdp.eval_js("window.__shortsAPI.start()")
                started = True
                cooldown = 0.25

            if started:
                cdp.eval_js(f"window.__shortsAPI.step({dt:.6f})")
                st = cdp.eval_js("window.__shortsAPI.getState()")

                if cooldown > 0:
                    cooldown -= dt

                if st["phase"] == "play" and cooldown <= 0:
                    dist = abs(st["cursor"] - st["targetCenter"])

                    # Before 13.4s: perform super satisfying GOD hits (and avoid traps)
                    if t < 13.4:
                        if not st["isTrap"] and dist <= 0.025:
                            prev_fever = st["fever"]
                            cdp.eval_js("window.__shortsAPI.hit()")
                            st2 = cdp.eval_js("window.__shortsAPI.getState()")
                            target_hits += 1
                            events.append({"t": t, "kind": "god", "combo": st2["combo"]})
                            if not prev_fever and st2["fever"]:
                                events.append({"t": t + 0.04, "kind": "fever"})
                            # Force next round to be an exciting fast or trap round at t ~ 10.4s
                            if 10.0 <= t <= 11.2 and not st2["isTrap"]:
                                cdp.eval_js("window.__shortsAPI.setRound({center: 0.55, width: 0.14, speed: 1.55, isTrap: true})")
                            cooldown = 0.20
                    else:
                        # Finale 13.4s..16.5s: nail-biting near misses to reach GAME OVER right around 16.2s!
                        if miss_count < 3 and (
                            (miss_count == 0 and t >= 13.9 and dist > 0.09)
                            or (miss_count == 1 and t >= 14.9 and dist > 0.09)
                            or (miss_count == 2 and t >= 15.85 and 0.07 <= dist <= 0.14)
                        ):
                            cdp.eval_js("window.__shortsAPI.hit()")
                            miss_count += 1
                            events.append({"t": t, "kind": "miss"})
                            cooldown = 0.35
                        elif miss_count < 3 and t >= 16.1:
                            cdp.eval_js("window.__shortsAPI.hit()")
                            miss_count += 1
                            events.append({"t": t, "kind": "miss"})
                            cooldown = 0.35

            shot = cdp.call("Page.captureScreenshot", {"format": "png"})
            raw_bytes = base64.b64decode(shot["data"])
            img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

            pop_text, pop_start, pop_color = "", t, (255, 255, 255)
            for s0, s1, txt, col in caption_plan:
                if s0 <= t < s1:
                    pop_text, pop_start, pop_color = txt, s0, col
                    break

            img = draw_caption_overlay(
                img=img,
                t=t,
                total_dur=total_dur,
                top_hook="99%が3回目でミスる鬼ゲー作ったｗ",
                pop_text=pop_text,
                pop_start=pop_start,
                pop_color=pop_color,
                bottom_cta="概要欄・プロフのURLから今すぐ無料プレイ ▼",
                font_big=font_big,
                font_med=font_med,
                font_small=font_small,
            )
            img.save(frames_dir / f"frame_{f_idx:04d}.png", compress_level=1)

        wav_path = OUT_DIR / "audio.wav"
        generate_audio(total_dur, events, wav_path)

        mp4_path = OUT_DIR / "day01_short.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frames_dir / "frame_%04d.png"),
                "-i",
                str(wav_path),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "19",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-shortest",
                "-movflags",
                "+faststart",
                str(mp4_path),
            ],
            check=True,
        )

        thumb_path = OUT_DIR / "note_thumbnail.png"
        generate_note_thumbnail(thumb_path)
        print(f"Generated: {mp4_path} ({mp4_path.stat().st_size // 1024} KB)")
        print(f"Generated: {thumb_path} ({thumb_path.stat().st_size // 1024} KB)")

    finally:
        if cdp:
            cdp.close()
        chrome_proc.terminate()
        srv.shutdown()


if __name__ == "__main__":
    main()
