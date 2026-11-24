#!/usr/bin/env python3
"""
Day 09 YouTube Shorts (1080x1920, 24fps, 28.5s) — OVERCLOCK GUNNER 3D (20-Weapon Chaos Roulette)
Pro YouTube Shorts Production Pipeline:
- Native crisp 1080x1920 WebGL capture via headless Chrome CDP (540x960 @ dpr=2, deterministic 24fps)
- 0.00-2.10s: High-impact Cold-Open (#20 CHAOS OMNIGUN + Orbital Laser + Boss) + chromatic split + speedlines + bold hook
- 2.10-4.00s: Authentic Arcade Title Screen showcase (live 3D cyber highway & rotating weapons)
- 4.00-8.15s: Weapon Roulette 1: #04 DUAL SAWED-OFF + Chain Blast -> SHIFT -> #15 RICOCHET SAW bouncing disc
- 8.15-12.50s: Weapon Roulette 2: #19 CYBER KATANA slicing enemies & missiles -> SHIFT -> #13 CRYO FREEZE RAY
- 12.50-16.40s: Weapon Roulette 3: #14 TESLA ARC -> #17 NOVA SINGULARITY Black Hole -> #09 DUAL PLASMA VULCAN
- 16.40-21.15s: Boss Climax: VALKYRIE-ZERO Charge Laser -> JUST DODGE!! -> OVERDRIVE LOCK -> #18 OMEGA ORBITAL!
- 21.15-25.15s: Animated YouTube Subscribe Button CTA (clicks into 登録済み!) over live #20 CHAOS OMNIGUN Overdrive
- 25.15-28.50s: Animated YouTube Comment Request CTA over live Cyber Katana + Orbital Finale
- Human-like natural Japanese narration (ja-JP-NanamiNeural, studio condenser mic mastering + auto-ducking)
- Stereo 138 BPM Cyberpunk Synthwave Action BGM + frame-accurate gunfire/explosion/shift/bell SFX
- Outputs:
    shorts/day09/output/day09_short.mp4
    shorts/day09/output/note_thumbnail.png
    shorts/day09/output/youtube_metadata.txt
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
OUT_DIR = ROOT / "shorts" / "day09" / "output"
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
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
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


# Natural, human-like YouTube Shorts narration cues
NARRATION_CUES = [
    (0.06,  "えっ、全20種の3D武器がランダムに切り替わるFPS、ヤバすぎ！", "+17%", "+3Hz"),
    (4.05,  "9秒ごとに武器が強制チェンジ！二丁散弾から跳弾ノコギリへ！", "+16%", "+2Hz"),
    (8.25,  "サイバー刀でミサイルも真っ二つ！冷凍ビームで敵を凍らせて…", "+15%", "+2Hz"),
    (12.60, "連鎖雷撃にブラックホール、二丁プラズマバルカンまで全20種類！", "+16%", "+2Hz"),
    (16.50, "ボス戦では極太レーザーを回避して、衛星レーザーで一気に殲滅だ！", "+16%", "+3Hz"),
    (21.20, "100日後にバズるゲームを見たい人は、チャンネル登録よろしく！", "+14%", "+1Hz"),
    (25.20, "作ってほしいゲームがあったら、コメント欄で教えてね！", "+14%", "+2Hz"),
]


def synthesize_tts_line(text: str, out_wav: Path, rate: str = "+15%", pitch: str = "+2Hz", sr: int = 44100) -> bool:
    """Synthesize natural Japanese YouTube voiceover with studio condenser mic mastering."""
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    try:
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(
                text,
                voice="ja-JP-NanamiNeural",
                rate=rate,
                pitch=pitch,
            )
            await asyncio.wait_for(comm.save(str(tmp_mp3)), timeout=15.0)

        asyncio.run(_gen())
        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 500:
            af = (
                "silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,"
                "areverse,silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,areverse,"
                "highpass=f=85,"
                "equalizer=f=180:t=q:w=1.2:g=2.4,"
                "equalizer=f=3200:t=q:w=1.4:g=1.9,"
                "equalizer=f=6800:t=q:w=2.0:g=-1.5,"
                "acompressor=threshold=-17dB:ratio=2.4:attack=8:release=85:makeup=1.6,"
                "aecho=0.85:0.88:18:0.055"
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(tmp_mp3),
                    "-af", af,
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
                ],
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
    ang = (pan + 1.0) * 0.25 * math.pi
    gl = math.cos(ang) * gain
    gr = math.sin(ang) * gain
    buf_l[idx : idx + ln] += sig[:ln] * gl
    buf_r[idx : idx + ln] += sig[:ln] * gr


def generate_audio(total_dur: float, events: list, wav_path: Path):
    sr = 44100
    n_samples = int(total_dur * sr)
    bgm_l = np.zeros(n_samples, dtype=np.float32)
    bgm_r = np.zeros(n_samples, dtype=np.float32)
    sfx_l = np.zeros(n_samples, dtype=np.float32)
    sfx_r = np.zeros(n_samples, dtype=np.float32)
    voice = np.zeros(n_samples, dtype=np.float32)

    # 138 BPM Hard-Hitting Cyberpunk Synthwave / Arcade Shooter Stereo Beat (Am - F - C - G)
    bpm = 138.0
    step_dur = 60.0 / bpm / 4.0  # 16th note
    bar_dur = step_dur * 16.0

    chords = [
        (55.00, [220.00, 261.63, 329.63, 440.00]),  # Am
        (43.65, [174.61, 220.00, 261.63, 349.23]),  # F
        (65.41, [196.00, 261.63, 329.63, 392.00]),  # C
        (49.00, [196.00, 246.94, 293.66, 392.00]),  # G
    ]
    arp_idx = [0, 3, 2, 1, 2, 3, 1, 0, 3, 2, 3, 1, 2, 0, 1, 3]

    num_bars = int(math.ceil(total_dur / bar_dur))
    for bar in range(num_bars):
        b0 = int(bar * bar_dur * sr)
        b_len = min(int(bar_dur * sr), n_samples - b0)
        if b_len <= 0:
            break
        bt = np.arange(b_len, dtype=np.float32) / sr
        _, tones = chords[bar % len(chords)]
        pad_l = np.zeros(b_len, dtype=np.float32)
        pad_r = np.zeros(b_len, dtype=np.float32)
        for ti, f in enumerate(tones):
            # Lush detuned cyberpunk supersaw-like pad
            pad_l += np.tanh(np.sin(2.0 * math.pi * (f * 1.003) * bt + ti * 0.5) * 1.6) * 0.20
            pad_r += np.tanh(np.sin(2.0 * math.pi * (f * 0.997) * bt + ti * 1.1) * 1.6) * 0.20
            pad_l += np.sin(2.0 * math.pi * (f * 2.002) * bt) * 0.05
            pad_r += np.sin(2.0 * math.pi * (f * 1.998) * bt) * 0.05
        beat_phase = (bt % (step_dur * 4.0)) / (step_dur * 4.0)
        pump = 0.35 + 0.65 * np.minimum(1.0, beat_phase * 3.0)
        env = np.minimum(1.0, bt / 0.03) * np.minimum(1.0, (bar_dur - bt).clip(0) / 0.05)
        bgm_l[b0 : b0 + b_len] += pad_l * pump * env * 0.14
        bgm_r[b0 : b0 + b_len] += pad_r * pump * env * 0.14

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        t_step = i * step_dur
        s0 = int(t_step * sr)
        if s0 >= n_samples:
            break
        step16 = i % 16
        bar = i // 16
        bass_f, tones = chords[bar % len(chords)]

        # Punchy electro kick
        if step16 in (0, 4, 8, 12) or (bar % 2 == 1 and step16 == 14):
            k_len = min(int(0.17 * sr), n_samples - s0)
            lt = np.arange(k_len, dtype=np.float32) / sr
            kf = 46.0 + 135.0 * np.exp(-lt * 36.0)
            kick = np.tanh(np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * 2.5) * np.exp(-lt * 13.0)
            add_stereo(bgm_l, bgm_r, s0, kick, pan=0.0, gain=0.25)

        # Gated synthwave snare on 4 & 12
        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 409)
            sn_len = min(int(0.14 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            noise = rng.uniform(-1.0, 1.0, sn_len).astype(np.float32)
            bright = np.diff(noise, prepend=0.0)
            body = np.sin(2.0 * math.pi * 195.0 * slt) * np.exp(-slt * 22.0) * 0.45
            snare = bright * np.exp(-slt * 20.0) * 0.72 + body
            add_stereo(bgm_l, bgm_r, s0, snare, pan=0.07 if step16 == 4 else -0.07, gain=0.17)

        # Driving 16th hi-hats
        if step16 % 2 == 0 or step16 in (3, 7, 11, 15):
            rng = np.random.default_rng(seed=i + 901)
            hh_len = min(int(0.036 * sr), n_samples - s0)
            hlt = np.arange(hh_len, dtype=np.float32) / sr
            h_noise = np.diff(rng.uniform(-1.0, 1.0, hh_len).astype(np.float32), prepend=0.0)
            hat = h_noise * np.exp(-hlt * (52.0 if step16 % 4 == 2 else 95.0))
            add_stereo(bgm_l, bgm_r, s0, hat, pan=-0.28 if step16 % 4 == 0 else 0.28, gain=0.055)

        # Rolling cyberpunk 16th octave bassline
        if step16 % 2 == 0 or step16 in (3, 11, 15):
            blen = min(int(step_dur * 1.3 * sr), n_samples - s0)
            blt = np.arange(blen, dtype=np.float32) / sr
            bf = bass_f * (2.0 if step16 in (2, 6, 10, 14, 15) else 1.0)
            bs = (
                np.sin(2.0 * math.pi * bf * blt) * 0.65
                + np.sin(2.0 * math.pi * bf * 2.0 * blt) * 0.30
                + np.sin(2.0 * math.pi * bf * 3.0 * blt) * 0.14
            )
            bs = np.tanh(bs * 1.9) * np.exp(-blt * 9.5)
            add_stereo(bgm_l, bgm_r, s0, bs, pan=0.0, gain=0.17)

        # Neon cyber lead arpeggio
        plen = min(int(0.12 * sr), n_samples - s0)
        plt = np.arange(plen, dtype=np.float32) / sr
        pf = tones[arp_idx[step16]] * 2.0
        pluck = np.tanh(
            (np.sin(2.0 * math.pi * pf * plt) * 0.65 + np.sin(2.0 * math.pi * pf * 2.0 * plt) * 0.30) * 1.5
        ) * np.exp(-plt * 19.0)
        add_stereo(bgm_l, bgm_r, s0, pluck, pan=-0.38 if step16 % 2 == 0 else 0.38, gain=0.068)

    # Editorial & Combat SFX helpers
    def add_whoosh(t_sec: float, gain: float = 0.26):
        idx = int(t_sec * sr)
        wlen = int(0.18 * sr)
        wt = np.arange(wlen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 17)
        wn = rng.uniform(-1.0, 1.0, wlen).astype(np.float32)
        env = np.sin(math.pi * wt / 0.18) ** 1.6
        sweep = np.sin(2.0 * math.pi * np.cumsum(280.0 + 1600.0 * (wt / 0.18)) / sr) * 0.35
        add_stereo(sfx_l, sfx_r, idx, (wn * 0.45 + sweep) * env, pan=0.0, gain=gain)

    def add_gun_punch(t_sec: float, lv: int = 3):
        idx = int(t_sec * sr)
        dur = 0.18 if lv in (3, 6) else 0.085
        glen = int(dur * sr)
        gt = np.arange(glen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 10000) + lv)
        n = rng.uniform(-1.0, 1.0, glen).astype(np.float32) * np.exp(-gt * (18.0 if lv in (3, 6) else 34.0))
        f0 = 760.0 if lv == 6 else (150.0 if lv == 3 else 220.0)
        osc = np.tanh(np.sin(2.0 * math.pi * np.cumsum(f0 * np.exp(-gt * 20.0) + 52.0) / sr) * 2.0) * np.exp(-gt * 18.0)
        gain = 0.28 if lv in (3, 6) else 0.15
        add_stereo(sfx_l, sfx_r, idx, n * 0.52 + osc * 0.48, pan=((idx % 3) - 1) * 0.12, gain=gain)

    def add_explosion_boom(t_sec: float, power: float = 1.0):
        idx = int(t_sec * sr)
        elen = int(0.46 * sr)
        lt = np.arange(elen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 51)
        snap = rng.uniform(-1.0, 1.0, elen).astype(np.float32) * np.exp(-lt * 14.0) * 0.40
        boom = np.tanh(np.sin(2.0 * math.pi * np.cumsum(190.0 * np.exp(-lt * 12.0) + 36.0) / sr) * 2.8) * np.exp(-lt * 6.5) * 0.56
        add_stereo(sfx_l, sfx_r, idx, snap + boom, pan=0.0, gain=0.68 * power)

    def add_shift_chime(t_sec: float, gain: float = 0.26):
        idx = int(t_sec * sr)
        clen = int(0.32 * sr)
        ct = np.arange(clen, dtype=np.float32) / sr
        sig = np.zeros(clen, dtype=np.float32)
        for k, fq in enumerate((523.25, 659.25, 783.99, 1046.5)):
            off = int(k * 0.04 * sr)
            if off < clen:
                lt = np.arange(clen - off, dtype=np.float32) / sr
                sig[off:] += np.sin(2.0 * math.pi * fq * lt) * np.exp(-lt * 14.0) * 0.45
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    def add_bell_ding(t_sec: float, gain: float = 0.34):
        idx = int(t_sec * sr)
        blen = int(0.42 * sr)
        bt = np.arange(blen, dtype=np.float32) / sr
        c1 = (np.sin(2.0 * math.pi * 1046.5 * bt) * 0.7 + np.sin(2.0 * math.pi * 2093.0 * bt) * 0.3) * np.exp(-bt * 12.0)
        d2 = int(0.085 * sr)
        c2 = np.zeros_like(c1)
        if d2 < blen:
            bt2 = np.arange(blen - d2, dtype=np.float32) / sr
            c2[d2:] = (np.sin(2.0 * math.pi * 1567.98 * bt2) * 0.75 + np.sin(2.0 * math.pi * 3135.96 * bt2) * 0.25) * np.exp(-bt2 * 9.0)
        add_stereo(sfx_l, sfx_r, idx, c1 + c2, pan=0.0, gain=gain)

    def add_pop(t_sec: float, freq: float = 780.0, gain: float = 0.24):
        idx = int(t_sec * sr)
        plen = int(0.11 * sr)
        pt = np.arange(plen, dtype=np.float32) / sr
        pf = freq * (1.0 + 0.55 * np.exp(-pt * 35.0))
        sig = np.sin(2.0 * math.pi * np.cumsum(pf) / sr) * np.exp(-pt * 24.0)
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    # Editorial transitions & signature YouTube CTA sounds
    for wt in (2.08, 3.98, 6.08, 8.12, 10.35, 12.48, 14.35, 16.38, 21.12, 25.12):
        add_whoosh(wt, gain=0.22)
    add_explosion_boom(0.35, power=1.15)  # Cold-open 1st-second orbital explosion hook!
    add_bell_ding(22.60, gain=0.36)       # Subscribe button clicked -> 登録済み🔔!
    add_pop(25.25, freq=820.0, gain=0.24) # Comment card pop!

    # Frame-accurate gameplay SFX from recorded JS game events (with light rate-limit so rapid minigun stays crisp)
    last_gun_t = -1.0
    last_boom_t = -1.0
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        kind = ev.get("type")
        if kind == "gun":
            if t0 - last_gun_t >= 0.09:
                add_gun_punch(t0, int(ev.get("lv", 3)))
                last_gun_t = t0
        elif kind in ("boom", "boom_big"):
            if t0 - last_boom_t >= 0.18:
                add_explosion_boom(t0, power=0.92 if kind == "boom_big" else 0.55)
                last_boom_t = t0
        elif kind == "shift":
            add_shift_chime(t0, gain=0.28)
        elif kind == "dodge":
            add_whoosh(t0, gain=0.28)

    # Human-like Japanese Voiceover + Smooth Auto-Ducking
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day09_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.11 * sr)
        for idx, (cue_t, line_txt, rate, pitch) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, rate=rate, pitch=pitch, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.92
                s0 = max(int(cue_t * sr), prev_end_s + int(0.08 * sr))
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    prev_end_s = s0 + s_len
                    d0 = max(0, s0 - ramp_n)
                    d1 = min(n_samples, s0 + s_len + ramp_n)
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.25)
                    if s0 > d0:
                        duck[d0:s0] = np.minimum(duck[d0:s0], np.linspace(1.0, 0.25, s0 - d0, dtype=np.float32))
                    if d1 > s0 + s_len:
                        duck[s0 + s_len : d1] = np.minimum(duck[s0 + s_len : d1], np.linspace(0.25, 1.0, d1 - (s0 + s_len), dtype=np.float32))
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    # Final Stereo Master Mix
    mix_l = bgm_l * duck + sfx_l * 0.80 + voice * 0.98
    mix_r = bgm_r * duck + sfx_r * 0.80 + voice * 0.98
    mix_l = np.tanh(mix_l * 1.12) * 0.92
    mix_r = np.tanh(mix_r * 1.12) * 0.92

    stereo = np.empty(n_samples * 2, dtype=np.int16)
    stereo[0::2] = np.clip(mix_l * 32767.0, -32767, 32767).astype(np.int16)
    stereo[1::2] = np.clip(mix_r * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def apply_chromatic_split(img: Image.Image, shift: int) -> Image.Image:
    if shift <= 0:
        return img
    r, g, b = img.split()
    r = ImageChops.offset(r, shift, 0)
    b = ImageChops.offset(b, -shift, 0)
    return Image.merge("RGB", (r, g, b))


def draw_rounded_box(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 0):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_rich_subtitle_line(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    y: int,
    tokens: list,
    font: ImageFont.FreeTypeFont,
    outer_stroke: int = 12,
    inner_stroke: int = 5,
):
    widths = [draw.textlength(txt, font=font) for txt, _ in tokens]
    total_w = sum(widths)
    cur_x = center_x - total_w / 2.0

    cx = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((cx + 5, y + 7), txt, font=font, fill=(0, 0, 0, 215), stroke_width=outer_stroke + 2, stroke_fill=(0, 0, 0, 200))
        cx += w

    cx = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((cx, y), txt, font=font, fill=(10, 16, 30, 255), stroke_width=outer_stroke, stroke_fill=(8, 12, 24, 255))
        cx += w

    cx = cur_x
    for (txt, color), w in zip(tokens, widths):
        draw.text((cx, y), txt, font=font, fill=(*color, 255), stroke_width=inner_stroke, stroke_fill=(12, 18, 34, 255))
        cx += w


def draw_shorts_overlay(
    frame_img: Image.Image,
    t: float,
    total_dur: float,
    section_pill: str,
    accent_rgb: tuple,
    sub_lines: list,
    seg_start: float,
    impact_pulse: float,
    trans_flash: float,
    fonts: dict,
) -> Image.Image:
    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.LANCZOS)

    if impact_pulse > 0.14:
        frame_img = apply_chromatic_split(frame_img, int(14 * impact_pulse))

    img = frame_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size

    # Subtle bottom dark gradient vignette so subtitles & CTA cards stay crisp
    for gy in range(0, 420, 14):
        alpha = int(125 * (gy / 420.0) ** 1.4)
        draw.rectangle((0, H - 420 + gy, W, H - 420 + gy + 14), fill=(4, 8, 18, alpha))

    # Impact Anime Speedlines
    if impact_pulse > 0.22:
        cx, cy = W // 2, int(H * 0.44)
        for i in range(28):
            ang = (i / 28.0) * math.tau + t * 5.2
            r1 = 310 + (i % 3) * 50
            r2 = 1140
            x1 = cx + int(math.cos(ang) * r1)
            y1 = cy + int(math.sin(ang) * r1)
            x2 = cx + int(math.cos(ang) * r2)
            y2 = cy + int(math.sin(ang) * r2)
            draw.line((x1, y1, x2, y2), fill=(*accent_rgb, int(185 * impact_pulse)), width=8 if i % 2 == 0 else 3)

    # 1. PRO YOUTUBE CHANNEL HEADER BAR (Top Safe Zone Y=68)
    pill_y0, pill_y1 = 68, 128
    draw_rounded_box(draw, (38, pill_y0, 566, pill_y1), 30, fill=(8, 14, 28, 220), outline=(255, 255, 255, 50), width=2)
    draw_rounded_box(draw, (46, pill_y0 + 7, 174, pill_y1 - 7), 22, fill=(235, 32, 54, 255))
    draw.text((62, pill_y0 + 14), "DAY 09", font=fonts["chip_b"], fill=(255, 255, 255, 255))
    draw.text((190, pill_y0 + 14), "100日後にバズるゲーム", font=fonts["chip"], fill=(242, 246, 255, 255))

    if section_pill:
        sw = int(draw.textlength(section_pill, font=fonts["chip_b"])) + 44
        sx0 = W - 38 - sw
        draw_rounded_box(draw, (sx0, pill_y0, W - 38, pill_y1), 30, fill=(8, 14, 28, 220), outline=(*accent_rgb, 225), width=3)
        draw.text((sx0 + 22, pill_y0 + 14), section_pill, font=fonts["chip_b"], fill=(*accent_rgb, 255))

    # 2. FIRST-SECOND COLD-OPEN IMPACT HOOK (0.00s - 1.95s)
    if t < 1.95:
        fade = 1.0 if t < 1.65 else max(0.0, (1.95 - t) / 0.30)
        bounce = int(38 * math.exp(-t * 14.0))
        kick_y = int(16 * impact_pulse)
        rib_y = 265 - bounce - kick_y
        draw_rounded_box(draw, (145, rib_y, W - 145, rib_y + 62), 14, fill=(228, 28, 52, int(245 * fade)), outline=(255, 215, 0, int(255 * fade)), width=4)
        rib_txt = "全20種ランダム切替3Dシューティング!!"
        rw = draw.textlength(rib_txt, font=fonts["ribbon"])
        draw.text(((W - rw) / 2, rib_y + 11), rib_txt, font=fonts["ribbon"], fill=(255, 255, 255, int(255 * fade)))

        if fade > 0.2:
            draw_rich_subtitle_line(
                draw, W // 2, rib_y + 78,
                [("何が出るか", (250, 204, 21)), ("分からん!!", (255, 255, 255))],
                fonts["hook"], outer_stroke=16, inner_stroke=6,
            )

    # 3. WEAPON ROULETTE FEATURE RIBBON (4.00s - 16.35s)
    if 4.00 <= t < 16.35:
        if t < 8.15:
            btxt, bcol, b_age = "9.5秒ごとに全20種がランダム強制切替!!", (234, 88, 12, 245), t - 4.00
        elif t < 12.50:
            btxt, bcol, b_age = "刀波でミサイル両断 × 冷凍ビームで70%減速!!", (14, 165, 233, 245), t - 8.15
        else:
            btxt, bcol, b_age = "雷連鎖 × ブラックホール × 二丁プラズマ!!", (168, 85, 247, 245), t - 12.50
        pop = int(24 * math.exp(-b_age * 16.0))
        by = 152 - pop
        bw = int(draw.textlength(btxt, font=fonts["ribbon"])) + 56
        bx0 = (W - bw) // 2
        draw_rounded_box(draw, (bx0 + 6, by + 6, bx0 + bw + 6, by + 62), 30, fill=(0, 0, 0, 150))
        draw_rounded_box(draw, (bx0, by, bx0 + bw, by + 58), 30, fill=bcol, outline=(255, 255, 255, 245), width=3)
        draw.text((bx0 + 28, by + 9), btxt, font=fonts["ribbon"], fill=(255, 255, 255, 255))

    # 4. BOSS CLIMAX RIBBON (16.40s - 21.05s)
    if 16.40 <= t < 21.05:
        age = t - 16.40
        pop = int(26 * math.exp(-age * 16.0))
        by = 152 - pop
        btxt = "巨大ボス3種 × チャージレーザー回避決戦!!"
        bw = int(draw.textlength(btxt, font=fonts["ribbon"])) + 56
        bx0 = (W - bw) // 2
        draw_rounded_box(draw, (bx0 + 6, by + 6, bx0 + bw + 6, by + 62), 30, fill=(0, 0, 0, 155))
        draw_rounded_box(draw, (bx0, by, bx0 + bw, by + 58), 30, fill=(190, 18, 60, 245), outline=(250, 204, 21, 255), width=4)
        draw.text((bx0 + 28, by + 9), btxt, font=fonts["ribbon"], fill=(255, 255, 255, 255))

    # 5. AUTHENTIC YOUTUBE CREATOR SUBTITLES (Safe Zone above bottom HUD)
    if sub_lines and 2.10 <= t < 21.15:
        age = max(0.0, t - seg_start)
        pop_y = int(20 * math.exp(-age * 18.0))
        base_y = 1390 if len(sub_lines) == 2 else 1445
        for li, line_tokens in enumerate(sub_lines):
            draw_rich_subtitle_line(
                draw, W // 2, base_y + li * 80 + pop_y,
                line_tokens, fonts["sub_yt"], outer_stroke=13, inner_stroke=5,
            )

    # 6. MANDATORY SUBSCRIBE CTA (21.15s - 25.15s) over Live #20 CHAOS OMNIGUN!
    if 21.15 <= t < 25.15:
        age = t - 21.15
        pop_y = int(42 * math.exp(-age * 14.0))
        clicked = t >= 22.60
        click_age = max(0.0, t - 22.60)
        cx = W // 2

        draw_rich_subtitle_line(
            draw, cx, 1085 + pop_y,
            [("100日後に", (250, 204, 21)), ("バズるゲーム", (255, 255, 255)), ("見たい人は", (255, 255, 255))],
            fonts["cta_head"], outer_stroke=13, inner_stroke=5,
        )
        draw_rich_subtitle_line(
            draw, cx, 1165 + pop_y,
            [("チャンネル登録", (255, 72, 92)), ("よろしく!!", (255, 255, 255))],
            fonts["cta_head_lg"], outer_stroke=14, inner_stroke=5,
        )

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1285 + pop_y, 1445 + pop_y
        draw_rounded_box(draw, (x0 + 8, y0 + 12, x1 + 8, y1 + 12), 34, fill=(0, 0, 0, 175))
        draw_rounded_box(draw, (x0, y0, x1, y1), 34, fill=(18, 22, 34, 246), outline=(255, 255, 255, 55), width=3)

        av_cx, av_cy = x0 + 82, (y0 + y1) // 2
        draw.ellipse((av_cx - 48, av_cy - 48, av_cx + 48, av_cy + 48), fill=(0, 229, 255, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((av_cx - 32, av_cy - 18), "FPS", font=fonts["chip_b"], fill=(12, 16, 28, 255))

        draw.text((x0 + 148, y0 + 36), "100日後にバズるゲーム", font=fonts["yt_name"], fill=(255, 255, 255, 255))
        draw.text((x0 + 148, y0 + 88), "毎日1本ゲーム開発中！", font=fonts["yt_meta"], fill=(160, 174, 198, 255))

        btn_scale = 1.0 - 0.08 * math.exp(-click_age * 18.0) if clicked else (1.0 + 0.03 * math.sin(t * 10.0))
        bw = int(265 * btn_scale)
        bh = int(84 * btn_scale)
        bcx, bcy = x1 - 155, (y0 + y1) // 2
        bx0, by0, bx1, by1 = bcx - bw // 2, bcy - bh // 2, bcx + bw // 2, bcy + bh // 2

        if clicked:
            if click_age < 0.45:
                rr = int(45 + click_age * 240)
                ra = int(230 * (1.0 - click_age / 0.45))
                draw.ellipse((bcx - rr, bcy - rr, bcx + rr, bcy + rr), outline=(255, 212, 0, ra), width=7)
            draw_rounded_box(draw, (bx0, by0, bx1, by1), 42, fill=(52, 58, 72, 255), outline=(255, 255, 255, 110), width=3)
            btxt = "登録済み"
            tw = draw.textlength(btxt, font=fonts["yt_btn"])
            draw.text((bcx - tw / 2 - 14, bcy - 20), btxt, font=fonts["yt_btn"], fill=(235, 240, 248, 255))
            blx, bly = int(bcx + tw / 2 + 12), bcy
            draw.pieslice((blx - 13, bly - 16, blx + 13, bly + 10), 180, 360, fill=(250, 204, 21, 255))
            draw.rectangle((blx - 13, bly - 3, blx + 13, bly + 9), fill=(250, 204, 21, 255))
            draw.rectangle((blx - 17, bly + 8, blx + 17, bly + 13), fill=(250, 204, 21, 255))
            draw.ellipse((blx - 4, bly + 13, blx + 4, bly + 20), fill=(250, 204, 21, 255))
        else:
            draw_rounded_box(draw, (bx0, by0, bx1, by1), 42, fill=(230, 24, 42, 255), outline=(255, 224, 130, 255), width=4)
            btxt = "チャンネル登録"
            tw = draw.textlength(btxt, font=fonts["yt_btn"])
            draw.text((bcx - tw / 2, bcy - 20), btxt, font=fonts["yt_btn"], fill=(255, 255, 255, 255))

        if 21.60 <= t < 23.40:
            prog_c = min(1.0, max(0.0, (t - 21.60) / 0.95))
            ease = 1.0 - (1.0 - prog_c) ** 3
            px = int(bcx + 120 * (1.0 - ease))
            py = int(bcy + 145 * (1.0 - ease) + (8 if clicked and click_age < 0.14 else 0))
            poly = [(px, py), (px, py + 46), (px + 13, py + 34), (px + 25, py + 50), (px + 33, py + 45), (px + 21, py + 29), (px + 36, py + 29)]
            draw.polygon(poly, fill=(255, 255, 255, 255), outline=(12, 16, 28, 255))

    # 7. MANDATORY COMMENT REQUEST CTA (25.15s - 28.50s)
    if t >= 25.15:
        age = t - 25.15
        pop_y = int(44 * math.exp(-age * 14.0))
        cx = W // 2

        draw_rich_subtitle_line(
            draw, cx, 1085 + pop_y,
            [("作ってほしい", (56, 189, 248)), ("ゲームあったら", (255, 255, 255))],
            fonts["cta_head"], outer_stroke=13, inner_stroke=5,
        )
        draw_rich_subtitle_line(
            draw, cx, 1165 + pop_y,
            [("コメント欄", (250, 204, 21)), ("で教えてね!!", (255, 255, 255))],
            fonts["cta_head_lg"], outer_stroke=14, inner_stroke=5,
        )

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1288 + pop_y, 1468 + pop_y
        draw_rounded_box(draw, (x0 + 8, y0 + 12, x1 + 8, y1 + 12), 30, fill=(0, 0, 0, 180))
        draw_rounded_box(draw, (x0, y0, x1, y1), 30, fill=(16, 22, 36, 248), outline=(56, 189, 248, 245), width=4)

        draw.text((x0 + 38, y0 + 22), "コメント欄 // REQUEST BOX", font=fonts["yt_meta"], fill=(56, 189, 248, 255))
        draw_rounded_box(draw, (x0 + 34, y0 + 68, x1 - 34, y1 - 24), 18, fill=(28, 36, 56, 255), outline=(255, 255, 255, 40), width=2)
        sample = "「次はホラー脱出ゲーム作って！」"
        chars = min(len(sample), int(age * 16.0) + 1)
        cursor = "|" if int(t * 6.0) % 2 == 0 else ""
        draw.text((x0 + 58, y0 + 90), sample[:chars] + cursor, font=fonts["yt_name"], fill=(245, 248, 255, 255))

    # Crisp Scene-Cut Flash Transition
    if trans_flash > 0.02:
        draw.rectangle((0, 0, W, H), fill=(255, 255, 255, int(135 * trans_flash)))

    # Sleek Bottom Progress Bar
    prog = min(1.0, t / total_dur)
    draw.rectangle((0, H - 10, W, H), fill=(15, 23, 42, 200))
    draw.rectangle((0, H - 10, int(W * prog), H), fill=(*accent_rgb, 255))

    return Image.alpha_composite(img, overlay).convert("RGB")


def render_note_thumbnail(browser: str, game_png_path: Path, out_png: Path, day_num: int = 9):
    b64 = base64.b64encode(game_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: radial-gradient(circle at 75% 45%, #7e22ce 0%, #0f172a 48%, #040712 100%);
  font-family:'Noto Sans CJK JP','Noto Sans JP',sans-serif;
  color:#ffffff;display:flex;align-items:center;justify-content:space-between;
  padding:42px 54px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2.5px solid rgba(0,229,255,0.48);border-radius:22px;pointer-events:none;
}}
.left{{width:735px;z-index:2;}}
.top-row{{display:flex;align-items:center;gap:16px;margin-bottom:16px;}}
.day-plate{{
  display:inline-flex;align-items:center;justify-content:center;
  padding:8px 28px;border-radius:14px;
  background:linear-gradient(135deg,#ef4444 0%,#dc2626 55%,#f97316 100%);
  border:4px solid #ffffff;
  color:#ffffff;font-weight:900;font-size:48px;line-height:1.0;letter-spacing:0.04em;
  box-shadow:0 10px 28px rgba(239,68,68,0.58), 0 4px 12px rgba(0,0,0,0.65);
  transform:skewX(-8deg);
}}
.day-plate span{{transform:skewX(8deg);display:inline-block;}}
.badge{{
  display:inline-block;padding:10px 22px;border-radius:999px;
  background:rgba(15,23,42,0.88);border:2px solid rgba(0,229,255,0.75);
  color:#e2e8f0;font-weight:900;font-size:21px;letter-spacing:0.04em;
}}
h1{{
  font-size:68px;line-height:1.02;font-weight:900;color:#ffffff;margin-bottom:14px;
  text-shadow:0 8px 24px rgba(0,0,0,0.78);
}}
h1 span{{color:#facc15;}}
.sub{{font-size:28px;font-weight:900;color:#e2e8f0;line-height:1.4;margin-bottom:24px;}}
.sub strong{{color:#00e5ff;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(15,23,42,0.88);
  border:2px solid rgba(250,204,21,0.72);font-size:19px;font-weight:800;color:#ffffff;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #facc15;
  box-shadow:0 24px 60px rgba(0,0,0,0.75), 0 0 46px rgba(0,229,255,0.55);
  transform:rotate(2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:28px;left:-52px;transform:rotate(-8deg);
  padding:10px 24px;border-radius:14px;background:linear-gradient(90deg,#facc15,#ff2255);
  border:3.5px solid #ffffff;color:#ffffff;font-weight:900;font-size:26px;
  box-shadow:0 12px 28px rgba(0,0,0,0.65);text-shadow:0 2px 6px rgba(0,0,0,0.6);
}}
</style></head><body>
  <div class="left">
    <div class="top-row">
      <div class="day-plate"><span>DAY {day_num}</span></div>
      <div class="badge">100日後にバズるゲーム ｜ 一人称3D FPS</div>
    </div>
    <h1>OVERCLOCK<br><span>GUNNER 3D</span></h1>
    <div class="sub"><strong>全20種ランダム武器切替×3種巨大ボス!!</strong><br>冷凍ビーム・跳弾ノコギリ・サイバー刀・衛星レーザー砲</div>
    <div class="chips">
      <div class="chip">全20種ランダム武器</div>
      <div class="chip">刀波・黒穴・衛星砲</div>
      <div class="chip">スマホ縦＆横フル対応</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">DAY {day_num} 全20種ルーレット!!</div>
  </div>
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
    src = ROOT / "notes" / "day09" / "youtube_metadata.txt"
    if src.exists():
        out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return
    out_path.write_text(
        "[YouTube Shorts タイトル]\n"
        "【Day 9】全20種の3D武器が9.5秒ごとにランダム強制切替！冷凍ビーム→跳弾ノコギリ→サイバー刀→ブラックホール砲で切り抜けるFPSがヤバすぎた!! #FPS #シューティング #Shorts\n",
        encoding="utf-8",
    )


def choreograph_frame(cdp: SimpleCDP, f_idx: int, t: float, fps: int):
    """Drive dramatic, uninterrupted 3D gameplay actions synced cleanly to our 28.5s storyboard."""
    # SCENE 1 (0.00 - 2.10s): COLD OPEN — #20 CHAOS OMNIGUN + VALKYRIE-ZERO + ORBITAL LASER!
    if f_idx == 0:
        cdp.eval_js("""
          window.__OG_DEBUG.startRun(true);
          window.__OG_DEBUG.spawnBossSector(2);
          window.__OG_DEBUG.state.boss.hp = 24000;
          window.__OG_DEBUG.state.boss.maxHp = 24000;
          window.__OG_DEBUG.state.boss.pos.z = -14.5;
          window.__OG_DEBUG.setWeaponIdx(19);
          window.__OG_DEBUG.state.odGauge = 100;
          window.__OG_DEBUG.triggerOverdrive();
          window.__OG_DEBUG.aimAtBossCore();
          window.__OG_DEBUG.fireNow();
        """)
    elif f_idx in (6, 12, 18, 26, 34, 42):
        cdp.eval_js("window.__OG_DEBUG.aimAtBossCore(); window.__OG_DEBUG.fireNow();")
    if f_idx == 8:
        cdp.eval_js("window.__OG_DEBUG.spawnOrbitalNow(0, -14); window.__OG_DEBUG.spawnVortexNow(-2.4, -12);")
    if f_idx == 24:
        cdp.eval_js("window.__OG_DEBUG.spawnOrbitalNow(1.8, -14);")

    # SCENE 2 (2.10 - 4.00s): AUTHENTIC ARCADE TITLE SCREEN
    if f_idx == int(2.10 * fps):
        cdp.eval_js("window.__OG_DEBUG.openTitle();")

    # SCENE 3 (4.00 - 8.15s): #04 DUAL SAWED-OFF -> SHIFT -> #15 RICOCHET SAW
    if f_idx == int(4.00 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.startRun(false);
          window.__OG_DEBUG.state.midModGiven = true;
          window.__OG_DEBUG.state.bossKillTarget = 999;
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(3);
          window.__OG_DEBUG.state.shiftTimer = 2.05;
          window.__OG_DEBUG.state.nextWeaponIdx = 14;
        """)
    if int(4.05 * fps) <= f_idx < int(6.10 * fps):
        if f_idx % 5 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")
        if f_idx == int(5.05 * fps):
            cdp.eval_js("window.__OG_DEBUG.spawnBarrelBoom();")
    if f_idx == int(6.10 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(14);
        """)
    if int(6.15 * fps) <= f_idx < int(8.15 * fps):
        if f_idx % 6 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")

    # SCENE 4 (8.15 - 12.50s): #19 CYBER KATANA (Slice Missiles!) -> SHIFT -> #13 CRYO FREEZE RAY
    if f_idx == int(8.15 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.state.midModGiven = true;
          window.__OG_DEBUG.state.bossKillTarget = 999;
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnShowcaseMissile();
          window.__OG_DEBUG.spawnShowcaseMissile();
          window.__OG_DEBUG.setWeaponIdx(18);
          window.__OG_DEBUG.state.shiftTimer = 2.20;
          window.__OG_DEBUG.state.nextWeaponIdx = 12;
        """)
    if int(8.25 * fps) <= f_idx < int(10.35 * fps):
        if f_idx % 7 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")
        if f_idx == int(9.10 * fps):
            cdp.eval_js("window.__OG_DEBUG.spawnShowcaseMissile();")
    if f_idx == int(10.35 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(12);
        """)
    if int(10.42 * fps) <= f_idx < int(12.50 * fps):
        if f_idx % 4 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")

    # SCENE 5 (12.50 - 16.40s): #14 TESLA ARC -> #17 NOVA SINGULARITY -> #09 DUAL PLASMA VULCAN
    if f_idx == int(12.50 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(13);
        """)
    if int(12.55 * fps) <= f_idx < int(13.80 * fps):
        if f_idx % 4 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")
    if f_idx == int(13.80 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(16);
          window.__OG_DEBUG.spawnVortexNow(0, -12);
        """)
    if int(13.85 * fps) <= f_idx < int(15.05 * fps):
        if f_idx % 6 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")
    if f_idx == int(15.05 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(8);
        """)
    if int(15.10 * fps) <= f_idx < int(16.40 * fps):
        if f_idx % 2 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")

    # SCENE 6 (16.40 - 21.15s): BOSS CLIMAX — VALKYRIE-ZERO Charge Laser -> JUST DODGE -> #18 OMEGA ORBITAL!
    if f_idx == int(16.40 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.spawnBossSector(2);
          window.__OG_DEBUG.state.boss.hp = 28000;
          window.__OG_DEBUG.state.boss.maxHp = 28000;
          window.__OG_DEBUG.state.boss.pos.z = -15.5;
          window.__OG_DEBUG.state.boss.laserCharge = 0.45;
          window.__OG_DEBUG.setWeaponIdx(17);
          window.__OG_DEBUG.state.odGauge = 100;
        """)
    if f_idx == int(17.50 * fps):
        cdp.eval_js("window.__OG_DEBUG.state.boss.laserCharge = 0.80; window.__OG_DEBUG.triggerDodge();")
    if f_idx == int(18.10 * fps):
        cdp.eval_js("window.__OG_DEBUG.triggerOverdrive(); window.__OG_DEBUG.spawnOrbitalNow(0, -14);")
    if int(16.50 * fps) <= f_idx < int(21.15 * fps):
        if f_idx % 5 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtBossCore(); window.__OG_DEBUG.fireNow();")
        if f_idx == int(19.60 * fps):
            cdp.eval_js("window.__OG_DEBUG.spawnOrbitalNow(-1.6, -14);")

    # SCENE 7 (21.15 - 25.15s): LIVE #20 CHAOS OMNIGUN OVERDRIVE BEHIND SUBSCRIBE CTA!
    if f_idx == int(21.15 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.startRun(false);
          window.__OG_DEBUG.state.midModGiven = true;
          window.__OG_DEBUG.state.bossKillTarget = 999;
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(19);
          window.__OG_DEBUG.state.odGauge = 100;
          window.__OG_DEBUG.triggerOverdrive();
        """)
    if int(21.25 * fps) <= f_idx < int(25.15 * fps):
        if f_idx % 4 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")
        if f_idx % 24 == 0:
            cdp.eval_js("window.__OG_DEBUG.spawnWaveEnemy(); window.__OG_DEBUG.spawnOrbitalNow((Math.random()-0.5)*4, -12);")

    # SCENE 8 (25.15 - 28.50s): LIVE CYBER KATANA + ORBITAL FINALE BEHIND COMMENT CTA!
    if f_idx == int(25.15 * fps):
        cdp.eval_js("""
          window.__OG_DEBUG.state.midModGiven = true;
          window.__OG_DEBUG.state.bossKillTarget = 999;
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.spawnWaveEnemy();
          window.__OG_DEBUG.setWeaponIdx(18);
          window.__OG_DEBUG.spawnVortexNow(0, -12);
        """)
    if int(25.25 * fps) <= f_idx < int(28.50 * fps):
        if f_idx % 6 == 0:
            cdp.eval_js("window.__OG_DEBUG.aimAtEnemy(0); window.__OG_DEBUG.fireNow();")
        if f_idx == int(26.80 * fps):
            cdp.eval_js("window.__OG_DEBUG.spawnOrbitalNow(0, -12);")


