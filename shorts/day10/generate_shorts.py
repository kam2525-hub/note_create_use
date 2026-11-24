#!/usr/bin/env python3
"""
Day 10 YouTube Shorts (1080x1920, 24fps, 25.0s) — おなら立ち幅跳び 999 (ONARA LONG JUMP 999)
NEW VIRAL STORYTELLING & COMIC TRACKER PIPELINE (Different from Day 01-09!):
- Native 1080x1920 capture via Chrome CDP (540x960 viewport @ deviceScaleFactor=2)
- 0.00-1.35s: ULTRA IMPACT COLD-OPEN — Instant cosmic EVO fart rocket blast + shark missile + anime speedlines + zoom shake + bold comic hook!
- 1.35-5.10s: Relatable Fail Attempt — Jumps from Tokyo sandpit, runs out of gas just short of Tokyo Tower ("あと◯◯mで東京タワーだったのにw")
- 5.10-10.80s: Comeback & In-Run Survivor Evolution — PERFECT jump -> Cola/Sweet Potato -> LV UP 3-choice skill modal!
- 10.80-15.80s: High-Stakes Thrills — Shark missile lock-on warning -> NEAR MISS dodge + Lv.5 EVO storm sweeping the sky!
- 15.80-18.80s: Dramatic Skid Landing & "So Close!!" Result Card + PE Teacher reaction + X share flex
- 18.80-22.00s: Mandatory Subscribe CTA (interactive cursor click -> 登録済み🔔)
- 22.00-25.00s: Mandatory Comment Request CTA ("次はこんなクソゲー作って!")
- Top Live World Progress Tracker Bar (🗼東京 -> 🗼ﾀﾜｰ -> ⚓横浜 -> 🗻富士山 -> 🇰🇷ｿｳﾙ) synced live with game distance!
- Energetic ja-JP-KeitaNeural narration + studio compressor/ducking + 132 BPM bouncy funk-comedy beat + fart/alarm/chime SFX
"""

import asyncio
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
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "shorts" / "day10" / "output"
ART_DIR = Path("/home/antigravity/.gemini/jetski/brain/v1/default/jetski_remote_agents_3p_devbox/ae4d8971-f39f-4330-8528-ad5d3653b283")
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
    for cand in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    ):
        if os.path.exists(cand):
            return cand
    out = subprocess.check_output(["fc-match", "-f", "%{file}", "Noto Sans CJK JP:bold"], text=True).strip()
    if out and os.path.exists(out):
        return out
    raise RuntimeError("Japanese Noto Sans CJK font not found")


FONT_SANS = find_jp_font()


class SimpleCDP:
    def __init__(self, ws_url: str):
        rest = ws_url[5:]
        host_port, path = rest.split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.msg_id = 0

    def _send(self, text: str):
        payload = text.encode("utf-8")
        hdr = bytearray([0x81])
        n = len(payload)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr.extend(struct.pack("!H", n))
        else:
            hdr.append(0x80 | 127)
            hdr.extend(struct.pack("!Q", n))
        mask = os.urandom(4)
        hdr.extend(mask)
        self.sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _recv_exact(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise ConnectionError("WS closed")
            out.extend(chunk)
        return bytes(out)

    def _recv(self) -> str:
        while True:
            b1, b2 = self._recv_exact(2)
            op, ln = b1 & 0x0F, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", self._recv_exact(8))[0]
            data = self._recv_exact(ln)
            if op == 8:
                raise ConnectionError("WS closed")
            if op == 1:
                return data.decode("utf-8", errors="replace")

    def call(self, method: str, params=None):
        self.msg_id += 1
        mid = self.msg_id
        self._send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            resp = json.loads(self._recv())
            if resp.get("id") == mid:
                if "error" in resp:
                    raise RuntimeError(resp["error"])
                return resp.get("result", {})

    def eval_js(self, expr: str):
        return self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}).get("result", {}).get("value")

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
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# Energetic male creator voiceover (fresh contrast from previous days!)
NARRATION_CUES = [
    (0.05,  "東京の砂場から、おならだけで世界のどこまで飛べる！？", "+18%", "+3Hz"),
    (1.90,  "最初はこれｗｗ 東京タワー手前で即ガス欠して草！", "+16%", "+2Hz"),
    (5.25,  "でもタイミングよく噴射してスキルを進化させると…", "+17%", "+2Hz"),
    (10.85, "サメミサイルを紙一重回避!! 横浜も富士山もぶち抜いたｗｗ", "+18%", "+3Hz"),
    (15.85, "あとちょっとで韓国ソウルだったのに悔しすぎる!!", "+16%", "+2Hz"),
    (18.85, "100日後にバズるゲームを見たい人、チャンネル登録よろしく！", "+15%", "+1Hz"),
    (22.05, "作って欲しいゲームがあったら、コメント欄によろしく！", "+15%", "+2Hz"),
]


