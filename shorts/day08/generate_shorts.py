#!/usr/bin/env python3
"""
Day 08 YouTube Shorts (1080x1920, 24fps, 28.5s) — ACE SPIKE 3D
Pro YouTube Shorts Production Pipeline:
- 0.00-1.60s: High-impact Cold-Open Meteor Spike + chromatic split + speedlines + bold hook title
- 2.25-3.85s: Pro sports-broadcast Home Screen
- 3.85-8.45s: Beginner-friendly TUTORIAL showcase + live Spike Drill play
- 8.45-12.80s: Slow-Mo Over/Under Receive -> Cross Spike
- 12.80-16.20s: Net-front MONSTER BLOCK!! + Quick Toss combo
- 16.20-21.15s: Story 5-tier select (EASY ~ 鬼) -> Final Boss 鬼 Meteor Finish
- 21.15-25.15s: Animated YouTube Subscribe Button CTA (clicks into 登録済み!) over live Jump Serve
- 25.15-28.50s: Animated YouTube Comment Request CTA over double Meteor Finale
- Human-like natural Japanese narration (ja-JP-NanamiNeural, natural pacing + studio mic mastering)
- Stereo 132 BPM upbeat sports-pop BGM + auto-ducking + impact/whoosh/bell/pop SFX
- Outputs:
    shorts/day08/output/day08_short.mp4
    shorts/day08/output/note_thumbnail.png
    shorts/day08/output/youtube_metadata.txt
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
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "shorts" / "day08" / "output"
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


# Natural, human-like YouTube narration cues (per-phrase rate & pitch tuned to avoid robotic fast-talk)
NARRATION_CUES = [
    (0.05,  "えっ、ブラウザで動く3Dバレー、スパイク気持ちよすぎ！", "+18%", "+3Hz"),
    (3.90,  "しかも安心のチュートリアル付き！初心者でもすぐ打てるよ。", "+15%", "+1Hz"),
    (8.50,  "強打はスロー中にオーバーとアンダーで拾って、そのままクロスへ強打！", "+16%", "+2Hz"),
    (12.90, "ネット際で跳べば、ドシャットブロックも決まるんだよね！", "+15%", "+2Hz"),
    (16.25, "ストーリーはイージーから鬼まで全5段階！ラスボスの鬼、勝てる？", "+16%", "+2Hz"),
    (21.20, "100日後にバズるゲームを見たい人は、チャンネル登録よろしく！", "+14%", "+1Hz"),
    (25.20, "作ってほしいゲームがあったら、コメント欄で教えてね！", "+14%", "+2Hz"),
]


def synthesize_tts_line(text: str, out_wav: Path, rate: str = "+15%", pitch: str = "+2Hz", sr: int = 44100) -> bool:
    """Synthesize natural human-like Japanese YouTube voiceover with studio condenser mic mastering."""
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
            # Studio condenser mic mastering chain:
            # trim silence -> warm chest resonance (+2.4dB @180Hz) -> vocal clarity (+1.8dB @3.2kHz)
            # -> tame digital sibilance (-1.5dB @6.8kHz) -> gentle broadcast comp -> subtle room air
            af = (
                "silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,"
                "areverse,silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,areverse,"
                "highpass=f=85,"
                "equalizer=f=180:t=q:w=1.2:g=2.4,"
                "equalizer=f=3200:t=q:w=1.4:g=1.8,"
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
    """Mix mono signal into stereo buffers with constant-power pan (-1..+1)."""
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

    # 132 BPM Upbeat Japanese Sports-Pop / YouTube Creator Stereo Beat (Fmaj7 - G6 - Em7 - Am7)
    bpm = 132.0
    step_dur = 60.0 / bpm / 4.0  # 16th note
    bar_dur = step_dur * 16.0

    chords = [
        # (bass_hz, [chord_tones_hz])
        (87.31,  [174.61, 220.00, 261.63, 329.63]),  # Fmaj7
        (98.00,  [196.00, 246.94, 293.66, 329.63]),  # G6
        (82.41,  [164.81, 196.00, 246.94, 293.66]),  # Em7
        (110.00, [220.00, 261.63, 329.63, 392.00]),  # Am7
    ]
    arp_idx = [0, 2, 3, 1, 2, 3, 1, 0, 3, 2, 1, 3, 2, 0, 1, 2]

    # Warm stereo chord pads per bar (with gentle sidechain pump on quarter beats)
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
            # Slight stereo detune for lush wide YouTube synth sound
            pad_l += np.sin(2.0 * math.pi * (f * 1.002) * bt + ti * 0.4) * 0.25
            pad_r += np.sin(2.0 * math.pi * (f * 0.998) * bt + ti * 0.9) * 0.25
            pad_l += np.sin(2.0 * math.pi * (f * 2.001) * bt) * 0.06
            pad_r += np.sin(2.0 * math.pi * (f * 1.999) * bt) * 0.06
        # Quarter-note sidechain pump
        beat_phase = (bt % (step_dur * 4.0)) / (step_dur * 4.0)
        pump = 0.45 + 0.55 * np.minimum(1.0, beat_phase * 3.2)
        env = np.minimum(1.0, bt / 0.04) * np.minimum(1.0, (bar_dur - bt).clip(0) / 0.06)
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

        # Four-on-the-floor punchy pop kick (steps 0, 4, 8, 12 + syncopation on 14)
        if step16 in (0, 4, 8, 12) or (bar % 2 == 1 and step16 == 14):
            k_len = min(int(0.18 * sr), n_samples - s0)
            lt = np.arange(k_len, dtype=np.float32) / sr
            kf = 48.0 + 115.0 * np.exp(-lt * 34.0)
            kick = np.tanh(np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * 2.2) * np.exp(-lt * 12.0)
            add_stereo(bgm_l, bgm_r, s0, kick, pan=0.0, gain=0.22)

        # Crisp clap/snare on 4 & 12
        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 409)
            sn_len = min(int(0.11 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            noise = rng.uniform(-1.0, 1.0, sn_len).astype(np.float32)
            # Simple bright high-pass via 1st difference
            bright = np.diff(noise, prepend=0.0)
            body = np.sin(2.0 * math.pi * 210.0 * slt) * np.exp(-slt * 26.0) * 0.4
            snare = (bright * np.exp(-slt * 28.0) * 0.65 + body)
            add_stereo(bgm_l, bgm_r, s0, snare, pan=0.08 if step16 == 4 else -0.08, gain=0.14)

        # Crisp 16th hi-hat groove
        if step16 % 2 == 0 or step16 in (3, 7, 11, 15):
            rng = np.random.default_rng(seed=i + 901)
            hh_len = min(int(0.038 * sr), n_samples - s0)
            hlt = np.arange(hh_len, dtype=np.float32) / sr
            h_noise = np.diff(rng.uniform(-1.0, 1.0, hh_len).astype(np.float32), prepend=0.0)
            hat = h_noise * np.exp(-hlt * (55.0 if step16 % 4 == 2 else 95.0))
            add_stereo(bgm_l, bgm_r, s0, hat, pan=-0.25 if step16 % 4 == 0 else 0.25, gain=0.055)

        # Bouncy octave bassline
        if step16 in (0, 3, 6, 8, 10, 14):
            blen = min(int(step_dur * 1.4 * sr), n_samples - s0)
            blt = np.arange(blen, dtype=np.float32) / sr
            bf = bass_f * (2.0 if step16 in (3, 10, 14) else 1.0)
            bs = (np.sin(2.0 * math.pi * bf * blt) * 0.72 + np.sin(2.0 * math.pi * bf * 2.0 * blt) * 0.28)
            bs = np.tanh(bs * 1.4) * np.exp(-blt * 7.5)
            add_stereo(bgm_l, bgm_r, s0, bs, pan=0.0, gain=0.16)

        # Bright YouTube pluck arpeggio
        if step16 in (0, 2, 4, 6, 8, 10, 12, 14):
            plen = min(int(0.14 * sr), n_samples - s0)
            plt = np.arange(plen, dtype=np.float32) / sr
            pf = tones[arp_idx[step16]] * 2.0
            pluck = (np.sin(2.0 * math.pi * pf * plt) * 0.65 + np.sin(2.0 * math.pi * pf * 2.0 * plt) * 0.22) * np.exp(-plt * 18.0)
            add_stereo(bgm_l, bgm_r, s0, pluck, pan=-0.35 if (step16 // 2) % 2 == 0 else 0.35, gain=0.075)

    # Helper SFX generators
    def add_whoosh(t_sec: float, gain: float = 0.28):
        idx = int(t_sec * sr)
        wlen = int(0.19 * sr)
        wt = np.arange(wlen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 17)
        wn = rng.uniform(-1.0, 1.0, wlen).astype(np.float32)
        env = np.sin(math.pi * wt / 0.19) ** 1.6
        sweep = np.sin(2.0 * math.pi * np.cumsum(260.0 + 1400.0 * (wt / 0.19)) / sr) * 0.35
        sig = (wn * 0.45 + sweep) * env
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    def add_pop(t_sec: float, freq: float = 740.0, gain: float = 0.24):
        idx = int(t_sec * sr)
        plen = int(0.11 * sr)
        pt = np.arange(plen, dtype=np.float32) / sr
        pf = freq * (1.0 + 0.55 * np.exp(-pt * 35.0))
        sig = np.sin(2.0 * math.pi * np.cumsum(pf) / sr) * np.exp(-pt * 24.0)
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    def add_bell_ding(t_sec: float, gain: float = 0.32):
        idx = int(t_sec * sr)
        blen = int(0.42 * sr)
        bt = np.arange(blen, dtype=np.float32) / sr
        # Crisp YouTube subscribe notification "Pi-kon!" double chime
        c1 = (np.sin(2.0 * math.pi * 1046.5 * bt) * 0.7 + np.sin(2.0 * math.pi * 2093.0 * bt) * 0.3) * np.exp(-bt * 12.0)
        d2 = int(0.085 * sr)
        c2 = np.zeros_like(c1)
        if d2 < blen:
            bt2 = np.arange(blen - d2, dtype=np.float32) / sr
            c2[d2:] = (np.sin(2.0 * math.pi * 1567.98 * bt2) * 0.75 + np.sin(2.0 * math.pi * 3135.96 * bt2) * 0.25) * np.exp(-bt2 * 9.0)
        add_stereo(sfx_l, sfx_r, idx, c1 + c2, pan=0.0, gain=gain)

    def add_impact_drop(t_sec: float, power: float = 1.0):
        idx = int(t_sec * sr)
        elen = int(0.36 * sr)
        lt = np.arange(elen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 51)
        snap = rng.uniform(-1.0, 1.0, elen).astype(np.float32) * np.exp(-lt * 26.0) * 0.36
        boom = np.tanh(np.sin(2.0 * math.pi * np.cumsum(220.0 * np.exp(-lt * 16.0) + 44.0) / sr) * 2.6) * np.exp(-lt * 8.5) * 0.50
        add_stereo(sfx_l, sfx_r, idx, snap + boom, pan=0.0, gain=0.85 * power)

    # Editorial YouTube transition SFX & key UI clicks
    for wt in (2.22, 3.82, 5.62, 8.42, 12.77, 16.17, 17.97, 21.12, 25.12):
        add_whoosh(wt, gain=0.22)
    add_impact_drop(0.44, power=1.15)     # Cold-open 1st-second Meteor Spike hook!
    add_pop(3.90, freq=680.0, gain=0.22)  # Tutorial screen reveal pop!
    add_pop(16.25, freq=580.0, gain=0.22) # Story 5-tier reveal pop!
    add_impact_drop(18.58, power=1.05)    # Final Boss 鬼 Meteor Finish!
    add_bell_ding(22.60, gain=0.34)       # Subscribe button clicked -> 登録済み🔔!
    add_pop(25.25, freq=820.0, gain=0.24) # Comment card pop!

    # Frame-accurate Volleyball Gameplay SFX from recorded game events
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        idx0 = int(t0 * sr)
        if idx0 >= n_samples:
            continue
        kind = ev.get("type")
        if kind in ("spike", "spike_just", "meteor_spike"):
            add_impact_drop(t0, power=1.0 if kind != "spike" else 0.72)
        elif kind in ("recv", "recv_just", "toss", "toss_just"):
            e_len = min(int(0.17 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            thump = np.sin(2.0 * math.pi * np.cumsum(380.0 * np.exp(-lt * 20.0) + 125.0) / sr) * np.exp(-lt * 16.0)
            add_stereo(sfx_l, sfx_r, idx0, thump, pan=0.0, gain=0.32)
        elif kind == "monster_block":
            e_len = min(int(0.42 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 88)
            slam = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 16.0) * 0.36
            sub = np.tanh(np.sin(2.0 * math.pi * np.cumsum(165.0 * np.exp(-lt * 12.0) + 38.0) / sr) * 2.8) * np.exp(-lt * 8.0) * 0.48
            add_stereo(sfx_l, sfx_r, idx0, slam + sub, pan=0.0, gain=0.95)

    # Human-like Japanese Voiceover + Smooth Auto-Ducking
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day08_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.11 * sr)
        for idx, (cue_t, line_txt, rate, pitch) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, rate=rate, pitch=pitch, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.90
                s0 = max(int(cue_t * sr), prev_end_s + int(0.08 * sr))
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    prev_end_s = s0 + s_len
                    d0 = max(0, s0 - ramp_n)
                    d1 = min(n_samples, s0 + s_len + ramp_n)
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.26)
                    if s0 > d0:
                        duck[d0:s0] = np.minimum(duck[d0:s0], np.linspace(1.0, 0.26, s0 - d0, dtype=np.float32))
                    if d1 > s0 + s_len:
                        duck[s0 + s_len : d1] = np.minimum(duck[s0 + s_len : d1], np.linspace(0.26, 1.0, d1 - (s0 + s_len), dtype=np.float32))
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    # Final Stereo Master Mix
    mix_l = bgm_l * duck + sfx_l * 0.85 + voice * 0.96
    mix_r = bgm_r * duck + sfx_r * 0.85 + voice * 0.96
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
    """Draw authentic YouTube creator dual-outline multi-colored caption line (no clunky box!)."""
    widths = []
    for txt, _ in tokens:
        bb = draw.textbbox((0, 0), txt, font=font, stroke_width=outer_stroke)
        # Use advance width via textlength for clean kerning
        adv = draw.textlength(txt, font=font)
        widths.append(adv)
    total_w = sum(widths)
    cur_x = center_x - total_w / 2.0

    # Pass 1: Deep drop shadow + outer black border
    cx = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((cx + 5, y + 7), txt, font=font, fill=(0, 0, 0, 210), stroke_width=outer_stroke + 2, stroke_fill=(0, 0, 0, 200))
        cx += w

    # Pass 2: Dark navy inner rim
    cx = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((cx, y), txt, font=font, fill=(10, 16, 30, 255), stroke_width=outer_stroke, stroke_fill=(8, 12, 24, 255))
        cx += w

    # Pass 3: Crisp vibrant fill + tight inner stroke
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
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.BILINEAR)

    if impact_pulse > 0.14:
        frame_img = apply_chromatic_split(frame_img, int(13 * impact_pulse))

    img = frame_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size

    # Subtle bottom gradient vignette so YouTube subtitles always pop cleanly
    for gy in range(0, 420, 14):
        alpha = int(135 * (gy / 420.0) ** 1.4)
        draw.rectangle((0, H - 420 + gy, W, H - 420 + gy + 14), fill=(4, 8, 18, alpha))

    # Impact Anime Speedlines
    if impact_pulse > 0.22:
        cx, cy = W // 2, int(H * 0.44)
        for i in range(28):
            ang = (i / 28.0) * math.tau + t * 5.2
            r1 = 320 + (i % 3) * 50
            r2 = 1120
            x1 = cx + int(math.cos(ang) * r1)
            y1 = cy + int(math.sin(ang) * r1)
            x2 = cx + int(math.cos(ang) * r2)
            y2 = cy + int(math.sin(ang) * r2)
            draw.line((x1, y1, x2, y2), fill=(*accent_rgb, int(175 * impact_pulse)), width=8 if i % 2 == 0 else 3)

    # =======================================================
    # 1. PRO YOUTUBE CHANNEL HEADER BAR (Top Safe Zone Y=68)
    # =======================================================
    # Left glass pill: "100日後にバズるゲーム" + vivid red/orange "DAY 08" badge
    pill_y0, pill_y1 = 68, 128
    draw_rounded_box(draw, (38, pill_y0, 566, pill_y1), 30, fill=(8, 14, 28, 210), outline=(255, 255, 255, 45), width=2)
    draw_rounded_box(draw, (46, pill_y0 + 7, 174, pill_y1 - 7), 22, fill=(235, 32, 54, 255))
    draw.text((62, pill_y0 + 14), "DAY 08", font=fonts["chip_b"], fill=(255, 255, 255, 255))
    draw.text((190, pill_y0 + 14), "100日後にバズるゲーム", font=fonts["chip"], fill=(242, 246, 255, 255))

    # Right contextual topic pill
    if section_pill:
        sw = int(draw.textlength(section_pill, font=fonts["chip_b"])) + 44
        sx0 = W - 38 - sw
        draw_rounded_box(draw, (sx0, pill_y0, W - 38, pill_y1), 30, fill=(8, 14, 28, 210), outline=(*accent_rgb, 215), width=3)
        draw.text((sx0 + 22, pill_y0 + 14), section_pill, font=fonts["chip_b"], fill=(*accent_rgb, 255))

    # =======================================================
    # 2. FIRST-SECOND COLD-OPEN IMPACT HOOK (0.00s - 1.95s)
    # =======================================================
    if t < 1.95:
        fade = 1.0 if t < 1.65 else max(0.0, (1.95 - t) / 0.30)
        bounce = int(38 * math.exp(-t * 14.0))
        kick_y = int(16 * impact_pulse)
        # Vivid Red Top Ribbon
        rib_y = 265 - bounce - kick_y
        draw_rounded_box(draw, (175, rib_y, W - 175, rib_y + 62), 14, fill=(228, 28, 52, int(245 * fade)), outline=(255, 215, 0, int(255 * fade)), width=4)
        rib_txt = "ブラウザで動くガチ3Dバレー!!"
        rw = draw.textlength(rib_txt, font=fonts["ribbon"])
        draw.text(((W - rw) / 2, rib_y + 11), rib_txt, font=fonts["ribbon"], fill=(255, 255, 255, int(255 * fade)))

        # Huge YouTube Variety Impact Headline
        if fade > 0.2:
            draw_rich_subtitle_line(
                draw, W // 2, rib_y + 78,
                [("スパイク", (250, 204, 21)), ("気持ちよすぎ!!", (255, 255, 255))],
                fonts["hook"], outer_stroke=16, inner_stroke=6,
            )

    # =======================================================
    # 3. TUTORIAL HIGHLIGHT BADGE (3.85s - 8.40s)
    # =======================================================
    if 3.85 <= t < 8.40:
        age = t - 3.85
        pop = int(28 * math.exp(-age * 16.0))
        by = 158 - pop
        btxt = "初心者でも安心！チュートリアル完備"
        bw = int(draw.textlength(btxt, font=fonts["ribbon"])) + 66
        bx0 = (W - bw) // 2
        draw_rounded_box(draw, (bx0 + 6, by + 6, bx0 + bw + 6, by + 66), 30, fill=(0, 0, 0, 150))
        draw_rounded_box(draw, (bx0, by, bx0 + bw, by + 60), 30, fill=(14, 165, 233, 245), outline=(255, 255, 255, 245), width=4)
        draw.text((bx0 + 33, by + 10), btxt, font=fonts["ribbon"], fill=(255, 255, 255, 255))

    # =======================================================
    # 4. STORY 5-DIFFICULTY BADGE (16.20s - 20.90s)
    # =======================================================
    if 16.20 <= t < 20.90:
        age = t - 16.20
        pop = int(28 * math.exp(-age * 16.0))
        by = 158 - pop
        btxt = "EASY 〜 最難関【鬼】 全5段階ストーリー"
        bw = int(draw.textlength(btxt, font=fonts["ribbon"])) + 62
        bx0 = (W - bw) // 2
        draw_rounded_box(draw, (bx0 + 6, by + 6, bx0 + bw + 6, by + 66), 30, fill=(0, 0, 0, 155))
        draw_rounded_box(draw, (bx0, by, bx0 + bw, by + 60), 30, fill=(190, 18, 60, 245), outline=(250, 204, 21, 255), width=4)
        draw.text((bx0 + 31, by + 10), btxt, font=fonts["ribbon"], fill=(255, 255, 255, 255))

    # =======================================================
    # 5. AUTHENTIC YOUTUBE CREATOR SUBTITLES (Safe Zone)
    # =======================================================
    # During 0.00-2.25s cold-open, the top impact hook headline owns the screen (no duplicate bottom text!)
    if sub_lines and 2.25 <= t < 21.15:
        age = max(0.0, t - seg_start)
        pop_y = int(22 * math.exp(-age * 18.0))
        if 2.25 <= t < 3.85:
            # Home screen showcase: sit cleanly in the open court gap above STORY/TUTORIAL dock!
            base_y = 1155
        elif 16.20 <= t < 18.00:
            # Story 5-tier select screen: sit cleanly near bottom safe zone below cards
            base_y = 1540
        else:
            base_y = 1445 if len(sub_lines) == 2 else 1495
        for li, line_tokens in enumerate(sub_lines):
            draw_rich_subtitle_line(
                draw, W // 2, base_y + li * 82 + pop_y,
                line_tokens, fonts["sub_yt"], outer_stroke=13, inner_stroke=5,
            )

    # =======================================================
    # 6. AUTHENTIC YOUTUBE SUBSCRIBE CTA (21.15s - 25.15s)
    #    Red "チャンネル登録" button clicked by cursor -> "登録済み 🔔"!
    # =======================================================
    if 21.15 <= t < 25.15:
        age = t - 21.15
        pop_y = int(42 * math.exp(-age * 14.0))
        clicked = t >= 22.60
        click_age = max(0.0, t - 22.60)
        cx = W // 2

        # Punchy YouTube caption above card
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

        # Authentic YouTube Channel Bar Card (Y=1285..1445, width=860, centered safe area)
        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1285 + pop_y, 1445 + pop_y
        draw_rounded_box(draw, (x0 + 8, y0 + 12, x1 + 8, y1 + 12), 34, fill=(0, 0, 0, 175))
        draw_rounded_box(draw, (x0, y0, x1, y1), 34, fill=(18, 22, 34, 246), outline=(255, 255, 255, 55), width=3)

        # Channel Avatar Circle
        av_cx, av_cy = x0 + 82, (y0 + y1) // 2
        draw.ellipse((av_cx - 48, av_cy - 48, av_cx + 48, av_cy + 48), fill=(245, 184, 0, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((av_cx - 32, av_cy - 18), "ACE", font=fonts["chip_b"], fill=(12, 16, 28, 255))

        # Channel Name & Sub-label
        draw.text((x0 + 148, y0 + 36), "100日後にバズるゲーム", font=fonts["yt_name"], fill=(255, 255, 255, 255))
        draw.text((x0 + 148, y0 + 88), "毎日1本ゲーム開発中！", font=fonts["yt_meta"], fill=(160, 174, 198, 255))

        # Subscribe Button (right side of card)
        btn_scale = 1.0 - 0.08 * math.exp(-click_age * 18.0) if clicked else (1.0 + 0.03 * math.sin(t * 10.0))
        bw = int(265 * btn_scale)
        bh = int(84 * btn_scale)
        bcx, bcy = x1 - 155, (y0 + y1) // 2
        bx0, by0, bx1, by1 = bcx - bw // 2, bcy - bh // 2, bcx + bw // 2, bcy + bh // 2

        if clicked:
            # Click ripple ring
            if click_age < 0.45:
                rr = int(45 + click_age * 240)
                ra = int(230 * (1.0 - click_age / 0.45))
                draw.ellipse((bcx - rr, bcy - rr, bcx + rr, bcy + rr), outline=(255, 212, 0, ra), width=7)
            draw_rounded_box(draw, (bx0, by0, bx1, by1), 42, fill=(52, 58, 72, 255), outline=(255, 255, 255, 110), width=3)
            btxt = "登録済み"
            tw = draw.textlength(btxt, font=fonts["yt_btn"])
            draw.text((bcx - tw / 2 - 14, bcy - 20), btxt, font=fonts["yt_btn"], fill=(235, 240, 248, 255))
            # Draw clean crisp notification bell icon on right of "登録済み"
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

        # Animated white pointer approaching and clicking the Subscribe button
        if 21.60 <= t < 23.40:
            prog_c = min(1.0, max(0.0, (t - 21.60) / 0.95))
            ease = 1.0 - (1.0 - prog_c) ** 3
            px = int(bcx + 120 * (1.0 - ease))
            py = int(bcy + 145 * (1.0 - ease) + (8 if clicked and click_age < 0.14 else 0))
            poly = [(px, py), (px, py + 46), (px + 13, py + 34), (px + 25, py + 50), (px + 33, py + 45), (px + 21, py + 29), (px + 36, py + 29)]
            draw.polygon(poly, fill=(255, 255, 255, 255), outline=(12, 16, 28, 255))

    # =======================================================
    # 7. AUTHENTIC YOUTUBE COMMENT REQUEST CTA (25.15s - 28.50s)
    # =======================================================
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

        # YouTube Comment Input Box Card
        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1288 + pop_y, 1468 + pop_y
        draw_rounded_box(draw, (x0 + 8, y0 + 12, x1 + 8, y1 + 12), 30, fill=(0, 0, 0, 180))
        draw_rounded_box(draw, (x0, y0, x1, y1), 30, fill=(16, 22, 36, 248), outline=(56, 189, 248, 245), width=4)

        draw.text((x0 + 38, y0 + 22), "コメント欄 // REQUEST BOX", font=fonts["yt_meta"], fill=(56, 189, 248, 255))
        # Inner typing field
        draw_rounded_box(draw, (x0 + 34, y0 + 68, x1 - 34, y1 - 24), 18, fill=(28, 36, 56, 255), outline=(255, 255, 255, 40), width=2)
        sample = "「次はサッカーゲーム作ってほしい！」"
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


def render_note_thumbnail(browser: str, game_png_path: Path, out_png: Path):
    b64 = base64.b64encode(game_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: radial-gradient(circle at 75% 45%, #0369a1 0%, #0f172a 48%, #040814 100%);
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  color:#ffffff;display:flex;align-items:center;justify-content:space-between;
  padding:46px 56px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2.5px solid rgba(56,189,248,0.45);border-radius:22px;pointer-events:none;
}}
.left{{width:725px;z-index:2;}}
.badge{{
  display:inline-block;padding:8px 22px;border-radius:999px;
  background:linear-gradient(90deg,#38bdf8,#f97316);color:#ffffff;
  font-weight:900;font-size:22px;letter-spacing:0.05em;margin-bottom:18px;
  box-shadow:0 8px 24px rgba(249,115,22,0.45);
}}
h1{{
  font-size:74px;line-height:1.02;font-weight:900;color:#ffffff;margin-bottom:16px;
  text-shadow:0 8px 24px rgba(0,0,0,0.75);
}}
h1 span{{color:#facc15;}}
.sub{{font-size:30px;font-weight:900;color:#e2e8f0;line-height:1.4;margin-bottom:26px;}}
.sub strong{{color:#38bdf8;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(15,23,42,0.88);
  border:2px solid rgba(250,204,21,0.68);font-size:19px;font-weight:800;color:#ffffff;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #facc15;
  box-shadow:0 24px 60px rgba(0,0,0,0.75), 0 0 46px rgba(56,189,248,0.55);
  transform:rotate(2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:28px;left:-46px;transform:rotate(-8deg);
  padding:10px 24px;border-radius:14px;background:linear-gradient(90deg,#facc15,#f97316);
  border:3.5px solid #ffffff;color:#080a12;font-weight:900;font-size:27px;
  box-shadow:0 12px 28px rgba(0,0,0,0.6);
}}
</style></head><body>
  <div class="left">
    <div class="badge">GAME DAY 08 ｜ Three.js 一人称3Dバレーボール</div>
    <h1>ACE <span>SPIKE 3D</span></h1>
    <div class="sub"><strong>チュートリアル完備×全5段階ストーリー!!</strong><br>スローレシーブ＆ドシャットブロック＆必殺スパイク</div>
    <div class="chips">
      <div class="chip">チュートリアル特訓付き</div>
      <div class="chip">EASY〜鬼 全5章ストーリー</div>
      <div class="chip">必殺メテオスパイク!!</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">流星スパイク!!</div>
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
    txt = """【タイトル案】
