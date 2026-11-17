#!/usr/bin/env python3
"""
Day 03 YouTube Shorts (1080x1920, 60fps, 18.0s) + Thumbnail Generator.
Series: 100日後にバズるゲームを作る男【ゲーム3日目】
Features:
- Deterministic 60fps capture from games/day03-blink-slash/index.html?shorts=1
- Dynamic camera zoom & impact screen shake clipped cleanly inside the game frame
- Zero overlap between video captions and game HUD
- Japanese neural voice narration (edge-tts ja-JP-KeitaNeural, gTTS fallback) + 144 BPM synth BGM + synced SFX
- 1280x670 thumbnail with explicit "ゲーム3日目" + live gameplay preview
"""

import asyncio
import base64
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
import tempfile
import threading
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = ROOT / "games" / "day03-blink-slash"
OUT_DIR = ROOT / "shorts" / "day03" / "output"
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
    out = subprocess.check_output(
        ["fc-match", "-f", "%{file}", "Noto Sans CJK JP:bold"], text=True
    ).strip()
    if out and os.path.exists(out):
        return out
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
                raw = bytearray(self._recv_exact(length))
                for i in range(length):
                    raw[i] ^= mask[i % 4]
                data = bytes(raw)
            else:
                data = self._recv_exact(length)
            if opcode == 0x8:
                raise ConnectionError("WebSocket closed by server")
            if opcode == 0x9:
                continue
            return data.decode("utf-8", errors="replace")

    def call(self, method: str, params=None):
        self.msg_id += 1
        mid = self.msg_id
        msg = json.dumps({"id": mid, "method": method, "params": params or {}})
        self._send_frame(msg)
        while True:
            resp = json.loads(self._recv_frame())
            if resp.get("id") == mid:
                if "error" in resp:
                    raise RuntimeError(f"CDP error {method}: {resp['error']}")
                return resp.get("result", {})

    def eval_js(self, expr: str):
        res = self.call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": False},
        )
        val = res.get("result", {})
        if "value" in val:
            return val["value"]
        return None

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
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


NARRATION_CUES = [
    (0.08, "100日後にバズるゲームを作る男、3日目！"),
    (2.35, "指を置くだけで時間が止まる、瞬間ワープ斬りアクション！"),
    (5.55, "稼いだコアで4つの刀スタイルや強化チップ、実績までやり込み満載！"),
    (9.45, "雷電スタイルに持ち替えて、Wave5のボスを一閃で粉砕！"),
    (14.30, "スマホで今すぐ無料プレイ！リンクはプロフィールから！"),
]


def synthesize_tts_line(text: str, out_wav: Path, sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")

    try:
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(
                text, voice="ja-JP-KeitaNeural", rate="+15%", pitch="+2Hz"
            )
            await comm.save(str(tmp_mp3))

        asyncio.run(_run())
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_mp3),
                "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        tmp_mp3.unlink(missing_ok=True)
        return True
    except Exception:
        tmp_mp3.unlink(missing_ok=True)

    try:
        if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
            os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"
        from gtts import gTTS

        gTTS(text=text, lang="ja").save(str(tmp_mp3))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_mp3),
                "-af", "atempo=1.24",
                "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        tmp_mp3.unlink(missing_ok=True)
        return True
    except Exception as exc:
        print(f"TTS fallback warning for '{text}': {exc}")
        tmp_mp3.unlink(missing_ok=True)
        return False


