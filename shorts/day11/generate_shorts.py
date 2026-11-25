#!/usr/bin/env python3
"""
Day 11 YouTube Shorts (1080x1920, 24fps, 25.5s) — SKY SMASH 3D (First-Person 3D Badminton)
NEW PRO-BROADCAST SPORTS TELEMETRY & RALLY RHYTHM PIPELINE (Fresh format distinct from Day 01-10!):
- 0.00-1.55s: SUB-SECOND RALLY -> JUMP SMASH CLIMAX! (Hairpin 0.12s -> Rival Lift 0.36s -> Jump Smash 0.78s!! < 1.0s)
- 1.55-5.80s: Slow-Mo Hairpin vs Far-Side SLIDING DIVE SAVE -> Follow-up Smash!
- 5.80-10.60s: Pro Tour Lobby & 4-Step Academy showcase -> WORLD CHAMPION【鬼】10.8m/s Counter Drive Finish!
- 10.60-18.00s: Honest Dev Note on Online Mode ("オンライン対戦はまだ未完成！この動画が伸びたら本気で作るかも!?")
- 18.00-21.80s: Mandatory Subscribe CTA (interactive cursor click -> 登録済み🔔) over Jump Smash rally
- 21.80-25.50s: Mandatory Comment Request CTA (typing comment box) over double Meteor Smash finale
- Voiceover: Energetic sports-caster ja-JP-KeitaNeural + studio compression + 138 BPM Electro-Sports Anthem + ducking
- Outputs:
    shorts/day11/output/day11_short.mp4
    shorts/day11/output/note_thumbnail.png
    shorts/day11/output/youtube_metadata.txt
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
OUT_DIR = ROOT / "shorts" / "day11" / "output"
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


# High-energy sports commentator voiceover cues
NARRATION_CUES = [
    (0.04,  "ヘアピンからのジャンプスマッシュ！この一人称バドミントン、気持ちよすぎ！", "+20%", "+3Hz"),
    (2.65,  "遠いスマッシュもスライディング飛び込みでギリギリ拾える！", "+17%", "+2Hz"),
    (5.85,  "チュートリアル付きで、最強の鬼モードはガチで速い！", "+17%", "+2Hz"),
    (10.65, "あ、ちなみにオンライン対戦ボタンはあるけど正直まだ未完成！", "+16%", "+1Hz"),
    (14.30, "もしこの動画がバズったら、本気で作るかも！？", "+17%", "+3Hz"),
    (18.05, "100日後にバズるゲームを見たい人は、チャンネル登録よろしく！", "+15%", "+2Hz"),
    (21.85, "オンライン待ってる人や作ってほしいゲームは、コメント欄で教えてね！", "+16%", "+2Hz"),
]


def synthesize_tts_line(text: str, out_wav: Path, rate: str = "+17%", pitch: str = "+2Hz", sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    try:
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(
                text,
                voice="ja-JP-KeitaNeural",
                rate=rate,
                pitch=pitch,
            )
            await asyncio.wait_for(comm.save(str(tmp_mp3)), timeout=15.0)

        asyncio.run(_gen())
        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 500:
            af = (
                "silenceremove=start_periods=1:start_silence=0.02:start_threshold=-45dB,"
                "areverse,silenceremove=start_periods=1:start_silence=0.02:start_threshold=-45dB,areverse,"
                "highpass=f=85,"
                "equalizer=f=200:t=q:w=1.2:g=2.0,"
                "equalizer=f=3200:t=q:w=1.4:g=2.4,"
                "acompressor=threshold=-16dB:ratio=2.8:attack=6:release=80:makeup=1.8"
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

    # 138 BPM High-Tempo Electro-Sports Anthem (Am - F - C - G)
    bpm = 138.0
    step_dur = 60.0 / bpm / 4.0  # 16th note
    bar_dur = step_dur * 16.0

    chords = [
        (110.00, [220.00, 261.63, 329.63, 440.00]),  # Am
        (87.31,  [174.61, 220.00, 261.63, 349.23]),  # F
        (130.81, [261.63, 329.63, 392.00, 523.25]),  # C
        (98.00,  [196.00, 246.94, 293.66, 392.00]),  # G
    ]
    arp_idx = [0, 2, 1, 3, 2, 3, 0, 2, 1, 3, 2, 0, 3, 2, 1, 3]

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
            pad_l += np.sin(2.0 * math.pi * (f * 1.0025) * bt + ti * 0.35) * 0.23
            pad_r += np.sin(2.0 * math.pi * (f * 0.9975) * bt + ti * 0.75) * 0.23
        beat_phase = (bt % (step_dur * 4.0)) / (step_dur * 4.0)
        pump = 0.38 + 0.62 * np.minimum(1.0, beat_phase * 3.0)
        env = np.minimum(1.0, bt / 0.03) * np.minimum(1.0, (bar_dur - bt).clip(0) / 0.05)
        bgm_l[b0 : b0 + b_len] += pad_l * pump * env * 0.13
        bgm_r[b0 : b0 + b_len] += pad_r * pump * env * 0.13

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        t_step = i * step_dur
        s0 = int(t_step * sr)
        if s0 >= n_samples:
            break
        step16 = i % 16
        bar = i // 16
        bass_f, tones = chords[bar % len(chords)]

        if step16 in (0, 4, 8, 12) or (bar % 2 == 1 and step16 == 14):
            k_len = min(int(0.16 * sr), n_samples - s0)
            lt = np.arange(k_len, dtype=np.float32) / sr
            kf = 50.0 + 130.0 * np.exp(-lt * 36.0)
            kick = np.tanh(np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * 2.4) * np.exp(-lt * 13.0)
            add_stereo(bgm_l, bgm_r, s0, kick, pan=0.0, gain=0.23)

        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 111)
            sn_len = min(int(0.10 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            bright = np.diff(rng.uniform(-1.0, 1.0, sn_len).astype(np.float32), prepend=0.0)
            body = np.sin(2.0 * math.pi * 225.0 * slt) * np.exp(-slt * 26.0) * 0.42
            add_stereo(bgm_l, bgm_r, s0, bright * np.exp(-slt * 30.0) * 0.65 + body, pan=0.06 if step16 == 4 else -0.06, gain=0.14)

        if step16 % 2 == 0:
            rng = np.random.default_rng(seed=i + 911)
            hh_len = min(int(0.036 * sr), n_samples - s0)
            hlt = np.arange(hh_len, dtype=np.float32) / sr
            h_noise = np.diff(rng.uniform(-1.0, 1.0, hh_len).astype(np.float32), prepend=0.0)
            hat = h_noise * np.exp(-hlt * (60.0 if step16 % 4 == 2 else 100.0))
            add_stereo(bgm_l, bgm_r, s0, hat, pan=-0.25 if step16 % 4 == 0 else 0.25, gain=0.05)

        if step16 in (0, 2, 4, 6, 8, 10, 12, 14):
            blen = min(int(step_dur * 1.15 * sr), n_samples - s0)
            blt = np.arange(blen, dtype=np.float32) / sr
            bf = bass_f * (2.0 if step16 in (2, 6, 10, 14) else 1.0)
            bs = np.tanh((np.sin(2.0 * math.pi * bf * blt) * 0.72 + np.sin(2.0 * math.pi * bf * 2.0 * blt) * 0.28) * 1.5) * np.exp(-blt * 8.0)
            add_stereo(bgm_l, bgm_r, s0, bs, pan=0.0, gain=0.14)

            plen = min(int(0.13 * sr), n_samples - s0)
            plt = np.arange(plen, dtype=np.float32) / sr
            pf = tones[arp_idx[step16]] * 2.0
            pluck = (np.sin(2.0 * math.pi * pf * plt) * 0.65 + np.sin(2.0 * math.pi * pf * 2.0 * plt) * 0.24) * np.exp(-plt * 20.0)
            add_stereo(bgm_l, bgm_r, s0, pluck, pan=-0.38 if (step16 // 2) % 2 == 0 else 0.38, gain=0.075)

    def add_whoosh(t_sec: float, gain: float = 0.24):
        idx = int(t_sec * sr)
        wlen = int(0.18 * sr)
        wt = np.arange(wlen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 19)
        wn = rng.uniform(-1.0, 1.0, wlen).astype(np.float32)
        env = np.sin(math.pi * wt / 0.18) ** 1.6
        sweep = np.sin(2.0 * math.pi * np.cumsum(280.0 + 1500.0 * (wt / 0.18)) / sr) * 0.35
        add_stereo(sfx_l, sfx_r, idx, (wn * 0.45 + sweep) * env, pan=0.0, gain=gain)

    def add_racket_pop(t_sec: float, freq: float = 820.0, gain: float = 0.34):
        idx = int(t_sec * sr)
        plen = int(0.09 * sr)
        pt = np.arange(plen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 77)
        snap = rng.uniform(-1.0, 1.0, plen).astype(np.float32) * np.exp(-pt * 42.0) * 0.45
        pong = np.sin(2.0 * math.pi * np.cumsum(freq * (1.0 + 0.45 * np.exp(-pt * 38.0))) / sr) * np.exp(-pt * 28.0) * 0.65
        add_stereo(sfx_l, sfx_r, idx, snap + pong, pan=0.0, gain=gain)

    def add_smash_boom(t_sec: float, power: float = 1.0):
        idx = int(t_sec * sr)
        elen = int(0.38 * sr)
        lt = np.arange(elen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 55)
        crack = rng.uniform(-1.0, 1.0, elen).astype(np.float32) * np.exp(-lt * 28.0) * 0.42
        boom = np.tanh(np.sin(2.0 * math.pi * np.cumsum(260.0 * np.exp(-lt * 18.0) + 46.0) / sr) * 2.8) * np.exp(-lt * 8.5) * 0.52
        add_stereo(sfx_l, sfx_r, idx, crack + boom, pan=0.0, gain=0.88 * power)

    def add_slide_sfx(t_sec: float, gain: float = 0.36):
        idx = int(t_sec * sr)
        slen = int(0.28 * sr)
        st = np.arange(slen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 33)
        skid = np.diff(rng.uniform(-1.0, 1.0, slen).astype(np.float32), prepend=0.0) * np.exp(-st * 9.0) * 0.55
        chirp = np.sin(2.0 * math.pi * np.cumsum(2400.0 - 950.0 * (st / 0.28)) / sr) * np.exp(-st * 18.0) * 0.18
        add_stereo(sfx_l, sfx_r, idx, skid + chirp, pan=0.0, gain=gain)

    def add_bell_ding(t_sec: float, gain: float = 0.36):
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

    # Frame-accurate gameplay SFX
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        kind = ev.get("type")
        if kind == "hairpin":
            add_racket_pop(t0, freq=940.0, gain=0.38)
        elif kind == "rival_lift":
            add_racket_pop(t0, freq=620.0, gain=0.30)
        elif kind == "jump":
            add_racket_pop(t0, freq=420.0, gain=0.22)
        elif kind in ("meteor_smash", "smash"):
            add_smash_boom(t0, power=1.12 if kind == "meteor_smash" else 0.85)
        elif kind == "enemy_smash":
            add_smash_boom(t0, power=0.65)
        elif kind == "slide_dive":
            add_slide_sfx(t0, gain=0.40)
        elif kind in ("slide_save", "counter_drive"):
            add_smash_boom(t0, power=0.78)
        elif kind == "ui_whoosh":
            add_whoosh(t0, gain=0.22)

    add_bell_ding(19.45, gain=0.36)  # Subscribe button click -> 登録済み🔔
    add_racket_pop(21.85, freq=880.0, gain=0.28)  # Comment card pop

    # Studio Narration + Smooth Ducking
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day11_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.10 * sr)
        for idx, (cue_t, line_txt, rate, pitch) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, rate=rate, pitch=pitch, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.92
                s0 = max(int(cue_t * sr), prev_end_s + int(0.06 * sr))
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

    mix_l = bgm_l * duck + sfx_l * 0.88 + voice * 0.96
    mix_r = bgm_r * duck + sfx_r * 0.88 + voice * 0.96
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
    cur_x = center_x - sum(widths) / 2.0

    cx = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((cx + 4, y + 6), txt, font=font, fill=(0, 0, 0, 215), stroke_width=outer_stroke + 2, stroke_fill=(0, 0, 0, 200))
        cx += w

    cx = cur_x
    for (txt, _), w in zip(tokens, widths):
        draw.text((cx, y), txt, font=font, fill=(8, 12, 22, 255), stroke_width=outer_stroke, stroke_fill=(8, 12, 22, 255))
        cx += w

    cx = cur_x
    for (txt, color), w in zip(tokens, widths):
        draw.text((cx, y), txt, font=font, fill=(*color, 255), stroke_width=inner_stroke, stroke_fill=(10, 16, 28, 255))
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
        frame_img = apply_chromatic_split(frame_img, int(14 * impact_pulse))

    img = frame_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size

    # Bottom gradient vignette
    for gy in range(0, 420, 14):
        alpha = int(140 * (gy / 420.0) ** 1.4)
        draw.rectangle((0, H - 420 + gy, W, H - 420 + gy + 14), fill=(5, 9, 18, alpha))

    # Impact Anime Speedlines (Volt-Lime & Cyan BWF feel)
    if impact_pulse > 0.20:
        cx, cy = W // 2, int(H * 0.44)
        for i in range(30):
            ang = (i / 30.0) * math.tau + t * 5.6
            r1 = 300 + (i % 3) * 50
            r2 = 1120
            x1 = cx + int(math.cos(ang) * r1)
            y1 = cy + int(math.sin(ang) * r1)
            x2 = cx + int(math.cos(ang) * r2)
            y2 = cy + int(math.sin(ang) * r2)
            draw.line((x1, y1, x2, y2), fill=(*accent_rgb, int(185 * impact_pulse)), width=8 if i % 2 == 0 else 3)

    # =======================================================
    # 1. PRO TOUR CARBON x VOLT-LIME TOP HEADER (NEW STYLE!)
    # =======================================================
    hy0, hy1 = 56, 120
    draw_rounded_box(draw, (32, hy0, W - 32, hy1), 16, fill=(7, 11, 20, 224), outline=(190, 242, 100, 145), width=3)
    # Angular Volt-Lime DAY 11 plate on left
    draw.polygon([(40, hy0 + 7), (195, hy0 + 7), (180, hy1 - 7), (40, hy1 - 7)], fill=(190, 242, 100, 255))
    draw.text((54, hy0 + 13), "DAY 11", font=fonts["chip_b"], fill=(7, 11, 20, 255))
    draw.text((208, hy0 + 14), "SKY SMASH 3D // 一人称バドミントン", font=fonts["chip"], fill=(242, 246, 255, 255))

    # Live Telemetry Ticker below header (Y=132..176)
    if section_pill:
        sw = int(draw.textlength(section_pill, font=fonts["chip_sm"])) + 40
        draw.polygon([(36, 132), (36 + sw, 132), (36 + sw - 12, 174), (36, 174)], fill=(*accent_rgb, 240))
        draw.text((50, 137), section_pill, font=fonts["chip_sm"], fill=(7, 11, 20, 255))

    # =======================================================
    # 2. SUB-SECOND RALLY -> JUMP SMASH HOOK (0.00s - 1.55s)
    # =======================================================
    if t < 1.55:
        bounce = int(32 * math.exp(-t * 16.0))
        kick_y = int(14 * impact_pulse)
        # Live rally beat indicator!
        if t < 0.36:
            r_txt, r_col = "RALLY 1 // ネット前ヘアピン!!", (190, 242, 100)
        elif t < 0.78:
            r_txt, r_col = "RALLY 2 >> 高く上がった!! JUMP!!", (34, 211, 238)
        else:
            r_txt, r_col = "428 KM/H!! METEOR SMASH!!", (250, 204, 21)

        rw = int(draw.textlength(r_txt, font=fonts["ribbon"])) + 56
        rx0 = (W - rw) // 2
        ry = 248 - bounce - kick_y
        draw_rounded_box(draw, (rx0, ry, rx0 + rw, ry + 56), 12, fill=(7, 11, 20, 242), outline=(*r_col, 255), width=4)
        draw.text((rx0 + 28, ry + 8), r_txt, font=fonts["ribbon"], fill=(*r_col, 255))

        draw_rich_subtitle_line(
            draw, W // 2, ry + 74,
            [("ラリーからの", (255, 255, 255)), ("ジャンプスマッシュ", (190, 242, 100))],
            fonts["hook_sm"], outer_stroke=14, inner_stroke=5,
        )
        draw_rich_subtitle_line(
            draw, W // 2, ry + 150,
            [("脳汁やばすぎ!!", (250, 204, 21))],
            fonts["hook"], outer_stroke=16, inner_stroke=6,
        )

    # =======================================================
    # 3. HONEST ONLINE WIP CARD (10.60s - 18.00s)
    # =======================================================
    if 10.60 <= t < 18.00:
        age = t - 10.60
        pop = int(28 * math.exp(-age * 16.0))
        cy_box = 245 - pop if t < 13.00 else 285
        x0, x1 = 58, W - 58
        y0, y1 = cy_box, cy_box + 178
        draw_rounded_box(draw, (x0 + 6, y0 + 8, x1 + 6, y1 + 8), 22, fill=(0, 0, 0, 175))
        draw_rounded_box(draw, (x0, y0, x1, y1), 22, fill=(11, 17, 30, 242), outline=(250, 204, 21, 255), width=4)
        draw.rectangle((x0 + 20, y0 + 18, x0 + 30, y1 - 18), fill=(250, 204, 21, 255))
        draw.text((x0 + 48, y0 + 20), "【重要】オンライン1vs1はまだ未完成です！", font=fonts["cta_head_sm"], fill=(250, 204, 21, 255))
        draw.text((x0 + 48, y0 + 78), "この動画が伸びたら本気で作るかも!?", font=fonts["yt_name"], fill=(255, 255, 255, 255))
        draw.text((x0 + 48, y0 + 124), "まずは1人用ツアー＆『鬼』・スライディング拾いで遊んでみて！", font=fonts["yt_meta"], fill=(190, 242, 100, 255))

    # =======================================================
    # 4. SPORTS CREATOR SUBTITLES (1.55s - 18.00s)
    # =======================================================
    if sub_lines and 1.55 <= t < 18.00:
        age = max(0.0, t - seg_start)
        pop_y = int(20 * math.exp(-age * 18.0))
        if 5.80 <= t < 8.15 or 10.60 <= t < 13.00:
            base_y = 1480
        else:
            base_y = 1435 if len(sub_lines) == 2 else 1490
        for li, line_tokens in enumerate(sub_lines):
            draw_rich_subtitle_line(
                draw, W // 2, base_y + li * 80 + pop_y,
                line_tokens, fonts["sub_yt"], outer_stroke=13, inner_stroke=5,
            )

    # =======================================================
    # 5. MANDATORY YOUTUBE SUBSCRIBE CTA (18.00s - 21.80s)
    # =======================================================
    if 18.00 <= t < 21.80:
        age = t - 18.00
        pop_y = int(42 * math.exp(-age * 14.0))
        clicked = t >= 19.45
        click_age = max(0.0, t - 19.45)
        cx = W // 2

        draw_rich_subtitle_line(
            draw, cx, 1085 + pop_y,
            [("100日後に", (190, 242, 100)), ("バズるゲーム", (255, 255, 255)), ("見たい人は", (255, 255, 255))],
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
        draw_rounded_box(draw, (x0, y0, x1, y1), 34, fill=(14, 18, 30, 246), outline=(190, 242, 100, 90), width=3)

        av_cx, av_cy = x0 + 82, (y0 + y1) // 2
        draw.ellipse((av_cx - 48, av_cy - 48, av_cx + 48, av_cy + 48), fill=(190, 242, 100, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((av_cx - 32, av_cy - 18), "SKY", font=fonts["chip_b"], fill=(7, 11, 20, 255))

        draw.text((x0 + 148, y0 + 36), "100日後にバズるゲーム", font=fonts["yt_name"], fill=(255, 255, 255, 255))
        draw.text((x0 + 148, y0 + 88), "毎日1本ゲーム開発中！", font=fonts["yt_meta"], fill=(160, 174, 198, 255))

        btn_scale = 1.0 - 0.08 * math.exp(-click_age * 18.0) if clicked else (1.0 + 0.03 * math.sin(t * 10.0))
        bw, bh = int(265 * btn_scale), int(84 * btn_scale)
        bcx, bcy = x1 - 155, (y0 + y1) // 2
        bx0, by0, bx1, by1 = bcx - bw // 2, bcy - bh // 2, bcx + bw // 2, bcy + bh // 2

        if clicked:
            if click_age < 0.45:
                rr = int(45 + click_age * 240)
                ra = int(230 * (1.0 - click_age / 0.45))
                draw.ellipse((bcx - rr, bcy - rr, bcx + rr, bcy + rr), outline=(190, 242, 100, ra), width=7)
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

        if 18.45 <= t < 20.25:
            prog_c = min(1.0, max(0.0, (t - 18.45) / 0.95))
            ease = 1.0 - (1.0 - prog_c) ** 3
            px = int(bcx + 120 * (1.0 - ease))
            py = int(bcy + 145 * (1.0 - ease) + (8 if clicked and click_age < 0.14 else 0))
            poly = [(px, py), (px, py + 46), (px + 13, py + 34), (px + 25, py + 50), (px + 33, py + 45), (px + 21, py + 29), (px + 36, py + 29)]
            draw.polygon(poly, fill=(255, 255, 255, 255), outline=(12, 16, 28, 255))

    # =======================================================
    # 6. MANDATORY YOUTUBE COMMENT REQUEST CTA (21.80s - 25.50s)
    # =======================================================
    if t >= 21.80:
        age = t - 21.80
        pop_y = int(44 * math.exp(-age * 14.0))
        cx = W // 2

        draw_rich_subtitle_line(
            draw, cx, 1085 + pop_y,
            [("オンライン希望＆", (34, 211, 238)), ("作ってほしいゲーム", (255, 255, 255))],
            fonts["cta_head"], outer_stroke=13, inner_stroke=5,
        )
        draw_rich_subtitle_line(
            draw, cx, 1165 + pop_y,
            [("コメント欄", (190, 242, 100)), ("で教えてね!!", (255, 255, 255))],
            fonts["cta_head_lg"], outer_stroke=14, inner_stroke=5,
        )

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1288 + pop_y, 1468 + pop_y
        draw_rounded_box(draw, (x0 + 8, y0 + 12, x1 + 8, y1 + 12), 30, fill=(0, 0, 0, 180))
        draw_rounded_box(draw, (x0, y0, x1, y1), 30, fill=(14, 18, 30, 248), outline=(34, 211, 238, 245), width=4)

        draw.text((x0 + 38, y0 + 22), "コメント欄 // REQUEST & オンライン要望", font=fonts["yt_meta"], fill=(34, 211, 238, 255))
        draw_rounded_box(draw, (x0 + 34, y0 + 68, x1 - 34, y1 - 24), 18, fill=(24, 32, 50, 255), outline=(255, 255, 255, 45), width=2)
        sample = "「オンライン完成させて！次はテニスも！」"
        chars = min(len(sample), int(age * 16.0) + 1)
        cursor = "|" if int(t * 6.0) % 2 == 0 else ""
        draw.text((x0 + 54, y0 + 90), sample[:chars] + cursor, font=fonts["yt_name"], fill=(245, 248, 255, 255))

    if trans_flash > 0.02:
        draw.rectangle((0, 0, W, H), fill=(255, 255, 255, int(130 * trans_flash)))

    prog = min(1.0, t / total_dur)
    draw.rectangle((0, H - 10, W, H), fill=(15, 23, 42, 200))
    draw.rectangle((0, H - 10, int(W * prog), H), fill=(*accent_rgb, 255))

    return Image.alpha_composite(img, overlay).convert("RGB")


def render_note_thumbnail(browser: str, game_png_path: Path, out_png: Path, day_num: int = 11):
    """Consistent with Day 08 note_thumbnail.png format — clearly featuring DAY 11 badge & stamp."""
    b64 = base64.b64encode(game_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: radial-gradient(circle at 75% 45%, #065f46 0%, #0b1120 48%, #040812 100%);
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  color:#ffffff;display:flex;align-items:center;justify-content:space-between;
  padding:42px 54px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2.5px solid rgba(190,242,100,0.48);border-radius:22px;pointer-events:none;
}}
.left{{width:735px;z-index:2;}}
.top-row{{
  display:flex;align-items:center;gap:16px;margin-bottom:16px;
}}
.day-plate{{
  display:inline-flex;align-items:center;justify-content:center;
  padding:8px 24px;border-radius:14px;white-space:nowrap;flex-shrink:0;
  background:linear-gradient(135deg,#ef4444 0%,#dc2626 55%,#f97316 100%);
  border:4px solid #ffffff;
  color:#ffffff;font-weight:900;font-size:44px;line-height:1.0;letter-spacing:0.04em;
  box-shadow:0 10px 28px rgba(239,68,68,0.58), 0 4px 12px rgba(0,0,0,0.65);
  transform:skewX(-8deg);
}}
.day-plate span{{transform:skewX(8deg);display:inline-block;}}
.badge{{
  display:inline-block;padding:9px 18px;border-radius:999px;white-space:nowrap;
  background:rgba(15,23,42,0.88);border:2px solid rgba(190,242,100,0.75);
  color:#e2e8f0;font-weight:900;font-size:18.5px;letter-spacing:0.03em;
}}
h1{{
  font-size:74px;line-height:1.02;font-weight:900;color:#ffffff;margin-bottom:14px;
  text-shadow:0 8px 24px rgba(0,0,0,0.75);
}}
h1 span{{color:#bef264;}}
.sub{{font-size:29px;font-weight:900;color:#e2e8f0;line-height:1.4;margin-bottom:24px;}}
.sub strong{{color:#22d3ee;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(15,23,42,0.88);
  border:2px solid rgba(190,242,100,0.68);font-size:19px;font-weight:800;color:#ffffff;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #bef264;
  box-shadow:0 24px 60px rgba(0,0,0,0.75), 0 0 46px rgba(34,211,238,0.50);
  transform:rotate(2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:28px;left:-52px;transform:rotate(-8deg);
  padding:10px 24px;border-radius:14px;background:linear-gradient(90deg,#bef264,#22d3ee);
  border:3.5px solid #ffffff;color:#070b12;font-weight:900;font-size:27px;
  box-shadow:0 12px 28px rgba(0,0,0,0.6);
}}
</style></head><body>
  <div class="left">
    <div class="top-row">
      <div class="day-plate"><span>DAY {day_num}</span></div>
      <div class="badge">100日後にバズるゲーム ｜ 一人称3Dバドミントン</div>
    </div>
    <h1>SKY <span>SMASH 3D</span></h1>
    <div class="sub"><strong>数回ラリーからの爆速ジャンプスマッシュ!!</strong><br>スライディング拾い＆ヘアピン心理戦＆鬼強化</div>
    <div class="chips">
      <div class="chip">4段階チュートリアル</div>
      <div class="chip">スライディング飛び込み</div>
      <div class="chip">最難関【鬼】実装!!</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">DAY {day_num} 400km/hスマッシュ!!</div>
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
    text = (
        "[YouTube Shorts タイトル]\n"
        "【Day 11】1秒で脳汁!! 一人称3Dバドミントンのスマッシュ＆スライディング拾いが神すぎた!! #バドミントン #Shorts #個人開発\n\n"
        "[YouTube Shorts 説明文]\n"
        "スマホ・PC（縦画面・横画面どちらもOK）で今すぐ無料で遊べます▼\n"
        "https://kam2525-hub.github.io/note_create_use/games/day11-sky-smash-3d/\n\n"
        "⚠️ オンライン1vs1モードは現在まだ未完成（テスト中）です！\n"
        "🔥 もしこの動画が伸びたら本気で作るかも!?（ぜひ感想・要望をコメントで教えてください！）\n\n"
        "🔥 100日後にバズるゲームを見たい人は、チャンネル登録よろしく！\n"
        "💬 作ってほしいゲームがあったら、ぜひコメント欄で教えてね！\n\n"
        "100日後にバズるゲーム【Day 11】\n"
        "『SKY SMASH 3D（Three.js 一人称3Dバドミントンアクション）』\n\n"
        "💥 数回ラリーから飛び込む400km/h級「METEOR JUMP SMASH!!」\n"
        "💨 遠いスマッシュを床スレスレで拾い返す「スライディング飛び込み返し（SHIFT）」\n"
        "🎀 着弾直前スローで決める「PERFECT HAIRPIN!!」＆ 動き連動の一人称ラケット！\n"
        "🎓 4段階チュートリアル（STEP 1〜4）＆ 10.8m/sで返してくる最難関「鬼」搭載！\n\n"
        "#Shorts #YouTubeShorts #おすすめ #バズれ #100日後にバズるゲーム #100日後にバズるゲームを作る男 #Day11 #ゲーム11日目 #バドミントン #バド #バド部 #スマッシュ #ヘアピン #スライディング #ドロップ #スポーツゲーム #一人称3D #3Dゲーム #ThreeJS #ゲーム制作 #個人開発 #インディーゲーム #自作ゲーム #無料ゲーム #ブラウザゲーム #スマホゲーム #神ゲー #SKYSMASH3D\n\n"
        "[固定コメント案]\n"
        "🔥 100日後にバズるゲームを見たい人は、チャンネル登録よろしく！！\n"
        "⚠️ オンライン対戦はまだ未完成ですが、この動画が伸びたら本気で作るかもです👀\n"
        "💬 「オンライン早く作り込んで！」「次は〇〇作って！」などコメント欄で教えてね👇\n"
        "▼今すぐ無料でプレイ（スマホ縦/横・PC対応）\n"
        "https://kam2525-hub.github.io/note_create_use/games/day11-sky-smash-3d/\n\n"
        "[タグ（カンマ区切り）]\n"
        "Shorts,YouTubeShorts,おすすめ,100日後にバズるゲーム,100日後にバズるゲームを作る男,Day11,ゲーム11日目,バドミントン,バド,バド部,スマッシュ,ヘアピン,スライディング,飛び込みレシーブ,バドミントンゲーム,スポーツゲーム,一人称3D,3Dゲーム,Three.js,WebGL,ゲーム制作,個人開発,インディーゲーム,自作ゲーム,無料ゲーム,ブラウザゲーム,スマホゲーム,神ゲー,爽快,チュートリアル,鬼モード,SKY SMASH 3D\n"
    )
    out_path.write_text(text, encoding="utf-8")
    notes_meta = ROOT / "notes" / "day11" / "youtube_metadata.txt"
    if notes_meta.parent.exists():
        notes_meta.write_text(text, encoding="utf-8")


def main():
    browser = find_browser()
    srv, port = start_static_server(ROOT)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
    profile_dir = tempfile.mkdtemp(prefix="cdp_day11_")
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
    total_dur = 25.5
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

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day11-sky-smash-3d/index.html?shorts=1"})
        for _ in range(80):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true;")

        fonts = {
            "chip": ImageFont.truetype(FONT_SANS, 25),
            "chip_b": ImageFont.truetype(FONT_SANS, 27),
            "chip_sm": ImageFont.truetype(FONT_SANS, 24),
            "ribbon": ImageFont.truetype(FONT_SANS, 34),
            "hook_sm": ImageFont.truetype(FONT_SANS, 58),
            "hook": ImageFont.truetype(FONT_SANS, 82),
            "sub_yt": ImageFont.truetype(FONT_SANS, 58),
            "cta_head_sm": ImageFont.truetype(FONT_SANS, 40),
            "cta_head": ImageFont.truetype(FONT_SANS, 52),
            "cta_head_lg": ImageFont.truetype(FONT_SANS, 70),
            "yt_name": ImageFont.truetype(FONT_SANS, 34),
            "yt_meta": ImageFont.truetype(FONT_SANS, 24),
            "yt_btn": ImageFont.truetype(FONT_SANS, 32),
        }

        W_WHITE = (255, 255, 255)
        C_VOLT = (190, 242, 100)
        C_CYAN = (34, 211, 238)
        C_GOLD = (250, 204, 21)
        C_RED = (251, 113, 133)

        caption_plan = [
            (0.00, 1.55, "1ST-SEC SMASH", C_VOLT, []),
            (1.55, 5.80, "ヘアピン & スライディング", C_CYAN, [
                [("遠い球は", W_WHITE), ("スライディング", C_CYAN), ("で", W_WHITE)],
                [("飛び込み拾い", C_VOLT), ("できる!!", W_WHITE)],
            ]),
            (5.80, 8.15, "4段階アカデミー", C_VOLT, [
                [("新UIロビー＆", W_WHITE), ("4段階講座", C_VOLT), ("付き!", W_WHITE)],
            ]),
            (8.15, 10.60, "最難関【鬼】戦", C_RED, [
                [("強化された", W_WHITE), ("最難関【鬼】", C_RED)],
                [("0.34秒スマッシュ", C_GOLD), ("を返せ!!", W_WHITE)],
            ]),
            (10.60, 14.25, "DEV NOTE // オンライン開発中", C_GOLD, [
                [("オンライン対戦ボタン", W_WHITE), ("あるけど", W_WHITE)],
                [("実はまだ", W_WHITE), ("未完成!!", C_GOLD)],
            ]),
            (14.25, 18.00, "伸びたら作るかも!?", C_CYAN, [
                [("この動画が", W_WHITE), ("伸びたら", C_VOLT)],
                [("オンライン", C_CYAN), ("本気で作るかも!?", C_GOLD)],
            ]),
            (18.00, 21.80, "毎日開発中", C_RED, []),
            (21.80, 25.60, "リクエスト募集", C_CYAN, []),
        ]

        impact_peaks = [0.78, 3.12, 3.40, 4.92, 8.66, 9.84, 13.30, 13.56, 15.76, 18.58, 22.36, 24.16]
        cut_times = [1.55, 2.75, 5.80, 6.95, 8.15, 10.60, 13.00, 18.00, 21.80]
        thumb_src_path = OUT_DIR / "_thumb_src.png"

        print(f"Capturing {total_frames} frames ({total_dur}s @ {fps}fps)...")
        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            cdp.eval_js(f"window.__stepFrame({dt_sec:.6f});")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 94})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            sec_pill, accent, sub_lines, s0 = "1ST-SEC SMASH", C_VOLT, [], t
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
                if dt_c < 0.085:
                    t_flash = max(t_flash, (1.0 - dt_c / 0.085) ** 1.8)

            frame = draw_shorts_overlay(
                raw_img, t, total_dur, sec_pill, accent, sub_lines, s0, pulse, t_flash, fonts
            )
            if f_idx == 20:  # ~0.83s right at Meteor Jump Smash impact for thumbnail!
                frame.save(thumb_src_path)
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=93)

        events_json = cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]"
        events = json.loads(events_json)
        print(f"Captured {total_frames} frames, {len(events)} gameplay events.")
        cdp.close()

        wav_path = OUT_DIR / "audio.wav"
        print("Synthesizing Keita sports voiceover + 138 BPM Electro-Sports BGM + SFX...")
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day11_short.mp4"
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
            render_note_thumbnail(browser, thumb_src_path, OUT_DIR / "note_thumbnail.png", day_num=11)
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