ブラウザで動くガチの3Dバレー作ったらスパイク気持ちよすぎた!!【100日後にバズるゲーム Day 8】#shorts

【概要欄】
100日後にバズるゲーム、8日目は一人称3Dバレーボール「ACE SPIKE 3D」!!
初心者でもすぐ打てるチュートリアル完備＆イージーから最難関「鬼」まで全5段階ストーリー搭載！

▶ 今すぐ無料プレイ（ブラウザですぐ遊べます）
https://kam2525-hub.github.io/note_create_use/games/day08-ace-spike-3d/

🔥 100日後にバズるゲームを見たい人はチャンネル登録よろしく！
💬 作ってほしいゲームがあったらコメント欄で教えてね！

#100日後にバズるゲーム #インディーゲーム #ゲーム開発 #バレーボール #3Dゲーム #ブラウザゲーム #shorts

【固定コメント案】
今すぐ無料で遊べます👇
https://kam2525-hub.github.io/note_create_use/games/day08-ace-spike-3d/

100日後にバズるゲームを見たい人はチャンネル登録よろしく！
「こんなゲーム作ってほしい！」があればぜひコメント欄へお願いします🔥
"""
    out_path.write_text(txt, encoding="utf-8")


def main():
    browser = find_browser()
    srv, port = start_static_server(ROOT)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
    profile_dir = tempfile.mkdtemp(prefix="cdp_day08_")
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
        cdp.call("Emulation.setDeviceMetricsOverride", {
            "width": 540, "height": 960, "deviceScaleFactor": 1.0, "mobile": True
        })

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day08-ace-spike-3d/index.html?shorts=1"})
        for _ in range(60):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true;")

        fonts = {
            "chip": ImageFont.truetype(FONT_SANS, 28),
            "chip_b": ImageFont.truetype(FONT_SANS, 28),
            "ribbon": ImageFont.truetype(FONT_SANS, 34),
            "hook": ImageFont.truetype(FONT_SANS, 78),
            "sub_yt": ImageFont.truetype(FONT_SANS, 60),
            "cta_head": ImageFont.truetype(FONT_SANS, 54),
            "cta_head_lg": ImageFont.truetype(FONT_SANS, 70),
            "yt_name": ImageFont.truetype(FONT_SANS, 34),
            "yt_meta": ImageFont.truetype(FONT_SANS, 25),
            "yt_btn": ImageFont.truetype(FONT_SANS, 32),
        }

        W_WHITE = (255, 255, 255)
        C_GOLD  = (250, 204, 21)
        C_CYAN  = (56, 189, 248)
        C_MINT  = (52, 211, 153)
        C_RED   = (251, 72, 98)

        # Segment plan: (start, end, section_pill, accent_rgb, subtitle_lines)
        caption_plan = [
            (0.00, 3.85, "3Dバレー", C_GOLD, [
                [("ブラウザで動く", W_WHITE), ("ガチ3Dバレー!!", C_GOLD)],
                [("スパイクが", W_WHITE), ("気持ちよすぎ!!", C_RED)],
            ]),
            (3.85, 8.45, "チュートリアル", C_CYAN, [
                [("安心の", W_WHITE), ("チュートリアル", C_CYAN), ("付き!!", W_WHITE)],
                [("初心者でも", W_WHITE), ("すぐ打てるよ！", C_GOLD)],
            ]),
            (8.45, 12.80, "スローレシーブ", C_MINT, [
                [("スロー中に", W_WHITE), ("オーバー", C_MINT), ("＆", W_WHITE), ("アンダー", C_CYAN)],
                [("拾ってそのまま", W_WHITE), ("クロス強打!!", C_GOLD)],
            ]),
            (12.80, 16.20, "ドシャット", C_CYAN, [
                [("ネット際でタイミング合わせれば", W_WHITE)],
                [("ドシャットブロック", C_CYAN), ("炸裂!!", C_GOLD)],
            ]),
            (16.20, 21.15, "全5段階ストーリー", C_RED, [
                [("EASY〜最難関", W_WHITE), ("【鬼】", C_RED), ("全5段階!!", C_GOLD)],
                [("ラスボスの鬼、", W_WHITE), ("勝てる人いる？", C_GOLD)],
            ]),
            (21.15, 25.15, "毎日開発中", C_RED, []),
            (25.15, 28.60, "リクエスト募集", C_CYAN, []),
        ]

        impact_peaks = [0.44, 6.24, 9.30, 11.32, 13.50, 18.58, 22.32, 25.68, 27.38]
        cut_times = [2.25, 3.85, 5.65, 8.45, 12.80, 16.20, 18.00, 21.15, 25.15]
        thumb_src_path = OUT_DIR / "_thumb_src.png"

        print(f"Capturing {total_frames} frames ({total_dur}s @ {fps}fps)...")
        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            cdp.eval_js(f"window.__stepFrame({dt_sec:.6f});")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 94})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            if f_idx == 12:
                raw_img.resize((1080, 1920), Image.Resampling.LANCZOS).save(thumb_src_path)

            sec_pill, accent, sub_lines, s0 = "3Dバレー", C_GOLD, [], t
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
                if dt_c < 0.09:
                    t_flash = max(t_flash, (1.0 - dt_c / 0.09) ** 1.8)

            frame = draw_shorts_overlay(
                raw_img, t, total_dur, sec_pill, accent, sub_lines, s0, pulse, t_flash, fonts
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=93)

        events_json = cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]"
        events = json.loads(events_json)
        print(f"Captured {total_frames} frames, {len(events)} gameplay events.")
        cdp.close()

        wav_path = OUT_DIR / "audio.wav"
        print("Synthesizing human-like voiceover + stereo BGM + SFX...")
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day08_short.mp4"
        print("Encoding final MP4...")
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
            render_note_thumbnail(browser, thumb_src_path, OUT_DIR / "note_thumbnail.png")
            thumb_src_path.unlink(missing_ok=True)

        write_youtube_metadata(OUT_DIR / "youtube_metadata.txt")
        # Clean temporary frame JPEGs and intermediate wav to keep repo tidy
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
