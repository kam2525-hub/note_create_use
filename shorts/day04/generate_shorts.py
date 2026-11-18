#!/usr/bin/env python3
"""
Day 04 YouTube Shorts (1080x1920, 60fps, 18.0s, FULL-BLEED 3D) + Thumbnail Generator.
Anti-AI-template layout:
- Edge-to-edge 1080x1920 native 3D gameplay (NO cyan border box, NO dark letterbox)
- Natural floating kinetic captions (NO top series billboard, NO permanent bottom CTA box)
- High-density popping/explosion SFX + Japanese voice narration + bright studio thumbnail
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
GAME_DIR = ROOT / "games" / "day04-sweep-rush"
OUT_DIR = ROOT / "shorts" / "day04" / "output"
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


# Natural, punchy Japanese voice narration (short sentences, zero robotic hype)
NARRATION_CUES = [
    (0.05, "散らかった部屋を一気に掃除するゲーム作った！"),
    (2.45, "洗剤ボムを巻き込むと、周りごと大爆発！"),
    (5.65, "クリアしたら強化を1つ選んで、"),
    (8.15, "マシンが巨大化！あとは部屋ごと吹き飛ばすだけ！"),
    (14.50, "スマホでそのまま遊べるよ！"),
]


def synthesize_tts_line(text: str, out_wav: Path, sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")

    try:
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(
                text, voice="ja-JP-KeitaNeural", rate="+16%", pitch="+2Hz"
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

    # 142 BPM upbeat marimba-house arcade BGM
    bpm = 142.0
    step_dur = 60.0 / bpm / 2.0
    bass_notes = [130.81, 130.81, 164.81, 196.0, 146.83, 146.83, 196.0, 164.81]
    lead_notes = [523.25, 659.25, 783.99, 1046.5, 880.0, 783.99, 659.25, 587.33]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        s_start = int(i * step_dur * sr)
        s_len = min(int(step_dur * 0.90 * sr), n_samples - s_start)
        if s_len <= 0:
            break
        lt = np.arange(s_len, dtype=np.float32) / sr
        bf = bass_notes[i % len(bass_notes)]
        lf = lead_notes[(i // 2) % len(lead_notes)]

        bass = np.sin(2.0 * math.pi * bf * lt) * np.exp(-lt * 9.0) * 0.14
        marimba = np.sin(2.0 * math.pi * lf * lt) * np.exp(-lt * 18.0) * 0.08

        kick = np.zeros(s_len, dtype=np.float32)
        if i % 2 == 0:
            kf = 120.0 * np.exp(-lt * 24.0) + 44.0
            kick = np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * np.exp(-lt * 17.0) * 0.22

        hat = np.zeros(s_len, dtype=np.float32)
        if i % 2 == 1:
            rng = np.random.default_rng(seed=i + 404)
            hat = rng.uniform(-1.0, 1.0, s_len).astype(np.float32) * np.exp(-lt * 65.0) * 0.045

        bgm[s_start : s_start + s_len] += bass + marimba + kick + hat

    # Frame-accurate ASMR pop + explosion SFX
    penta = [392.0, 440.0, 493.88, 587.33, 659.25, 783.99, 880.0, 987.77, 1174.66, 1318.51]
    last_pop_t = -1.0
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        idx0 = int(t0 * sr)
        if idx0 >= n_samples:
            continue
        kind = ev.get("type")
        if kind == "pop":
            if t0 - last_pop_t < 0.025:
                continue
            last_pop_t = t0
            c = int(ev.get("combo", 1))
            f0 = penta[c % len(penta)]
            e_len = min(int(0.085 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(f0, f0 * 1.24, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 28.0) * 0.24
        elif kind == "bomb":
            e_len = min(int(0.36 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            f = 185.0 * np.exp(-lt * 9.0) + 40.0
            rng = np.random.default_rng(seed=int(t0 * 1000) + 4)
            boom = np.sin(2.0 * math.pi * np.cumsum(f) / sr) * np.exp(-lt * 8.0) * 0.42
            fizz = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 14.0) * 0.14
            sfx[idx0 : idx0 + e_len] += boom + fizz
        elif kind in ("vortex", "fever"):
            for k, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
                k0 = idx0 + int(k * 0.045 * sr)
                e_len = min(int(0.16 * sr), n_samples - k0)
                if e_len > 0:
                    lt = np.arange(e_len, dtype=np.float32) / sr
                    sfx[k0 : k0 + e_len] += np.sin(2.0 * math.pi * f * lt) * np.exp(-lt * 15.0) * 0.22
        elif kind == "stage_clear":
            for k, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
                k0 = idx0 + int(k * 0.06 * sr)
                e_len = min(int(0.20 * sr), n_samples - k0)
                if e_len > 0:
                    lt = np.arange(e_len, dtype=np.float32) / sr
                    sfx[k0 : k0 + e_len] += np.sin(2.0 * math.pi * f * lt) * np.exp(-lt * 12.0) * 0.26

    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp_dir = Path(tempfile.mkdtemp(prefix="tts_day04_"))
    try:
        for idx, (cue_t, line_txt) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp_dir / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.74
                s0 = int(cue_t * sr)
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.36)
    finally:
        shutil.rmtree(tts_tmp_dir, ignore_errors=True)

    mixed = bgm * duck + sfx * 0.86 + voice
    mixed = np.tanh(mixed * 1.15) * 0.88
    pcm = np.clip(mixed * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def overlay_human_captions(
    frame_img: Image.Image,
    t: float,
    pop_text: str,
    pop_start: float,
    pop_color: tuple,
    end_cta: str,
    font_big,
    font_med,
    font_small,
) -> Image.Image:
    """
    Full-bleed 1080x1920 compositor with ZERO boxy frames/banners.
    Captions float naturally like creator-edited TikTok/Shorts subtitles.
    """
    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.LANCZOS)

    img = frame_img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Subtle creator subtitle in upper-mid safe zone (below game HUD, above center action)
    if pop_text:
        age = max(0.0, t - pop_start)
        pop_lift = int(14 * math.exp(-age * 16.0))
        fnt = font_big if len(pop_text) <= 13 else font_med
        tb = draw.textbbox((0, 0), pop_text, font=fnt, stroke_width=10)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        tx = (W - tw) // 2
        ty = 310 - th // 2 - pop_lift

        # Soft shadow + bold readable outline (classic Japanese creator telop look)
        draw.text((tx + 4, ty + 6), pop_text, font=fnt, fill=(15, 24, 42, 165))
        draw.text(
            (tx, ty),
            pop_text,
            font=fnt,
            fill=pop_color,
            stroke_width=10,
            stroke_fill=(20, 30, 48),
        )

    # Clean, non-intrusive end pointer ONLY in last 3.2 seconds (upper-safe zone)
    if end_cta:
        tb = draw.textbbox((0, 0), end_cta, font=font_small, stroke_width=6)
        tw = tb[2] - tb[0]
        tx = (W - tw) // 2
        ty = 390
        draw.text(
            (tx, ty),
            end_cta,
            font=font_small,
            fill=(255, 255, 255),
            stroke_width=6,
            stroke_fill=(20, 30, 48),
        )

    return img.convert("RGB")


def generate_thumbnail(action_img: Image.Image, out_png: Path):
    """Bright, playful studio-style 1280x670 thumbnail (zero dark cyber grid)."""
    W, H = 1280, 670
    img = Image.new("RGB", (W, H), (235, 245, 255))
    draw = ImageDraw.Draw(img)

    # Soft sky-to-cream vertical studio gradient
    for y in range(0, H, 4):
        frac = y / H
        r = int(206 + 44 * frac)
        g = int(233 + 19 * frac)
        b = int(255)
        draw.rectangle([(0, y), (W, y + 4)], fill=(r, g, b))

    # Subtle bright polka dots in background (playful toy aesthetic)
    for gx in range(40, W, 96):
        for gy in range(40, H, 96):
            draw.ellipse([(gx - 4, gy - 4), (gx + 4, gy + 4)], fill=(192, 220, 248))

    # Right-side crisp 3D gameplay card with soft drop shadow (no neon border!)
    card_w, card_h = 330, 586
    cx, cy = 876, 42
    draw.rounded_rectangle(
        [(cx + 10, cy + 14), (cx + card_w + 10, cy + card_h + 14)],
        radius=28,
        fill=(182, 204, 228),
    )
    preview = action_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
    mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (card_w, card_h)], radius=26, fill=255)
    img.paste(preview, (cx, cy), mask)
    draw.rounded_rectangle(
        [(cx, cy), (cx + card_w, cy + card_h)],
        radius=26,
        outline=(255, 255, 255),
        width=6,
    )

    font_tag = ImageFont.truetype(FONT_SANS, 32)
    font_hero = ImageFont.truetype(FONT_SANS, 82)
    font_title = ImageFont.truetype(FONT_SANS, 58)
    font_sub = ImageFont.truetype(FONT_SANS, 34)

    # Day 4 badge
    badge_txt = "ゲーム4日目｜ブラウザで今すぐ遊べる"
    sb = draw.textbbox((0, 0), badge_txt, font=font_tag)
    draw.rounded_rectangle([(68, 72), (68 + (sb[2] - sb[0]) + 42, 130)], radius=18, fill=(255, 190, 11))
    draw.text((89, 80), badge_txt, font=font_tag, fill=(27, 37, 56))

    # Bold hook headline
    draw.text((68, 172), "部屋中の3Dブロックを", font=font_hero, fill=(27, 37, 56))
    draw.text((68, 272), "一撃でお掃除無双！", font=font_hero, fill=(255, 90, 95))

    draw.text((70, 396), "SWEEP RUSH", font=font_title, fill=(47, 128, 237))
    draw.text((70, 470), "洗剤ボム連鎖 × 3択お掃除ビルド", font=font_sub, fill=(75, 92, 118))

    pills = [("3D爽快アクション", (18, 196, 139)), ("巨大化インフレ", (255, 136, 0)), ("完全無料", (47, 128, 237))]
    px = 70
    for label, col in pills:
        pb = draw.textbbox((0, 0), label, font=font_tag)
        pw = pb[2] - pb[0]
        draw.rounded_rectangle([(px, 545), (px + pw + 34, 601)], radius=16, fill=(255, 255, 255), outline=col, width=3)
        draw.text((px + 17, 553), label, font=font_tag, fill=col)
        px += pw + 48

    img.save(out_png)


def main():
    srv, port = start_static_server(GAME_DIR)
    debug_port = 9234
    browser_bin = find_browser()
    profile_dir = tempfile.mkdtemp(prefix="cdp_day04_")
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
            "--window-size=540,960",
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
        # Native 540x960 @2x = 1080x1920 full-bleed!
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540,
            "height": 960,
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

        font_big = ImageFont.truetype(FONT_SANS, 66)
        font_med = ImageFont.truetype(FONT_SANS, 48)
        font_small = ImageFont.truetype(FONT_SANS, 38)

        caption_plan = [
            (0.0, 2.40, "部屋を爆速でお掃除!!", (255, 255, 255)),
            (2.40, 5.55, "洗剤ボムで大爆発!!", (255, 214, 51)),
            (5.55, 8.05, "3択でマシン強化!!", (102, 240, 190)),
            (8.05, 14.40, "ブレード巨大化で一掃ｗ", (255, 214, 51)),
            (14.40, 18.10, "何％まで掃除できる？", (255, 255, 255)),
        ]

        all_events = []
        thumb_action_img = None
        thumb_best_score = -1.0

        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            step_res = cdp.eval_js(f"window.__SHORTS_STEP__({dt_ms:.6f})") or {}
            evs = step_res.get("events", [])
            for ev in evs:
                ev["t"] = t
                all_events.append(ev)

            shot = cdp.call("Page.captureScreenshot", {"format": "png"})
            game_img = Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB")

            if step_res.get("phase") == "play" and 25 <= step_res.get("pct", 0) <= 72:
                action_score = 1.0 + sum(
                    25.0 if ev.get("type") == "bomb"
                    else 12.0 if ev.get("type") == "vortex"
                    else 2.0
                    for ev in evs
                )
                if 13.0 <= t <= 16.5:
                    action_score += 8.0
                if action_score >= thumb_best_score:
                    thumb_best_score = action_score
                    thumb_action_img = game_img.copy()

            pop_text, pop_start, pop_color = "", t, (255, 255, 255)
            for s0, s1, txt, col in caption_plan:
                if s0 <= t < s1:
                    pop_text, pop_start, pop_color = txt, s0, col
                    break

            end_cta = "リンクから無料で遊べるよ ▼" if t >= 14.8 else ""
            frame = overlay_human_captions(
                frame_img=game_img,
                t=t,
                pop_text=pop_text,
                pop_start=pop_start,
                pop_color=pop_color,
                end_cta=end_cta,
                font_big=font_big,
                font_med=font_med,
                font_small=font_small,
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.png", compress_level=1)

        wav_path = OUT_DIR / "audio.wav"
        generate_audio(total_dur, all_events, wav_path)

        mp4_path = OUT_DIR / "day04_short.mp4"
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
