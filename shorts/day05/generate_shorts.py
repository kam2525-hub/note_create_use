#!/usr/bin/env python3
"""
Day 05 YouTube Shorts (1080x1920, 60fps, 14.0s, FULL-BLEED + FULL AUDIO) + Note Thumbnail Generator.
Retention-engineered pacing:
- 0.00s..1.00s (FIRST-SECOND HOOK): Immediate blaster fire flipping RED -6 gate to BLUE + pass!
- High-energy 152 BPM arcade synthwave BGM (accelerates with double-time hats at x4 tsunami)
- Frame-accurate SFX (shots, gate ticks, blue-flip chime, x3/x4 bass drop, bubble-wrap pops, boss explosion)
- Energetic Japanese voice narration with automatic BGM ducking + floating kinetic captions
"""

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
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = ROOT / "games" / "day05-crowd-999"
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


# High-retention Japanese narration cues timed cleanly around peaks
NARRATION_CUES = [
    (0.02, "あの広告の増殖ゲーム、ガチで作ってみた！"),
    (2.15, "赤を撃って青に反転！3ウェイ砲からの、"),
    (4.35, "掛ける3で一気に大増殖！"),
    (6.70, "巨人召喚からの掛ける4で、400人近くの大津波！"),
    (10.30, "巨大ボスも一瞬で粉砕！何人増やせる？"),
]