def synthesize_tts_line(text: str, out_wav: Path, rate: str = "+16%", pitch: str = "+2Hz", sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"
    try:
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(text, voice="ja-JP-KeitaNeural", rate=rate, pitch=pitch)
            await asyncio.wait_for(comm.save(str(tmp_mp3)), timeout=15.0)

        asyncio.run(_gen())
        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 500:
            af = (
                "silenceremove=start_periods=1:start_silence=0.02:start_threshold=-45dB,"
                "areverse,silenceremove=start_periods=1:start_silence=0.02:start_threshold=-45dB,areverse,"
                "highpass=f=90,"
                "equalizer=f=220:t=q:w=1.2:g=2.2,"
                "equalizer=f=3000:t=q:w=1.4:g=2.4,"
                "acompressor=threshold=-16dB:ratio=2.8:attack=6:release=80:makeup=1.8"
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(tmp_mp3), "-af", af, "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            tmp_mp3.unlink(missing_ok=True)
            return True
    except Exception as e:
        print(f"[WARN] TTS failed for '{text}': {e}")
        tmp_mp3.unlink(missing_ok=True)
    return False


def load_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def add_stereo(buf_l: np.ndarray, buf_r: np.ndarray, idx: int, sig: np.ndarray, pan: float = 0.0, gain: float = 1.0):
    if idx < 0 or idx >= len(buf_l):
        return
    ln = min(len(sig), len(buf_l) - idx)
    if ln <= 0:
        return
    gl = gain * math.sqrt(max(0.0, 0.5 * (1.0 - pan)))
    gr = gain * math.sqrt(max(0.0, 0.5 * (1.0 + pan)))
    buf_l[idx : idx + ln] += sig[:ln] * gl
    buf_r[idx : idx + ln] += sig[:ln] * gr


def synthesize_audio_track(wav_path: Path, total_dur: float, sfx_events: list, sr: int = 44100):
    """Synthesize upbeat 132 BPM comedy-funk action BGM + crisp fart/alarm/avoid/fanfare SFX + Keita narration."""
    n_samples = int(total_dur * sr)
    bgm_l = np.zeros(n_samples, dtype=np.float32)
    bgm_r = np.zeros(n_samples, dtype=np.float32)
    sfx_l = np.zeros(n_samples, dtype=np.float32)
    sfx_r = np.zeros(n_samples, dtype=np.float32)
    voice = np.zeros(n_samples, dtype=np.float32)

    # 132 BPM Bouncy Pop-Funk Action Beat (bright contrast to Day 09 dark cyberpunk)
    bpm = 132.0
    step_dur = 60.0 / bpm / 4.0  # 16th note
    n_steps = int(total_dur / step_dur)
    rng = np.random.default_rng(10999)

    chord_roots = [52, 52, 55, 57, 52, 52, 59, 57]  # E major / funk progression
    mel_offsets = [0, 7, 12, 10, 7, 12, 15, 12]

    for s in range(n_steps):
        t0 = s * step_dur
        idx = int(t0 * sr)
        bar = (s // 16) % len(chord_roots)
        step = s % 16
        root = chord_roots[bar]

        # Punchy Kick on 0, 6, 8, 10
        if step in (0, 6, 8, 10):
            klen = int(0.14 * sr)
            kt = np.arange(klen, dtype=np.float32) / sr
            kf = 130.0 * np.exp(-kt * 26.0) + 48.0
            kick = np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * np.exp(-kt * 16.0)
            add_stereo(bgm_l, bgm_r, idx, kick, pan=0.0, gain=0.22)

        # Crisp Snare/Clap on 4, 12
        if step in (4, 12):
            slen = int(0.11 * sr)
            st = np.arange(slen, dtype=np.float32) / sr
            snare = (rng.uniform(-1, 1, slen).astype(np.float32) * 0.7 + np.sin(2.0 * math.pi * 220.0 * st) * 0.3) * np.exp(-st * 28.0)
            add_stereo(bgm_l, bgm_r, idx, snare, pan=0.05, gain=0.14)

        # Shaker Hi-hat on offbeats
        if step % 2 == 1:
            hlen = int(0.035 * sr)
            ht = np.arange(hlen, dtype=np.float32) / sr
            hat = rng.uniform(-1, 1, hlen).astype(np.float32) * np.exp(-ht * 90.0)
            add_stereo(bgm_l, bgm_r, idx, hat, pan=-0.25 if step % 4 == 1 else 0.25, gain=0.05)

        # Bouncy Slap-Bass Pattern
        if step in (0, 2, 6, 8, 11, 14):
            midi = root - 12 + (12 if step in (11, 14) else 0)
            freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
            blen = int(0.12 * sr)
            bt = np.arange(blen, dtype=np.float32) / sr
            bass = (np.sin(2.0 * math.pi * freq * bt) * 0.7 + np.sin(2.0 * math.pi * freq * 2.0 * bt) * 0.3) * np.exp(-bt * 16.0)
            add_stereo(bgm_l, bgm_r, idx, bass, pan=0.0, gain=0.16)

        # Catchy Toy-Brass Lead Hook
        if step in (0, 3, 6, 8, 12, 14):
            midi = root + 12 + mel_offsets[(step + bar) % len(mel_offsets)]
            freq = 440.0 * (2.0 ** ((midi - 69) / 12.0))
            llen = int(0.13 * sr)
            lt = np.arange(llen, dtype=np.float32) / sr
            lead = (np.sin(2.0 * math.pi * freq * lt) * 0.65 + np.sin(2.0 * math.pi * freq * 3.0 * lt) * 0.15) * np.exp(-lt * 15.0)
            add_stereo(bgm_l, bgm_r, idx, lead, pan=0.22 if step % 4 == 0 else -0.22, gain=0.085)

    # Custom SFX Synthesizers
    def add_fart_sfx(t_sec: float, power: float = 1.0, gold: bool = False):
        idx = int(t_sec * sr)
        dur = 0.20 + min(0.18, power * 0.06)
        flen = int(dur * sr)
        ft = np.arange(flen, dtype=np.float32) / sr
        base = 92.0 if gold else 64.0
        wobble = np.sin(2.0 * math.pi * 26.0 * ft) * 18.0
        freq = base * (1.28 - 0.52 * (ft / dur)) + wobble
        phase = 2.0 * math.pi * np.cumsum(np.maximum(25.0, freq)) / sr
        # Filtered saw-like brassy fart
        sig = (np.sin(phase) * 0.55 + np.sin(phase * 2.0) * 0.30 + np.sin(phase * 3.0) * 0.15)
        env = np.minimum(1.0, ft / 0.015) * np.exp(-ft * (6.0 if gold else 9.0))
        add_stereo(sfx_l, sfx_r, idx, sig * env, pan=-0.1, gain=0.38 if gold else 0.28)
        if gold:
            # Shiny JUST / EVO sparkle chord
            ct = ft
            spark = np.sin(2.0 * math.pi * 1046.5 * ct) * np.exp(-ct * 14.0) * 0.25
            add_stereo(sfx_l, sfx_r, idx, spark, pan=0.15, gain=0.32)

    def add_boom(t_sec: float, gain: float = 0.42):
        idx = int(t_sec * sr)
        blen = int(0.38 * sr)
        bt = np.arange(blen, dtype=np.float32) / sr
        bf = 110.0 * np.exp(-bt * 11.0) + 34.0
        sub = np.sin(2.0 * math.pi * np.cumsum(bf) / sr) * np.exp(-bt * 7.5)
        nz = rng.uniform(-1, 1, blen).astype(np.float32) * np.exp(-bt * 16.0) * 0.4
        add_stereo(sfx_l, sfx_r, idx, sub + nz, pan=0.0, gain=gain)

    def add_whoosh(t_sec: float, gain: float = 0.20):
        idx = int(t_sec * sr)
        wlen = int(0.18 * sr)
        wt = np.arange(wlen, dtype=np.float32) / sr
        env = np.sin(math.pi * wt / 0.18) ** 1.4
        sig = rng.uniform(-1, 1, wlen).astype(np.float32) * env * 0.35 + np.sin(2.0 * math.pi * (280 + 700 * wt) * wt) * env * 0.4
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    def add_alarm(t_sec: float, gain: float = 0.22):
        for off in (0.0, 0.16):
            idx = int((t_sec + off) * sr)
            alen = int(0.10 * sr)
            at = np.arange(alen, dtype=np.float32) / sr
            sig = np.sin(2.0 * math.pi * 880.0 * at) * np.exp(-at * 18.0)
            add_stereo(sfx_l, sfx_r, idx, sig, pan=0.2, gain=gain)

    def add_chime(t_sec: float, gain: float = 0.28):
        idx = int(t_sec * sr)
        clen = int(0.42 * sr)
        ct = np.arange(clen, dtype=np.float32) / sr
        s1 = np.sin(2.0 * math.pi * 1046.5 * ct) * np.exp(-ct * 11.0)
        s2 = np.sin(2.0 * math.pi * 1567.98 * ct) * np.exp(-ct * 9.0)
        add_stereo(sfx_l, sfx_r, idx, s1 * 0.6 + s2 * 0.6, pan=0.0, gain=gain)

    def add_bonk(t_sec: float, gain: float = 0.26):
        idx = int(t_sec * sr)
        blen = int(0.22 * sr)
        bt = np.arange(blen, dtype=np.float32) / sr
        bf = 190.0 * np.exp(-bt * 12.0) + 55.0
        sig = np.sin(2.0 * math.pi * np.cumsum(bf) / sr) * np.exp(-bt * 12.0)
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    # Signature Impact & Editorial Sounds
    add_boom(0.02, gain=0.48)
    add_fart_sfx(0.04, power=1.8, gold=True)   # 0.04s 1st-second IMPACT FART ROCKET!
    add_fart_sfx(0.55, power=1.6, gold=True)
    for wt in (1.32, 5.05, 10.75, 15.75, 18.75, 21.95):
        add_whoosh(wt, gain=0.20)
    add_bonk(3.65, gain=0.28)                  # Scene 2 comical flop landing!
    add_chime(9.10, gain=0.30)                 # Lv-up!
    add_alarm(11.35, gain=0.24)                # Shark missile lock-on!
    add_chime(12.60, gain=0.32)                # Near-miss dodge!
    add_chime(20.15, gain=0.34)                # Subscribe bell click!

    for ev in sfx_events:
        t0, kind = ev
        if kind == "fart":
            add_fart_sfx(t0, power=1.1, gold=False)
        elif kind == "gold_fart":
            add_fart_sfx(t0, power=1.5, gold=True)

    # Voiceover + Smooth Auto-Ducking
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day10_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.10 * sr)
        for i, (cue_t, line_txt, rate, pitch) in enumerate(NARRATION_CUES):
            wav_c = tts_tmp / f"cue_{i}.wav"
            if synthesize_tts_line(line_txt, wav_c, rate=rate, pitch=pitch, sr=sr):
                arr = load_wav_mono(wav_c)
                pk = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if pk > 0.01:
                    arr = (arr / pk) * 0.90
                s0 = max(int(cue_t * sr), prev_end_s + int(0.06 * sr))
                ln = min(len(arr), n_samples - s0)
                if ln > 0:
                    voice[s0 : s0 + ln] += arr[:ln]
                    prev_end_s = s0 + ln
                    d0 = max(0, s0 - ramp_n)
                    d1 = min(n_samples, s0 + ln + ramp_n)
                    duck[s0 : s0 + ln] = np.minimum(duck[s0 : s0 + ln], 0.24)
                    if s0 > d0:
                        duck[d0:s0] = np.minimum(duck[d0:s0], np.linspace(1.0, 0.24, s0 - d0, dtype=np.float32))
                    if d1 > s0 + ln:
                        duck[s0 + ln : d1] = np.minimum(duck[s0 + ln : d1], np.linspace(0.24, 1.0, d1 - (s0 + ln), dtype=np.float32))
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    # Master Limiter Mix (zero clipping, punchy Shorts loudness)
    mix_l = bgm_l * duck + sfx_l * 0.72 + voice * 0.96
    mix_r = bgm_r * duck + sfx_r * 0.72 + voice * 0.96
    mix_l = np.tanh(mix_l * 1.10) * 0.90
    mix_r = np.tanh(mix_r * 1.10) * 0.90

    stereo = np.empty(n_samples * 2, dtype=np.int16)
    stereo[0::2] = np.clip(mix_l * 32767.0, -32767, 32767).astype(np.int16)
    stereo[1::2] = np.clip(mix_r * 32767.0, -32767, 32767).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def draw_comic_text_line(draw: ImageDraw.ImageDraw, cx: int, y: int, tokens: list, font: ImageFont.FreeTypeFont, outer_w: int = 12):
    widths = [draw.textlength(txt, font=font) for txt, _ in tokens]
    cur_x = cx - sum(widths) / 2.0
    x = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((x + 6, y + 7), txt, font=font, fill=(15, 23, 42, 240), stroke_width=outer_w + 2, stroke_fill=(15, 23, 42, 240))
        x += w
    x = cur_x
    for (txt, col), w in zip(tokens, widths):
        draw.text((x, y), txt, font=font, fill=(*col, 255), stroke_width=outer_w - 4, stroke_fill=(15, 23, 42, 255))
        x += w


def draw_world_tracker(draw: ImageDraw.ImageDraw, sim_x: float, fonts: dict, y_top: int = 192):
    """Unique Day-10 Top Tracker: Shows live runner progress from Tokyo -> World Cities!"""
    W = 1080
    x0, x1 = 44, W - 44
    y0, y1 = y_top, y_top + 66
    draw.rounded_rectangle((x0 + 4, y0 + 5, x1 + 4, y1 + 5), radius=18, fill=(15, 23, 42, 220))
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=(255, 253, 245, 238), outline=(15, 23, 42, 255), width=4)

    stops = [(0, "東京"), (35, "ﾀﾜｰ"), (125, "横浜"), (275, "富士"), (890, "ｿｳﾙ")]
    bar_l, bar_r = x0 + 62, x1 - 62
    bar_y = y0 + 25
    draw.line((bar_l, bar_y, bar_r, bar_y), fill=(203, 213, 225, 255), width=8)

    # Piecewise progress across visual nodes
    prog = 0.0
    if sim_x >= stops[-1][0]:
        prog = 1.0
    else:
        for i in range(len(stops) - 1):
            a, b = stops[i][0], stops[i + 1][0]
            if a <= sim_x <= b:
                prog = (i + (sim_x - a) / max(1, b - a)) / (len(stops) - 1)
                break
    fill_x = int(bar_l + (bar_r - bar_l) * prog)
    draw.line((bar_l, bar_y, max(bar_l + 4, fill_x), bar_y), fill=(249, 115, 22, 255), width=8)

    for i, (sx, lbl) in enumerate(stops):
        nx = int(bar_l + (bar_r - bar_l) * (i / (len(stops) - 1)))
        reached = sim_x >= sx
        draw.ellipse((nx - 8, bar_y - 8, nx + 8, bar_y + 8), fill=(250, 204, 21, 255) if reached else (255, 255, 255, 255), outline=(15, 23, 42, 255), width=3)
        tw = draw.textlength(lbl, font=fonts["tiny"])
        draw.text((nx - tw / 2, y0 + 36), lbl, font=fonts["tiny"], fill=(15, 23, 42, 255))

    # Moving runner marker
    draw.ellipse((fill_x - 14, bar_y - 14, fill_x + 14, bar_y + 14), fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=3)


def apply_chromatic_split(img: Image.Image, shift: int) -> Image.Image:
    if shift <= 0:
        return img
    r, g, b = img.split()
    return Image.merge("RGB", (ImageChops.offset(r, shift, 0), g, ImageChops.offset(b, -shift, 0)))


def draw_frame_overlay(frame_img: Image.Image, t: float, total_dur: float, sim_x: float, impact: float, flash: float, fonts: dict) -> Image.Image:
    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.LANCZOS)

    # First-second impact zoom & chromatic burst!
    if t < 1.35:
        zoom = 1.0 + 0.14 * max(0.0, 1.0 - t / 1.35) + 0.05 * impact
        nw, nh = int(1080 * zoom), int(1920 * zoom)
        zimg = frame_img.resize((nw, nh), Image.Resampling.BICUBIC)
        l = (nw - 1080) // 2 + (int(math.sin(t * 95) * 10) if t < 0.55 else 0)
        u = (nh - 1920) // 2 + (int(math.cos(t * 88) * 10) if t < 0.55 else 0)
        l = max(0, min(nw - 1080, l))
        u = max(0, min(nh - 1920, u))
        frame_img = zimg.crop((l, u, l + 1080, u + 1920))

    if impact > 0.16:
        frame_img = apply_chromatic_split(frame_img, int(12 * impact))

    img = frame_img.convert("RGBA")
    ov = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)
    W, H = 1080, 1920

    # Bottom gradient scrim so comic subtitles always pop cleanly
    for gy in range(0, 440, 16):
        alpha = int(140 * (gy / 440.0) ** 1.4)
        draw.rectangle((0, H - 440 + gy, W, H - 440 + gy + 16), fill=(10, 15, 30, alpha))

    # Anime impact speedlines during cold open & near-miss
    if impact > 0.20:
        cx, cy = W // 2, int(H * 0.50)
        for i in range(30):
            ang = (i / 30.0) * math.tau + t * 5.0
            r1 = 290 + (i % 3) * 45
            r2 = 1200
            col = (250, 204, 21) if i % 2 == 0 else (239, 68, 68)
            draw.line((cx + int(math.cos(ang) * r1), cy + int(math.sin(ang) * r1), cx + int(math.cos(ang) * r2), cy + int(math.sin(ang) * r2)),
                      fill=(*col, int(195 * impact)), width=9 if i % 2 == 0 else 4)

    # Comic Top Header Banner (Clean & bold!)
    draw.rounded_rectangle((46, 62, W - 40, 134), radius=24, fill=(15, 23, 42, 235))
    draw.rounded_rectangle((42, 58, W - 44, 130), radius=24, fill=(250, 204, 21, 255), outline=(15, 23, 42, 255), width=4)
    draw.rounded_rectangle((56, 70, 216, 118), radius=14, fill=(239, 68, 68, 255), outline=(15, 23, 42, 255), width=3)
    draw.text((76, 76), "DAY 10", font=fonts["badge"], fill=(255, 255, 255, 255))
    draw.text((236, 76), "100日後にバズるゲーム", font=fonts["hdr"], fill=(15, 23, 42, 255))

    # Live World Progress Tracker (Tokyo -> Seoul)
    draw_world_tracker(draw, sim_x, fonts, y_top=144)

    # SCENE 1 (0.00 - 1.35s): MASSIVE FIRST-SECOND IMPACT HOOK!
    if t < 1.35:
        bounce = int(38 * math.exp(-t * 14.0))
        # Shock banner
        draw.rounded_rectangle((70, 320 + bounce, W - 70, 405 + bounce), radius=20, fill=(239, 68, 68, 250), outline=(255, 255, 255, 255), width=4)
        draw_comic_text_line(draw, W // 2, 332 + bounce, [("検証!!", (250, 204, 21)), (" おならだけで", (255, 255, 255))], fonts["hook_sm"], outer_w=9)
        draw_comic_text_line(draw, W // 2, 425 + bounce, [("世界", (250, 204, 21)), ("何m飛べる!?", (255, 255, 255))], fonts["hook_lg"], outer_w=15)
        draw_comic_text_line(draw, W // 2, 1370, [("東京0m", (56, 189, 248)), ("からガチ検証ｗｗ", (255, 255, 255))], fonts["sub"], outer_w=12)

    # SCENE 2 (1.35 - 5.10s): Comical Fail Run!
    elif t < 5.10:
        if t >= 3.65:
            # Stamp when crashing short of Tokyo Tower!
            draw.rounded_rectangle((170, 295, W - 170, 380), radius=22, fill=(15, 23, 42, 238), outline=(239, 68, 68, 255), width=5)
            draw_comic_text_line(draw, W // 2, 310, [("東京タワー手前", (250, 204, 21)), ("で終了ｗｗ", (239, 68, 68))], fonts["hook_sm"], outer_w=9)
        draw_comic_text_line(draw, W // 2, 1485, [("最初は", (255, 255, 255)), ("即ガス欠で2,076mｗ", (250, 204, 21))], fonts["sub"], outer_w=12)
        draw_comic_text_line(draw, W // 2, 1570, [("あと1,924m", (239, 68, 68)), ("で東京タワーなのに!!", (255, 255, 255))], fonts["sub"], outer_w=12)

    # SCENE 3 (5.10 - 10.80s): Skill Evolution Comeback!
    elif t < 10.80:
        draw_comic_text_line(draw, W // 2, 1340, [("JUST連発", (56, 189, 248)), ("＆", (255, 255, 255)), ("コーラ急上昇!!", (250, 204, 21))], fonts["sub"], outer_w=12)
        draw_comic_text_line(draw, W // 2, 1425, [("1プレイ限定で", (255, 255, 255)), ("スキル進化!!", (163, 230, 53))], fonts["sub"], outer_w=12)

    # SCENE 4 (10.80 - 15.80s): Shark Missile + Near Miss + EVO Storm!
    elif t < 15.80:
        if 11.30 <= t < 12.65:
            draw_comic_text_line(draw, W // 2, 315, [("⚠ ミサイル接近!!", (239, 68, 68))], fonts["hook_sm"], outer_w=11)
        elif t >= 12.65:
            draw_comic_text_line(draw, W // 2, 315, [("紙一重回避", (56, 189, 248)), ("→EVO覚醒!!", (250, 204, 21))], fonts["hook_sm"], outer_w=11)
        draw_comic_text_line(draw, W // 2, 1340, [("サメミサイルを", (239, 68, 68)), ("紙一重回避!!", (56, 189, 248))], fonts["sub"], outer_w=12)
        draw_comic_text_line(draw, W // 2, 1425, [("回転焼き芋EVO", (250, 204, 21)), ("で横浜＆富士山突破!!", (255, 255, 255))], fonts["sub"], outer_w=12)

    # SCENE 5 (15.80 - 18.80s): Dramatic Result Cliffhanger!
    elif t < 18.80:
        draw_comic_text_line(draw, W // 2, 1510, [("あとちょっとで", (250, 204, 21)), ("海外だったのに!!", (239, 68, 68))], fonts["sub"], outer_w=12)
        draw_comic_text_line(draw, W // 2, 1595, [("悔しすぎて", (255, 255, 255)), ("もう1回が止まらんｗ", (163, 230, 53))], fonts["sub"], outer_w=12)

    # SCENE 6A (18.80 - 22.00s): Mandatory Subscribe CTA!
    elif t < 22.00:
        age = t - 18.80
        pop = int(40 * math.exp(-age * 14.0))
        clicked = t >= 20.15
        cage = max(0.0, t - 20.15)
        cx = W // 2

        draw_comic_text_line(draw, cx, 1080 + pop, [("100日後に", (250, 204, 21)), ("バズるゲーム", (255, 255, 255)), ("見たい人は", (255, 255, 255))], fonts["cta_h"], outer_w=13)
        draw_comic_text_line(draw, cx, 1165 + pop, [("チャンネル登録", (239, 68, 68)), ("よろしく!!", (255, 255, 255))], fonts["cta_lg"], outer_w=14)

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1285 + pop, 1445 + pop
        draw.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=32, fill=(0, 0, 0, 180))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=32, fill=(15, 23, 42, 245), outline=(250, 204, 21, 255), width=4)

        av_x, av_y = x0 + 84, (y0 + y1) // 2
        draw.ellipse((av_x - 46, av_y - 46, av_x + 46, av_y + 46), fill=(163, 230, 53, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((av_x - 28, av_y - 18), "D10", font=fonts["badge"], fill=(15, 23, 42, 255))
        draw.text((x0 + 148, y0 + 34), "100日後にバズるゲーム", font=fonts["yt_name"], fill=(255, 255, 255, 255))
        draw.text((x0 + 148, y0 + 86), "プロフ/概要欄から即プレイ!", font=fonts["yt_meta"], fill=(148, 163, 184, 255))

        bcx, bcy = x1 - 155, (y0 + y1) // 2
        sc = 1.0 - 0.08 * math.exp(-cage * 16.0) if clicked else (1.0 + 0.03 * math.sin(t * 10.0))
        bw, bh = int(260 * sc), int(82 * sc)
        bx0, by0, bx1, by1 = bcx - bw // 2, bcy - bh // 2, bcx + bw // 2, bcy + bh // 2

        if clicked:
            if cage < 0.45:
                rr = int(42 + cage * 220)
                draw.ellipse((bcx - rr, bcy - rr, bcx + rr, bcy + rr), outline=(250, 204, 21, int(230 * (1 - cage / 0.45))), width=7)
            draw.rounded_rectangle((bx0, by0, bx1, by1), radius=40, fill=(51, 65, 85, 255), outline=(255, 255, 255, 130), width=3)
            btxt = "登録済み"
            tw = draw.textlength(btxt, font=fonts["yt_btn"])
            draw.text((bcx - tw / 2 - 12, bcy - 20), btxt, font=fonts["yt_btn"], fill=(241, 245, 249, 255))
            blx, bly = int(bcx + tw / 2 + 12), bcy
            draw.pieslice((blx - 12, bly - 14, blx + 12, bly + 10), 180, 360, fill=(250, 204, 21, 255))
            draw.rectangle((blx - 12, bly - 2, blx + 12, bly + 9), fill=(250, 204, 21, 255))
            draw.rectangle((blx - 16, bly + 8, blx + 16, bly + 13), fill=(250, 204, 21, 255))
        else:
            draw.rounded_rectangle((bx0, by0, bx1, by1), radius=40, fill=(239, 68, 68, 255), outline=(250, 204, 21, 255), width=4)
            btxt = "チャンネル登録"
            tw = draw.textlength(btxt, font=fonts["yt_btn"])
            draw.text((bcx - tw / 2, bcy - 20), btxt, font=fonts["yt_btn"], fill=(255, 255, 255, 255))

        if 19.25 <= t < 20.85:
            pr = min(1.0, max(0.0, (t - 19.25) / 0.85))
            ease = 1.0 - (1.0 - pr) ** 3
            px = int(bcx + 115 * (1 - ease))
            py = int(bcy + 140 * (1 - ease) + (8 if clicked and cage < 0.14 else 0))
            draw.polygon([(px, py), (px, py + 44), (px + 12, py + 32), (px + 24, py + 48), (px + 32, py + 42), (px + 20, py + 28), (px + 34, py + 28)],
                         fill=(255, 255, 255, 255), outline=(15, 23, 42, 255))

    # SCENE 6B (22.00 - 25.00s): Mandatory Comment Request CTA!
    else:
        age = t - 22.00
        pop = int(42 * math.exp(-age * 14.0))
        cx = W // 2
        draw_comic_text_line(draw, cx, 1080 + pop, [("作って欲しい", (56, 189, 248)), ("ゲームあったら", (255, 255, 255))], fonts["cta_h"], outer_w=13)
        draw_comic_text_line(draw, cx, 1165 + pop, [("コメント欄", (250, 204, 21)), ("によろしく!!", (255, 255, 255))], fonts["cta_lg"], outer_w=14)

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1285 + pop, 1465 + pop
        draw.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=30, fill=(0, 0, 0, 180))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=30, fill=(15, 23, 42, 245), outline=(56, 189, 248, 255), width=4)
        draw.text((x0 + 38, y0 + 22), "コメント欄 // IDEA REQUEST", font=fonts["yt_meta"], fill=(56, 189, 248, 255))
        draw.rounded_rectangle((x0 + 34, y0 + 68, x1 - 34, y1 - 24), radius=18, fill=(30, 41, 59, 255), outline=(255, 255, 255, 50), width=2)
        sample = "「次は鼻くそ飛ばしゲーム作ってｗ」"
        chars = min(len(sample), int(age * 16.0) + 1)
        cur = "|" if int(t * 6.0) % 2 == 0 else ""
        draw.text((x0 + 54, y0 + 90), sample[:chars] + cur, font=fonts["yt_name"], fill=(248, 250, 252, 255))

    if flash > 0.02:
        draw.rectangle((0, 0, W, H), fill=(255, 255, 255, int(145 * flash)))

    # Bottom Progress Bar
    draw.rectangle((0, H - 10, W, H), fill=(15, 23, 42, 210))
    draw.rectangle((0, H - 10, int(W * min(1.0, t / total_dur)), H), fill=(250, 204, 21, 255))

    return Image.alpha_composite(img, ov).convert("RGB")


def choreograph_game(cdp: SimpleCDP, f_idx: int, t: float, fps: int, sfx_events: list):
    """Drive the real Day 10 HTML5 canvas game frame-by-frame to tell a crisp comedic 25s Shorts story!"""
    # SCENE 1 (0.00 - 1.35s): COLD-OPEN — Instant EVO Mega-Fart Blast in front of Tokyo Tower & Shark Missile!
    if f_idx == 0:
        cdp.eval_js("""(() => {
            const d = window.__OJ_DEBUG;
            d.startRun();
            d.state.phase = 'flying';
            d.state.x = 29; d.state.y = 7.5; d.state.vx = 22; d.state.vy = 5.5;
            d.state.lv = 6; d.state.xp = 0; d.state.nextXp = 999999;
            d.selectSkill('rocket'); d.selectSkill('rocket'); d.selectSkill('rocket'); d.selectSkill('rocket'); d.selectSkill('rocket');
            d.selectSkill('imo'); d.selectSkill('imo'); d.selectSkill('imo'); d.selectSkill('imo'); d.selectSkill('imo');
            d.selectSkill('missile'); d.selectSkill('missile'); d.selectSkill('missile'); d.selectSkill('missile'); d.selectSkill('missile');
            d.selectSkill('aura'); d.selectSkill('aura');
            d.state.feverTimer = 1.4;
            d.state.ambushes = [{ warn: 0, x: 40, y: 11.2, fired: true, vx: -28, nearMissed: false, dead: false }];
            d.state.hazards = [{ x: 37, y: 14, kind: 'spikeball', r: 2.0, phase: 0, hit: false, nearMissed: false }];
            d.fireFart(true);
        })()""")
    if 0 < f_idx < int(1.35 * fps) and f_idx % 8 == 0:
        cdp.eval_js("window.__OJ_DEBUG.state.xp=0; window.__OJ_DEBUG.state.fartCooldown=0; window.__OJ_DEBUG.fireFart(true);")

    # SCENE 2 (1.35 - 5.10s): RELATABLE FAIL — Jumps cleanly from Tokyo sandpit, runs out of gas at 2,076m!
    if f_idx == int(1.35 * fps):
        cdp.eval_js("""(() => {
            const d = window.__OJ_DEBUG;
            d.startRun();
            d.state.xp = 0; d.state.nextXp = 999999;
            d.state.phase = 'charging'; d.state.charge = 0.65;
            d.handlePressUp();
        })()""")
    if f_idx in (int(1.80 * fps), int(2.35 * fps), int(2.90 * fps), int(3.40 * fps)):
        cdp.eval_js("window.__OJ_DEBUG.state.fartCooldown=0; window.__OJ_DEBUG.fireFart(false);")
        sfx_events.append((t, "fart"))
    if f_idx == int(3.65 * fps):
        # Force dramatic flop landing at 2,076m short of Tokyo Tower
        cdp.eval_js("window.__OJ_DEBUG.state.gas=0; window.__OJ_DEBUG.state.y=0.1; window.__OJ_DEBUG.state.vx=0.4; window.__stepSim(0.05, 4);")

    # SCENE 3 (5.10 - 10.80s): COMEBACK + PERFECT JUMP + COLA + LV UP MODAL PICK!
    if f_idx == int(5.10 * fps):
        cdp.eval_js("""(() => {
            const d = window.__OJ_DEBUG;
            d.startRun();
            d.state.phase = 'charging'; d.state.charge = 0.88;
            d.handlePressUp();
            d.state.items = [
                { x: 14, y: 8.0, kind: 'cola', label: '急上昇!', color: '#38bdf8', bob: 0, taken: false },
                { x: 26, y: 11.0, kind: 'imo', label: '+16%GAS', color: '#a855f7', bob: 1, taken: false }
            ];
            d.state.gems = [
                { x: 19, y: 9.5, val: 20, gold: true, taken: false },
                { x: 22, y: 10.0, val: 20, gold: true, taken: false }
            ];
        })()""")
        sfx_events.append((t, "gold_fart"))
    if f_idx in (int(6.10 * fps), int(7.20 * fps), int(8.20 * fps)):
        cdp.eval_js("window.__OJ_DEBUG.state.justRingTimer=0.28; window.__OJ_DEBUG.state.fartCooldown=0; window.__OJ_DEBUG.fireFart(false);")
        sfx_events.append((t, "gold_fart"))
    if f_idx == int(9.05 * fps):
        cdp.eval_js("(() => { const d=window.__OJ_DEBUG; d.state.xp=0; d.addXp(d.state.nextXp); })()")
    if f_idx == int(10.10 * fps):
        cdp.eval_js('(() => { const el=document.querySelector("#skill-choice-list .skill-choice"); if(el) el.click(); window.__OJ_DEBUG.state.xp=0; })()')

    # SCENE 4 (10.80 - 15.80s): SHARK MISSILE NEAR-MISS -> YOKOHAMA/FUJI EVO STORM!
    if f_idx == int(10.80 * fps):
        cdp.eval_js("""(() => {
            const d = window.__OJ_DEBUG;
            document.getElementById('screen-lvup').classList.add('hidden');
            d.state.phase = 'flying';
            d.state.xp = 0; d.state.nextXp = 999999;
            d.state.x = 122; d.state.y = 9.0; d.state.vx = 19; d.state.vy = 2.0; d.state.gas = 88;
            for (let i=0;i<5;i++) d.selectSkill('imo');
            for (let i=0;i<5;i++) d.selectSkill('missile');
            d.selectSkill('aura'); d.selectSkill('aura'); d.selectSkill('thunder');
            d.state.ambushes = [{ warn: 0.68, x: 146, y: 9.6, fired: false, nearMissed: false, dead: false }];
        })()""")
    if f_idx == int(11.95 * fps):
        # Burst upward with fart to near-miss dodge the incoming shark missile!
        cdp.eval_js("window.__OJ_DEBUG.state.justRingTimer=0.28; window.__OJ_DEBUG.state.fartCooldown=0; window.__OJ_DEBUG.fireFart(false);")
        sfx_events.append((t, "gold_fart"))
    if f_idx in (int(13.40 * fps), int(14.55 * fps)):
        cdp.eval_js("window.__OJ_DEBUG.state.fartCooldown=0; window.__OJ_DEBUG.fireFart(false);")
        sfx_events.append((t, "gold_fart"))

    # SCENE 5 (15.80 - 18.80s): DRAMATIC SKID LANDING -> "あとちょっとで韓国ソウルだったのに!!"
    if f_idx == int(15.80 * fps):
        cdp.eval_js("""(() => {
            const d = window.__OJ_DEBUG;
            document.getElementById('screen-lvup').classList.add('hidden');
            d.state.phase = 'flying';
            d.state.xp = 0; d.state.nextXp = 999999;
            d.state.x = 810; d.state.y = 1.8; d.state.vx = 11.0; d.state.vy = -2.5; d.state.gas = 0;
        })()""")
    if f_idx == int(16.75 * fps):
        cdp.eval_js("window.__OJ_DEBUG.state.y = 0; window.__OJ_DEBUG.state.vx = 0.4; window.__stepSim(0.05, 2);")

    # SCENE 6 (18.80 - 25.00s): LIVE ACTION LOOP BEHIND SUBSCRIBE & COMMENT CTAs
    if f_idx == int(18.80 * fps):
        cdp.eval_js("""(() => {
            const d = window.__OJ_DEBUG;
            d.startRun();
            d.state.phase = 'flying';
            d.state.xp = 0; d.state.nextXp = 999999;
            d.state.x = 265; d.state.y = 8.5; d.state.vx = 18.0; d.state.vy = 4.0; d.state.gas = 92;
            for (let i=0;i<5;i++) d.selectSkill('imo');
            for (let i=0;i<5;i++) d.selectSkill('missile');
            for (let i=0;i<5;i++) d.selectSkill('rocket');
            d.selectSkill('aura'); d.selectSkill('aura');
            d.state.feverTimer = 4.0;
        })()""")
    if f_idx >= int(18.90 * fps) and f_idx % 12 == 0:
        cdp.eval_js("window.__OJ_DEBUG.state.xp=0; window.__OJ_DEBUG.state.fartCooldown=0; window.__OJ_DEBUG.fireFart(true);")


def render_note_thumbnail(browser: str, game_png_path: Path, out_png: Path, day_num: int = 10):
    b64 = base64.b64encode(game_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: linear-gradient(135deg, #38bdf8 0%, #fde047 55%, #f97316 100%);
  font-family:'Noto Sans CJK JP','Noto Sans JP',sans-serif;
  color:#111827;display:flex;align-items:center;justify-content:space-between;
  padding:42px 54px;position:relative;
}}
body::before{{content:'';position:absolute;inset:16px;border:5px solid #111827;border-radius:22px;pointer-events:none;}}
.left{{width:735px;z-index:2;}}
.top-row{{display:flex;align-items:center;gap:16px;margin-bottom:16px;}}
.day-plate{{
  display:inline-flex;align-items:center;justify-content:center;padding:8px 28px;border-radius:14px;
  background:#ef4444;border:4px solid #111827;color:#ffffff;font-weight:900;font-size:48px;line-height:1.0;
  box-shadow:5px 5px 0 #111827;
}}
.badge{{
  display:inline-block;padding:8px 20px;border-radius:999px;background:#ffffff;border:3px solid #111827;
  color:#111827;font-weight:900;font-size:21px;box-shadow:3px 3px 0 #111827;
}}
h1{{font-size:62px;line-height:1.08;font-weight:900;margin-bottom:14px;}}
h1 span{{color:#dc2626;}}
.sub{{font-size:27px;font-weight:900;color:#111827;line-height:1.4;margin-bottom:22px;}}
.chips{{display:flex;gap:10px;flex-wrap:wrap;}}
.chip{{padding:8px 15px;border-radius:12px;background:#ffffff;border:3px solid #111827;font-size:19px;font-weight:900;box-shadow:3px 3px 0 #111827;}}
.phone{{width:318px;height:568px;border-radius:36px;padding:10px;background:#111827;border:4px solid #ffffff;box-shadow:10px 10px 0 rgba(17,24,39,0.35);transform:rotate(2.2deg);}}
.phone img{{width:100%;height:100%;object-fit:cover;border-radius:26px;}}
</style></head><body>
  <div class="left">
    <div class="top-row"><div class="day-plate">DAY {day_num}</div><div class="badge">東京発・世界の何m飛べる？</div></div>
    <h1>おなら<span>立ち幅跳び</span> 999</h1>
    <div class="sub">単純なのに中毒性ヤバいXバズ系バカ物理!!<br/>サメミサイルを紙一重回避して世界へぶっ飛べ！</div>
    <div class="chips"><div class="chip">🗼 東京→世界</div><div class="chip">⚡ Lv.5超進化</div><div class="chip">😱 紙一重回避</div></div>
  </div>
  <div class="phone"><img src="data:image/png;base64,{b64}"/></div>
</body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        tmp_html = tf.name
    try:
        subprocess.run([browser, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", f"--screenshot={out_png}", "--window-size=1280,670", f"file://{tmp_html}"], check=True)
    finally:
        os.unlink(tmp_html)


def main():
    browser = find_browser()
    srv, port = start_static_server(ROOT)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
    profile_dir = tempfile.mkdtemp(prefix="cdp_day10_shorts_")
    proc = subprocess.Popen(
        [browser, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--remote-allow-origins=*",
         f"--user-data-dir={profile_dir}", f"--remote-debugging-port={dbg_port}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.*"):
        old.unlink()

    fps = 24
    dt_sec = 1.0 / fps
    total_dur = 25.0
    total_frames = int(fps * total_dur)

    try:
        ws_url = None
        for _ in range(80):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{dbg_port}/json/list", timeout=1).read())
                ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"), None)
                if ws_url:
                    break
            except Exception:
                time.sleep(0.15)
        assert ws_url, "CDP connect failed"

        cdp = SimpleCDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        # Fast 540x960 CSS @ dpr=1 capture upscaled cleanly with crisp 1080x1920 PIL vector overlays
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 540, "height": 960, "deviceScaleFactor": 1.0, "mobile": True})
        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day10-onara-long-jump/index.html?shorts=1"})
        for _ in range(60):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        cdp.eval_js("window.__manualStep = true;")

        fonts = {
            "badge": ImageFont.truetype(FONT_SANS, 30),
            "hdr": ImageFont.truetype(FONT_SANS, 34),
            "tiny": ImageFont.truetype(FONT_SANS, 21),
            "hook_sm": ImageFont.truetype(FONT_SANS, 54),
            "hook_lg": ImageFont.truetype(FONT_SANS, 88),
            "sub": ImageFont.truetype(FONT_SANS, 56),
            "cta_h": ImageFont.truetype(FONT_SANS, 52),
            "cta_lg": ImageFont.truetype(FONT_SANS, 68),
            "yt_name": ImageFont.truetype(FONT_SANS, 34),
            "yt_meta": ImageFont.truetype(FONT_SANS, 24),
            "yt_btn": ImageFont.truetype(FONT_SANS, 31),
        }

        sfx_events = []
        impact_peaks = [0.15, 0.65, 1.35, 3.65, 5.20, 12.60, 16.75, 20.15]
        cut_times = [1.35, 5.10, 10.80, 15.80, 18.80, 22.00]
        thumb_src = OUT_DIR / "_thumb_src.png"

        preview_dir = (ART_DIR / "scratch") if ART_DIR.exists() else None
        if preview_dir is not None:
            preview_dir.mkdir(parents=True, exist_ok=True)
        preview_targets = {
            int(0.25 * fps): "s1_impact_0s25",
            int(3.95 * fps): "s2_fail_3s95",
            int(9.50 * fps): "s3_lvup_9s50",
            int(12.60 * fps): "s4_nearmiss_12s60",
            int(17.20 * fps): "s5_result_17s20",
            int(20.30 * fps): "s6a_sub_20s30",
            int(23.50 * fps): "s6b_comment_23s50",
        }

        print(f"Rendering {total_frames} frames ({total_dur}s @ {fps}fps, 540x960->1080x1920)...", flush=True)
        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            choreograph_game(cdp, f_idx, t, fps, sfx_events)
            # Single CDP roundtrip for physics step + sim_x
            sim_x = float(cdp.eval_js(f"window.__stepFrame({dt_sec:.6f}); window.__OJ_DEBUG.state.x") or 0.0)

            shot_b64 = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 94})["data"]
            raw_img = Image.open(io.BytesIO(base64.b64decode(shot_b64))).convert("RGB")
            if f_idx == int(12.90 * fps):
                raw_img.resize((1080, 1920), Image.Resampling.LANCZOS).save(thumb_src)

            imp = max([math.exp(-abs(t - pk) * 7.0) for pk in impact_peaks] + [0.0])
            fl = max([math.exp(-max(0.0, t - ct) * 14.0) if t >= ct else 0.0 for ct in cut_times] + [0.0])
            comp = draw_frame_overlay(raw_img, t, total_dur, sim_x, imp, fl, fonts)
            comp.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=94)

            if preview_dir is not None and f_idx in preview_targets:
                comp.save(preview_dir / f"preview_{preview_targets[f_idx]}.png")

            if f_idx % 120 == 0:
                print(f"  Frame {f_idx}/{total_frames} (simX={sim_x:.1f})", flush=True)

        wav_path = OUT_DIR / "audio_master.wav"
        print("Synthesizing 132 BPM comedy-funk BGM + SFX + Keita narration...", flush=True)
        synthesize_audio_track(wav_path, total_dur, sfx_events)

        mp4_path = OUT_DIR / "day10_short.mp4"
        print(f"Encoding final {mp4_path} via ffmpeg...", flush=True)
        subprocess.run([
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%04d.jpg"),
            "-i", str(wav_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            str(mp4_path),
        ], check=True)

        if thumb_src.exists():
            render_note_thumbnail(browser, thumb_src, OUT_DIR / "note_thumbnail.png", 10)
            if ART_DIR.exists():
                (ART_DIR / "note_thumbnail.png").write_bytes((OUT_DIR / "note_thumbnail.png").read_bytes())
                (ART_DIR / "day10_short.mp4").write_bytes(mp4_path.read_bytes())
            thumb_src.unlink(missing_ok=True)

        shutil.rmtree(frames_dir, ignore_errors=True)
        wav_path.unlink(missing_ok=True)
        print("SUCCESS! Video ready:", mp4_path, "bytes:", mp4_path.stat().st_size, flush=True)
    finally:
        proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