def main():
    browser = find_browser()
    srv, port = start_static_server(ROOT)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
    profile_dir = tempfile.mkdtemp(prefix="cdp_day09_")
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

    frames_dir = OUT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.*"):
        old.unlink()

    fps = 24
    dt_sec = 1.0 / fps
    total_dur = 28.5
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
        # Fast crisp 540x960 WebGL capture -> Lanczos 1080x1920 + razor-sharp 1080x1920 overlays!
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540, "height": 960, "deviceScaleFactor": 1.0, "mobile": True
        })

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day09-overclock-gunner-3d/index.html?shorts=1"})
        for _ in range(60):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true; window.__gameEvents = []; window.__simTime = 0;")

        fonts = {
            "chip": ImageFont.truetype(FONT_SANS, 28),
            "chip_b": ImageFont.truetype(FONT_SANS, 28),
            "ribbon": ImageFont.truetype(FONT_SANS, 34),
            "hook": ImageFont.truetype(FONT_SANS, 82),
            "sub_yt": ImageFont.truetype(FONT_SANS, 58),
            "cta_head": ImageFont.truetype(FONT_SANS, 54),
            "cta_head_lg": ImageFont.truetype(FONT_SANS, 70),
            "yt_name": ImageFont.truetype(FONT_SANS, 34),
            "yt_meta": ImageFont.truetype(FONT_SANS, 25),
            "yt_btn": ImageFont.truetype(FONT_SANS, 32),
        }

        W_WHITE = (255, 255, 255)
        C_GOLD  = (250, 204, 21)
        C_CYAN  = (0, 229, 255)
        C_MINT  = (0, 230, 118)
        C_PURP  = (213, 0, 249)
        C_RED   = (255, 34, 85)

        caption_plan = [
            (0.00, 2.10, "20種武器FPS", C_GOLD, []),
            (2.10, 4.00, "20種ルーレット", C_CYAN, [
                [("全20種の", W_WHITE), ("3D武器", C_GOLD), ("がランダム切替!!", C_CYAN)],
                [("どう切り抜けるか", W_WHITE), ("ヤバすぎ!!", C_RED)],
            ]),
            (4.00, 8.15, "ランダム切替", C_GOLD, [
                [("9.5秒ごとに", W_WHITE), ("強制チェンジ!!", C_GOLD)],
                [("二丁散弾", C_RED), ("→", W_WHITE), ("3回跳弾ノコギリ!!", C_MINT)],
            ]),
            (8.15, 12.50, "サイバー刀＆冷凍", C_CYAN, [
                [("サイバー刀で", C_RED), ("ミサイル両断!!", C_GOLD)],
                [("冷凍ビーム", C_CYAN), ("で敵を70%減速!!", W_WHITE)],
            ]),
            (12.50, 16.40, "異次元アーセナル", C_PURP, [
                [("連鎖雷撃", C_PURP), ("×", W_WHITE), ("ブラックホール砲!!", C_CYAN)],
                [("両手プラズマバルカン", C_RED), ("まで全20種!!", C_GOLD)],
            ]),
            (16.40, 21.15, "巨大ボス決戦", C_RED, [
                [("極太レーザーを", C_RED), ("紙一重DODGE!!", C_CYAN)],
                [("衛星レーザー", C_GOLD), ("でボスを一掃だ!!", W_WHITE)],
            ]),
            (21.15, 25.15, "毎日開発中", C_RED, []),
            (25.15, 28.60, "リクエスト募集", C_CYAN, []),
        ]

        impact_peaks = [0.35, 5.05, 6.10, 8.15, 13.80, 18.10, 19.60, 22.60, 26.80]
        cut_times = [2.10, 4.00, 6.10, 8.15, 10.35, 12.50, 13.80, 15.05, 16.40, 21.15, 25.15]
        thumb_src_path = OUT_DIR / "_thumb_src.png"

        print(f"Capturing {total_frames} frames ({total_dur}s @ {fps}fps, native 1080x1920)...")
        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            choreograph_frame(cdp, f_idx, t, fps)
            cdp.eval_js(f"window.__stepFrame({dt_sec:.6f});")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 93})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            if f_idx == 10:
                raw_img.resize((1080, 1920), Image.Resampling.LANCZOS).save(thumb_src_path)

            sec_pill, accent, sub_lines, s0 = "20種武器FPS", C_GOLD, [], t
            for seg in caption_plan:
                if seg[0] <= t < seg[1]:
                    s0, _, sec_pill, accent, sub_lines = seg
                    break

            pulse = 0.0
            for pt in impact_peaks:
                if 0.0 <= (t - pt) < 0.24:
                    pulse = max(pulse, math.exp(-(t - pt) * 13.0))

            t_flash = 0.0
            for ct in cut_times:
                dt_c = abs(t - ct)
                if dt_c < 0.08:
                    t_flash = max(t_flash, (1.0 - dt_c / 0.08) ** 1.8)

            frame = draw_shorts_overlay(
                raw_img, t, total_dur, sec_pill, accent, sub_lines, s0, pulse, t_flash, fonts
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=92)

        events_json = cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]"
        events = json.loads(events_json)
        print(f"Captured {total_frames} frames, {len(events)} gameplay events.")
        cdp.close()

        wav_path = OUT_DIR / "audio.wav"
        print("Synthesizing human-like voiceover + 138 BPM Cyberpunk stereo BGM + SFX...")
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day09_short.mp4"
        print("Encoding final MP4 (1080x1920 H.264 + 192k AAC)...")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%04d.jpg"),
                "-i", str(wav_path),
                "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                "-pix_fmt", "yuv420p", "-r", str(fps),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-shortest", "-movflags", "+faststart",
                str(out_mp4),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        if thumb_src_path.exists():
            render_note_thumbnail(browser, thumb_src_path, OUT_DIR / "note_thumbnail.png", day_num=9)
            thumb_src_path.unlink(missing_ok=True)

        write_youtube_metadata(OUT_DIR / "youtube_metadata.txt")
        shutil.rmtree(frames_dir, ignore_errors=True)
        wav_path.unlink(missing_ok=True)
        print(f"DONE! Generated {out_mp4} ({out_mp4.stat().st_size:,} bytes)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