def synthesize_tts_line(text: str, out_wav: Path, sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"
    try:
        from gtts import gTTS

        gTTS(text=text, lang="ja").save(str(tmp_mp3))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_mp3),
                "-af", "atempo=1.30,asetrate=44100*0.97,aresample=44100",
                "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        tmp_mp3.unlink(missing_ok=True)
        return True
    except Exception as exc:
        print(f"TTS warning for '{text}': {exc}")
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

    # 152 BPM Hyper-Dopamine Arcade Synthwave BGM!
    bpm = 152.0
    step_dur = 60.0 / bpm / 2.0  # 8th notes
    # Uplifting minor-to-heroic progression
    bass_prog = [110.0, 110.0, 130.81, 146.83, 164.81, 164.81, 146.83, 196.0]
    arp_notes = [440.0, 523.25, 659.25, 880.0, 783.99, 659.25, 587.33, 1046.5]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        t_step = i * step_dur
        s0 = int(t_step * sr)
        s_len = min(int(step_dur * 0.92 * sr), n_samples - s0)
        if s_len <= 0:
            break
        lt = np.arange(s_len, dtype=np.float32) / sr
        bf = bass_prog[i % len(bass_prog)]
        af = arp_notes[i % len(arp_notes)] * (1.25 if t_step > 7.5 else 1.0)

        # Punchy saw-like driving bass
        bass = (np.sin(2.0 * math.pi * bf * lt) + 0.35 * np.sin(4.0 * math.pi * bf * lt)) * np.exp(-lt * 10.0) * 0.14
        # Sparkly lead pluck
        arp = np.sin(2.0 * math.pi * af * lt) * np.exp(-lt * 20.0) * (0.09 if t_step > 7.5 else 0.065)

        # Kick every quarter note (even steps)
        kick = np.zeros(s_len, dtype=np.float32)
        if i % 2 == 0:
            kf = 138.0 * np.exp(-lt * 26.0) + 46.0
            kick = np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * np.exp(-lt * 16.0) * 0.24

        # Crisp offbeat hats (doubled after x4 tsunami!)
        hat = np.zeros(s_len, dtype=np.float32)
        if i % 2 == 1 or t_step > 7.5:
            rng = np.random.default_rng(seed=i + 999)
            hat = rng.uniform(-1.0, 1.0, s_len).astype(np.float32) * np.exp(-lt * 70.0) * 0.05

        bgm[s0 : s0 + s_len] += bass + arp + kick + hat

    # 0.00s Impact Attention-Grabber Whoosh/Slam!
    imp_len = min(int(0.28 * sr), n_samples)
    lt0 = np.arange(imp_len, dtype=np.float32) / sr
    sfx[:imp_len] += np.sin(2.0 * math.pi * np.cumsum(260.0 * np.exp(-lt0 * 14.0) + 55.0) / sr) * np.exp(-lt0 * 10.0) * 0.35
    sfx[:imp_len] += np.sin(2.0 * math.pi * 1046.5 * lt0) * np.exp(-lt0 * 14.0) * 0.18

    # Frame-Accurate Game Event SFX!
    penta = [523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1174.66, 1318.51, 1567.98, 1760.0, 2093.0]
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        idx0 = int(t0 * sr)
        if idx0 >= n_samples:
            continue
        kind = ev.get("type")

        if kind == "shot":
            e_len = min(int(0.05 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(780.0, 320.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 55.0) * 0.09

        elif kind == "gate_tick":
            val = int(ev.get("val", 0))
            f = min(1600.0, max(380.0, 460.0 + (val + 12) * 26.0))
            e_len = min(int(0.07 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * f * lt) * np.exp(-lt * 32.0) * 0.18

        elif kind == "gate_flip":
            for k, f in enumerate((659.25, 987.77, 1318.51)):
                k0 = idx0 + int(k * 0.04 * sr)
                e_len = min(int(0.18 * sr), n_samples - k0)
                if e_len > 0:
                    lt = np.arange(e_len, dtype=np.float32) / sr
                    sfx[k0 : k0 + e_len] += np.sin(2.0 * math.pi * f * lt) * np.exp(-lt * 14.0) * 0.24

        elif kind == "barrel":
            for k, f in enumerate((587.33, 880.0, 1174.66, 1567.98)):
                k0 = idx0 + int(k * 0.04 * sr)
                e_len = min(int(0.22 * sr), n_samples - k0)
                if e_len > 0:
                    lt = np.arange(e_len, dtype=np.float32) / sr
                    sfx[k0 : k0 + e_len] += np.sin(2.0 * math.pi * f * lt) * np.exp(-lt * 13.0) * 0.24

        elif kind == "gate_pass":
            op = ev.get("op")
            val = int(ev.get("val", 1))
            big = (op == "mul" and val >= 3) or val >= 20
            # Heavy bass drop + triumphant chord!
            b_len = min(int(0.28 * sr), n_samples - idx0)
            lt = np.arange(b_len, dtype=np.float32) / sr
            sfx[idx0 : idx0 + b_len] += np.sin(2.0 * math.pi * np.cumsum(150.0 * np.exp(-lt * 16.0) + 45.0) / sr) * np.exp(-lt * 8.0) * (0.38 if big else 0.22)
            chord = (523.25, 659.25, 783.99, 1046.5, 1318.51) if big else (523.25, 659.25, 880.0)
            for k, f in enumerate(chord):
                k0 = idx0 + int(k * 0.035 * sr)
                e_len = min(int(0.26 * sr), n_samples - k0)
                if e_len > 0:
                    clt = np.arange(e_len, dtype=np.float32) / sr
                    sfx[k0 : k0 + e_len] += np.sin(2.0 * math.pi * f * clt) * np.exp(-clt * 11.0) * 0.20

        elif kind == "pop":
            c = int(ev.get("combo", 1))
            f0 = penta[min(c % len(penta), len(penta) - 1)]
            e_len = min(int(0.08 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(f0, f0 * 1.45, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 34.0) * 0.18

        elif kind == "horde_clear":
            e_len = min(int(0.32 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 7)
            sfx[idx0 : idx0 + e_len] += rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 16.0) * 0.18
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * 1046.5 * lt) * np.exp(-lt * 10.0) * 0.22

        elif kind == "boss_hit":
            e_len = min(int(0.06 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * 165.0 * lt) * np.exp(-lt * 36.0) * 0.14

        elif kind == "victory":
            # Massive Boss Explosion + Heroic Victory Fanfare!
            e_len = min(int(0.65 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(140.0 * np.exp(-lt * 11.0) + 38.0) / sr) * np.exp(-lt * 5.0) * 0.45
            rng = np.random.default_rng(seed=2026)
            sfx[idx0 : idx0 + e_len] += rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 7.0) * 0.22
            for k, f in enumerate((523.25, 659.25, 783.99, 1046.5, 1318.51, 1567.98)):
                k0 = idx0 + int((0.08 + k * 0.06) * sr)
                fl = min(int(0.45 * sr), n_samples - k0)
                if fl > 0:
                    flt = np.arange(fl, dtype=np.float32) / sr
                    sfx[k0 : k0 + fl] += np.sin(2.0 * math.pi * f * flt) * np.exp(-flt * 5.5) * 0.24

    # Mix TTS Japanese Narration with automatic BGM ducking
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day05_"))
    try:
        for idx, (cue_t, line_txt) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.78
                s0 = int(cue_t * sr)
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.34)
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    mixed = bgm * duck + sfx * 0.85 + voice
    mixed = np.tanh(mixed * 1.18) * 0.88
    pcm = np.clip(mixed * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def overlay_kinetic_captions(
    frame_img: Image.Image,
    t: float,
    pop_text: str,
    pop_start: float,
    pop_color: tuple,
    sub_text: str,
    font_big,
    font_med,
    font_small,
) -> Image.Image:
    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.LANCZOS)

    img = frame_img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    if pop_text:
        age = max(0.0, t - pop_start)
        pop_lift = int(20 * math.exp(-age * 16.0))
        fnt = font_big if len(pop_text) <= 13 else font_med
        tb = draw.textbbox((0, 0), pop_text, font=fnt, stroke_width=12)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        tx = (W - tw) // 2
        ty = 315 - th // 2 - pop_lift

        draw.text((tx + 5, ty + 7), pop_text, font=fnt, fill=(8, 15, 30, 195))
        draw.text(
            (tx, ty),
            pop_text,
            font=fnt,
            fill=pop_color,
            stroke_width=12,
            stroke_fill=(10, 20, 40),
        )

    if sub_text:
        tb = draw.textbbox((0, 0), sub_text, font=font_small, stroke_width=8)
        tw = tb[2] - tb[0]
        tx = (W - tw) // 2
        ty = 382
        draw.text(
            (tx, ty),
            sub_text,
            font=font_small,
            fill=(255, 255, 255),
            stroke_width=8,
            stroke_fill=(10, 20, 40),
        )

    return img.convert("RGB")


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
    dbg_port = 9285
    profile_dir = tempfile.mkdtemp(prefix="cdp_day05_")
    proc = subprocess.Popen(
        [
            browser, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={dbg_port}", "--window-size=540,960",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.*"):
        old.unlink()

    fps = 60
    dt_sec = 1.0 / fps
    total_dur = 14.0
    total_frames = int(fps * total_dur)

    try:
        ws_url = None
        for _ in range(80):
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
            raise RuntimeError("Failed to connect to Chrome CDP")

        cdp = SimpleCDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540, "height": 960, "deviceScaleFactor": 2, "mobile": True
        })

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day05-crowd-999/index.html?shorts=1"})
        for _ in range(60):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true;")

        font_big = ImageFont.truetype(FONT_SANS, 64)
        font_med = ImageFont.truetype(FONT_SANS, 50)
        font_small = ImageFont.truetype(FONT_SANS, 38)

        # Retention-optimized kinetic caption plan (no unsupported color emojis -> zero tofu boxes!)
        caption_plan = [
            (0.00, 1.05, "あの詐欺広告をガチ神ゲー化!!", (253, 224, 71), "赤ゲートを撃って青に反転！"),
            (1.05, 2.55, "連射で一気に大増殖!!", (56, 189, 248), ""),
            (2.55, 4.30, "★ 3WAY拡散砲を解放!!", (250, 204, 21), ""),
            (4.30, 6.20, "×3ゲート突入!! 96人!!", (56, 189, 248), ""),
            (6.20, 7.65, "★ 巨人チャンピオン参戦!!", (253, 224, 71), ""),
            (7.65, 10.20, "×4で384人の大津波!!", (56, 189, 248), ""),
            (10.20, 14.10, "巨大ボス撃破!! 何人増やせる？", (253, 224, 71), "リンクから無料で遊べるよ ▼"),
        ]

        thumb_src_path = OUT_DIR / "_thumb_src.png"

        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            cdp.eval_js("window.__stepFrame(1/60);")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 95})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            if f_idx == 486:  # 8.1s x4 tsunami shot for crisp note thumbnail
                raw_img.save(thumb_src_path)

            pop_text, pop_start, pop_color, sub_text = "", t, (255, 255, 255), ""
            for s0, s1, txt, col, sub in caption_plan:
                if s0 <= t < s1:
                    pop_text, pop_start, pop_color, sub_text = txt, s0, col, sub
                    break

            frame = overlay_kinetic_captions(
                raw_img, t, pop_text, pop_start, pop_color, sub_text,
                font_big, font_med, font_small,
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=94)

        events_json = cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]"
        events = json.loads(events_json)
        cdp.close()

        # Generate full mixed audio (152 BPM BGM + SFX + Japanese Narration!)
        wav_path = OUT_DIR / "audio.wav"
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day05_short.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%04d.jpg"),
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
                str(out_mp4),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        if thumb_src_path.exists():
            render_note_thumbnail(browser, thumb_src_path, OUT_DIR / "note_thumbnail.png")
            thumb_src_path.unlink(missing_ok=True)

        print(f"Generated 60fps Audio Short: {out_mp4} ({out_mp4.stat().st_size // 1024} KB)")
        print(f"Recorded events: {len(events)}")
    finally:
        proc.terminate()
        shutil.rmtree(profile_dir, ignore_errors=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