def load_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def generate_audio(total_dur: float, events: list, wav_path: Path):
    sr = 44100
    n_samples = int(total_dur * sr)
    bgm = np.zeros(n_samples, dtype=np.float32)
    sfx = np.zeros(n_samples, dtype=np.float32)
    voice = np.zeros(n_samples, dtype=np.float32)

    # 144 BPM cyber katana synthwave BGM
    bpm = 144.0
    step_dur = 60.0 / bpm / 2.0
    bass_notes = [110.0, 110.0, 130.81, 146.83, 110.0, 164.81, 146.83, 130.81]
    arp_notes = [220.0, 329.63, 440.0, 523.25, 493.88, 440.0, 329.63, 392.0]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        s_start = int(i * step_dur * sr)
        s_len = min(int(step_dur * 0.92 * sr), n_samples - s_start)
        if s_len <= 0:
            break
        lt = np.arange(s_len, dtype=np.float32) / sr
        bf = bass_notes[i % len(bass_notes)]
        af = arp_notes[(i // 2) % len(arp_notes)]

        bass_wave = np.tanh(2.4 * np.sin(2.0 * math.pi * bf * lt)) * np.exp(-lt * 10.0) * 0.14
        arp_wave = np.sin(2.0 * math.pi * af * lt) * np.exp(-lt * 14.0) * 0.08

        kick = np.zeros(s_len, dtype=np.float32)
        if i % 2 == 0:
            kf = 130.0 * np.exp(-lt * 22.0) + 44.0
            kick = np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * np.exp(-lt * 16.0) * 0.24

        hat = np.zeros(s_len, dtype=np.float32)
        if i % 2 == 1:
            rng = np.random.default_rng(seed=i + 303)
            hat = rng.uniform(-1.0, 1.0, s_len).astype(np.float32) * np.exp(-lt * 60.0) * 0.05

        bgm[s_start : s_start + s_len] += bass_wave + arp_wave + kick + hat

    # Frame-accurate gameplay SFX
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        idx0 = int(t0 * sr)
        if idx0 >= n_samples:
            continue
        kind = ev.get("type")
        if kind == "slash":
            dur = int(0.16 * sr)
            e_len = min(dur, n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            f = np.linspace(980.0, 210.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.tanh(1.9 * np.sin(2.0 * math.pi * np.cumsum(f) / sr)) * np.exp(-lt * 18.0) * 0.30
        elif kind == "just":
            for k, f in enumerate((880.0, 1318.5, 1760.0)):
                k0 = idx0 + int(k * 0.04 * sr)
                e_len = min(int(0.18 * sr), n_samples - k0)
                if e_len > 0:
                    lt = np.arange(e_len, dtype=np.float32) / sr
                    sfx[k0 : k0 + e_len] += np.sin(2.0 * math.pi * f * lt) * np.exp(-lt * 14.0) * 0.25
        elif kind in ("bomb", "boss_kill"):
            dur = int(0.40 * sr)
            e_len = min(dur, n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            f = 195.0 * np.exp(-lt * 9.0) + 38.0
            rng = np.random.default_rng(seed=int(t0 * 1000) + 7)
            boom = np.sin(2.0 * math.pi * np.cumsum(f) / sr) * np.exp(-lt * 7.0) * 0.44
            noise = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 14.0) * 0.16
            sfx[idx0 : idx0 + e_len] += boom + noise
        elif kind == "lightning":
            dur = int(0.14 * sr)
            e_len = min(dur, n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * 1174.66 * lt) * np.exp(-lt * 22.0) * 0.20

    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp_dir = Path(tempfile.mkdtemp(prefix="tts_day03_"))
    try:
        for idx, (cue_t, line_txt) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp_dir / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.72
                s0 = int(cue_t * sr)
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.36)
    finally:
        shutil.rmtree(tts_tmp_dir, ignore_errors=True)

    mixed = bgm * duck + sfx * 0.85 + voice
    mixed = np.tanh(mixed * 1.15) * 0.88
    pcm = np.clip(mixed * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def composite_frame(
    game_img: Image.Image,
    t: float,
    total_dur: float,
    zoom_boost: float,
    shake_px: float,
    pop_text: str,
    pop_start: float,
    pop_color: tuple,
    font_big,
    font_med,
    font_small,
    rng: random.Random,
) -> Image.Image:
    W_OUT, H_OUT = 1080, 1920
    canvas = Image.new("RGB", (W_OUT, H_OUT), (6, 9, 17))
    draw = ImageDraw.Draw(canvas)

    for y in range(0, 260, 4):
        alpha = int(32 * (1 - y / 260))
        draw.rectangle([(0, y), (W_OUT, y + 4)], fill=(12, 22 + alpha, 42 + alpha))

    vp_w, vp_h = 920, 1360
    vp_x = (W_OUT - vp_w) // 2
    vp_y = 268

    if game_img.size != (vp_w, vp_h):
        game_img = game_img.resize((vp_w, vp_h), Image.Resampling.LANCZOS)

    scale = 1.0 + zoom_boost
    if scale > 1.001 or shake_px > 0.3:
        zw = int(round(vp_w * scale))
        zh = int(round(vp_h * scale))
        zoomed = game_img.resize((zw, zh), Image.Resampling.BILINEAR)
        sx = rng.uniform(-shake_px, shake_px)
        sy = rng.uniform(-shake_px, shake_px)
        cx = max(0.0, min(float(zw - vp_w), (zw - vp_w) / 2.0 + sx))
        cy = max(0.0, min(float(zh - vp_h), (zh - vp_h) / 2.0 + sy))
        cropped = zoomed.crop((int(cx), int(cy), int(cx) + vp_w, int(cy) + vp_h))
    else:
        cropped = game_img

    draw.rounded_rectangle(
        [(vp_x - 4, vp_y - 4), (vp_x + vp_w + 4, vp_y + vp_h + 4)],
        radius=24,
        outline=(0, 229, 255),
        width=3,
    )
    canvas.paste(cropped, (vp_x, vp_y))

    badge_txt = "100日後にバズるゲームを作る男｜ゲーム3日目"
    bbox_b = draw.textbbox((0, 0), badge_txt, font=font_small)
    bw = bbox_b[2] - bbox_b[0]
    bx = (W_OUT - bw) // 2
    draw.rounded_rectangle(
        [(bx - 22, 34), (bx + bw + 22, 90)],
        radius=26,
        fill=(20, 30, 50),
        outline=(255, 212, 0),
        width=2,
    )
    draw.text((bx, 42), badge_txt, font=font_small, fill=(255, 212, 0))

    if pop_text:
        age = t - pop_start
        pop_scale = 1.0 + 0.10 * math.exp(-age * 16.0)
        fnt = font_big if len(pop_text) <= 14 else font_med
        tb = draw.textbbox((0, 0), pop_text, font=fnt)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        tx = (W_OUT - tw) // 2
        ty = 175 - th // 2
        if pop_scale > 1.005:
            ty -= int((pop_scale - 1.0) * 35)
        draw.text(
            (tx, ty),
            pop_text,
            font=fnt,
            fill=pop_color,
            stroke_width=8,
            stroke_fill=(5, 7, 12),
        )

    cta_line1 = "今すぐスマホで無料プレイ"
    cta_line2 = "チャンネルのプロフURLから遊べます ▼"
    b1 = draw.textbbox((0, 0), cta_line1, font=font_med)
    b2 = draw.textbbox((0, 0), cta_line2, font=font_small)
    draw.rounded_rectangle(
        [(130, 1666), (W_OUT - 130, 1812)],
        radius=22,
        fill=(18, 25, 40),
        outline=(0, 229, 255),
        width=2,
    )
    draw.text(((W_OUT - (b1[2] - b1[0])) // 2, 1682), cta_line1, font=font_med, fill=(255, 212, 0))
    draw.text(((W_OUT - (b2[2] - b2[0])) // 2, 1746), cta_line2, font=font_small, fill=(225, 242, 255))

    prog = min(1.0, max(0.0, t / total_dur))
    draw.rectangle([(80, 1858), (W_OUT - 80, 1872)], fill=(26, 34, 52))
    draw.rectangle([(80, 1858), (80 + int((W_OUT - 160) * prog), 1872)], fill=(0, 229, 255))

    return canvas


def generate_thumbnail(action_game_img: Image.Image, out_png: Path):
    """Generate 1280x670 crisp thumbnail with explicit 'ゲーム3日目' + live gameplay preview."""
    W, H = 1280, 670
    img = Image.new("RGB", (W, H), (7, 11, 20))
    draw = ImageDraw.Draw(img)

    for gx in range(0, W, 48):
        draw.line([(gx, 0), (gx, H)], fill=(18, 28, 46), width=1)
    for gy in range(0, H, 48):
        draw.line([(0, gy), (W, gy)], fill=(18, 28, 46), width=1)

    card_w, card_h = 370, 548
    cx, cy = 838, 61
    preview = action_game_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
    draw.rounded_rectangle(
        [(cx - 5, cy - 5), (cx + card_w + 5, cy + card_h + 5)],
        radius=22,
        fill=(14, 20, 32),
        outline=(0, 229, 255),
        width=4,
    )
    img.paste(preview, (cx, cy))

    font_tag = ImageFont.truetype(FONT_SANS, 34)
    font_day = ImageFont.truetype(FONT_SANS, 96)
    font_title = ImageFont.truetype(FONT_SANS, 70)
    font_sub = ImageFont.truetype(FONT_SANS, 36)

    series_txt = "100日後にバズるゲームを作る男"
    sb = draw.textbbox((0, 0), series_txt, font=font_tag)
    draw.rounded_rectangle([(68, 72), (68 + (sb[2] - sb[0]) + 44, 134)], radius=14, fill=(255, 212, 0))
    draw.text((90, 82), series_txt, font=font_tag, fill=(10, 14, 22))

    draw.text(
        (70, 174),
        "ゲーム3日目",
        font=font_day,
        fill=(255, 255, 255),
        stroke_width=8,
        stroke_fill=(6, 9, 15),
    )

    draw.text(
        (72, 314),
        "BLINK SLASH 99",
        font=font_title,
        fill=(0, 229, 255),
        stroke_width=5,
        stroke_fill=(6, 9, 15),
    )

    draw.text(
        (72, 414),
        "時間停止ワープ斬り × 刀スタイル解放",
        font=font_sub,
        fill=(235, 245, 255),
    )

    pills = [("見切り無双", (59, 255, 156)), ("4種の刀&実績12", (255, 140, 36)), ("完全無料", (255, 212, 0))]
    px = 72
    for label, col in pills:
        pb = draw.textbbox((0, 0), label, font=font_tag)
        pw = pb[2] - pb[0]
        draw.rounded_rectangle([(px, 508), (px + pw + 32, 566)], radius=14, fill=(18, 27, 42), outline=col, width=2)
        draw.text((px + 16, 517), label, font=font_tag, fill=col)
        px += pw + 46

    img.save(out_png)


def main():
    srv, port = start_static_server(GAME_DIR)
    debug_port = 9233
    browser_bin = find_browser()
    profile_dir = tempfile.mkdtemp(prefix="cdp_day03_")
    chrome_log_path = Path(profile_dir) / "chrome.log"
    chrome_log_fh = open(chrome_log_path, "wb")
    chrome_env = os.environ.copy()
    chrome_env.pop("DBUS_SESSION_BUS_ADDRESS", None)

    chrome_proc = subprocess.Popen(
        [
            browser_bin,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={debug_port}",
            "--window-size=460,680",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=chrome_log_fh,
        env=chrome_env,
    )

    cdp = None
    try:
        ws_url = None
        for _ in range(80):
            if chrome_proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=1) as resp:
                    tabs = json.loads(resp.read().decode())
                    for tab in tabs:
                        if tab.get("type") == "page":
                            ws_url = tab["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                time.sleep(0.2)

        if not ws_url:
            chrome_proc.terminate()
            chrome_log_fh.flush()
            err_txt = chrome_log_path.read_text(errors="replace") if chrome_log_path.exists() else ""
            raise RuntimeError(f"Failed to connect to Chrome CDP ({browser_bin}): {err_txt[:800]}")

        cdp = SimpleCDP(ws_url)
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 460,
            "height": 680,
            "deviceScaleFactor": 2,
            "mobile": True,
        })
        cdp.call("Page.enable")
        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/index.html?shorts=1"})
        time.sleep(1.2)
        cdp.eval_js("window.__SHORTS_MANUAL__ = true;")

        fps = 60
        dt_ms = 1000.0 / fps
        dt_sec = 1.0 / fps
        total_dur = 18.0
        total_frames = int(total_dur * fps)

        frames_dir = OUT_DIR / "frames"
        frames_dir.mkdir(exist_ok=True)
        for old in frames_dir.glob("*.png"):
            old.unlink()

        font_big = ImageFont.truetype(FONT_SANS, 62)
        font_med = ImageFont.truetype(FONT_SANS, 44)
        font_small = ImageFont.truetype(FONT_SANS, 34)

        caption_plan = [
            (0.0, 2.30, "3日目は時間停止ワープ斬り!!", (255, 255, 255)),
            (2.30, 5.50, "見切り×連続斬りが爽快!!", (0, 229, 255)),
            (5.50, 9.40, "刀スタイル＆実績でやり込み!!", (59, 255, 156)),
            (9.40, 14.25, "雷電ブレードでBOSS粉砕!!", (255, 212, 0)),
            (14.25, 18.1, "何Waveまで生き残れる？ ▼", (0, 229, 255)),
        ]

        all_events = []
        zoom_boost = 0.0
        shake_px = 0.0
        rng = random.Random(20261117)
        thumb_action_img = None
        thumb_best_score = -1.0

        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            step_res = cdp.eval_js(f"window.__SHORTS_STEP__({dt_ms:.6f})") or {}
            evs = step_res.get("events", [])
            for ev in evs:
                ev["t"] = t
                all_events.append(ev)
                if ev.get("type") in ("bomb", "boss_kill"):
                    zoom_boost = max(zoom_boost, 0.068)
                    shake_px = max(shake_px, 15.0)
                elif ev.get("type") == "just":
                    zoom_boost = max(zoom_boost, 0.05)
                    shake_px = max(shake_px, 10.0)
                elif ev.get("type") == "slash" and ev.get("kills", 0) > 0:
                    zoom_boost = max(zoom_boost, 0.035)
                    shake_px = max(shake_px, 6.0)

            zoom_boost *= 0.90
            shake_px *= 0.80

            shot = cdp.call("Page.captureScreenshot", {"format": "png"})
            game_img = Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB")

            if t < 5.2 or t >= 8.6:
                action_score = 1.0 + sum(
                    22.0 if ev.get("type") in ("bomb", "boss_kill")
                    else 15.0 if ev.get("type") == "just"
                    else 6.0 * ev.get("kills", 0)
                    for ev in evs
                )
                if 1.2 <= t <= 2.2 or 9.5 <= t <= 13.5:
                    action_score += 5.0
                if action_score >= thumb_best_score:
                    thumb_best_score = action_score
                    thumb_action_img = game_img.copy()

            pop_text, pop_start, pop_color = "", t, (255, 255, 255)
            for s0, s1, txt, col in caption_plan:
                if s0 <= t < s1:
                    pop_text, pop_start, pop_color = txt, s0, col
                    break

            frame = composite_frame(
                game_img=game_img,
                t=t,
                total_dur=total_dur,
                zoom_boost=zoom_boost,
                shake_px=shake_px,
                pop_text=pop_text,
                pop_start=pop_start,
                pop_color=pop_color,
                font_big=font_big,
                font_med=font_med,
                font_small=font_small,
                rng=rng,
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.png", compress_level=1)

        wav_path = OUT_DIR / "audio.wav"
        generate_audio(total_dur, all_events, wav_path)

        mp4_path = OUT_DIR / "day03_short.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%04d.png"),
                "-i", str(wav_path),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-shortest",
                "-movflags", "+faststart",
                str(mp4_path),
            ],
            check=True,
        )

        thumb_path = OUT_DIR / "note_thumbnail.png"
        generate_thumbnail(thumb_action_img or game_img, thumb_path)
        print(f"Generated 60fps Short: {mp4_path} ({mp4_path.stat().st_size // 1024} KB)")
        print(f"Generated Thumbnail:   {thumb_path} ({thumb_path.stat().st_size // 1024} KB)")
        print(f"Recorded events: {len(all_events)}")

    finally:
        if cdp:
            cdp.close()
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=5)
        except Exception:
            chrome_proc.kill()
        chrome_log_fh.close()
        shutil.rmtree(profile_dir, ignore_errors=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
