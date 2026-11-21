#!/usr/bin/env python3
"""
Day 06 YouTube Shorts (1080x1920, 60fps, 14.5s) — NEW VIRAL FIGHT-NIGHT TASTE!
Features:
- NUCLEAR 1-SECOND COLD-OPEN HOOK (0.00s..1.15s): Starts mid-climax vs Final Boss ZEUS OMEGA
  -> 0.05s JUST SLIP -> ULTRA COUNTER KO SLAM at 0.42s with chromatic RGB split + manga impact lines!
- Brand-new Fight-Night Kinetic Typography: slanted high-contrast PPV slam ribbons + telemetry badges
- 144 BPM Dark Phonk / Trap Boxing Beat (808 sub slides + iconic cowbell hook + trap hats)
- Frame-accurate layered boxing SFX (bell, glove whoosh, time-slow drop, bone-rattling counter impacts, crowd roar)
- Energetic Japanese male voiceover (edge-tts KeitaNeural with gTTS fallback) + automatic BGM ducking
- Generates both shorts/day06/output/day06_short.mp4 and shorts/day06/output/note_thumbnail.png
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
GAME_DIR = ROOT / "games" / "day06-counter-ko-3d"
OUT_DIR = ROOT / "shorts" / "day06" / "output"
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


# High-retention concise Japanese narration cues (guaranteed non-overlapping across 22.5s!)
NARRATION_CUES = [
    (0.05, "零点一秒の見切りから、一撃カウンターKO！"),
    (2.35, "二本指押しでガードとパリィ！"),
    (4.35, "敵のガードは上アッパーでぶち破れ！"),
    (7.30, "しゃがみ連打はダック狩りアッパーで即死！"),
    (10.85, "四つの難易度、勝つほど進化する全二十人の強敵！"),
    (15.45, "上下左右の極限見切りから、必殺アッパーで完全粉砕！"),
    (19.20, "ベリーハード五連戦、君は制覇できる？"),
]


def synthesize_tts_line(text: str, out_wav: Path, sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    # Try edge-tts energetic male voice (KeitaNeural) with crisp punchy pacing
    try:
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(text, voice="ja-JP-KeitaNeural", rate="+32%", pitch="+4Hz")
            await asyncio.wait_for(comm.save(str(tmp_mp3)), timeout=8.0)

        asyncio.run(_gen())
        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 500:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(tmp_mp3),
                    "-af", "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-42dB,areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-42dB,areverse,acompressor=threshold=-16dB:ratio=3:attack=5:release=60,highpass=f=95",
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            tmp_mp3.unlink(missing_ok=True)
            return True
    except Exception as exc:
        print(f"edge-tts fallback to gTTS for '{text}': {exc}")
        tmp_mp3.unlink(missing_ok=True)

    # Fallback: gTTS with fast punchy pitch shift & silence trim
    try:
        from gtts import gTTS

        gTTS(text=text, lang="ja").save(str(tmp_mp3))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_mp3),
                "-af", "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB,areverse,atempo=1.42,asetrate=44100*0.92,aresample=44100",
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

    # =====================================================================
    # 144 BPM DARK PHONK + NEON SYNTH ARENA BEAT (22.5s FULL PROGRESSION)
    # =====================================================================
    bpm = 144.0
    step_dur = 60.0 / bpm / 4.0  # 16th-note grid
    bass_notes = [41.20, 41.20, 49.00, 41.20, 55.00, 55.00, 46.25, 49.00]
    cowbell_riff = [659.25, 0, 783.99, 0, 987.77, 0, 880.00, 783.99,
                    659.25, 0, 739.99, 0, 659.25, 493.88, 659.25, 0]
    synth_arp = [329.63, 392.00, 493.88, 659.25, 587.33, 493.88, 440.00, 392.00]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        t_step = i * step_dur
        s0 = int(t_step * sr)
        s_len = min(int(step_dur * 1.45 * sr), n_samples - s0)
        if s_len <= 0:
            break
        lt = np.arange(s_len, dtype=np.float32) / sr
        step16 = i % 16

        # Heavy Distorted 808 Sub-Kick
        if step16 in (0, 6, 8, 14):
            bf = bass_notes[(i // 8) % len(bass_notes)]
            pitch_env = bf + 98.0 * np.exp(-lt * 34.0)
            sub = np.tanh(np.sin(2.0 * math.pi * np.cumsum(pitch_env) / sr) * 2.5) * np.exp(-lt * 6.2) * 0.26
            bgm[s0 : s0 + s_len] += sub

        # Punchy Trap Snare + Crisp Clap Layer on 4 and 12
        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 404)
            sn_len = min(int(0.12 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            snare = (
                rng.uniform(-1.0, 1.0, sn_len).astype(np.float32) * np.exp(-slt * 32.0) * 0.18
                + np.sin(2.0 * math.pi * (215.0 * np.exp(-slt * 22.0) + 125.0) * slt) * np.exp(-slt * 26.0) * 0.15
            )
            bgm[s0 : s0 + sn_len] += snare

        # Trap Hi-Hats (double-time 16th rolls in Act 4 & Act 5 climax!)
        if step16 % 2 == 0 or t_step > 10.8:
            rng = np.random.default_rng(seed=i + 808)
            h_len = min(int(0.032 * sr), n_samples - s0)
            hlt = np.arange(h_len, dtype=np.float32) / sr
            hat = rng.uniform(-1.0, 1.0, h_len).astype(np.float32) * np.exp(-hlt * 110.0) * 0.052
            bgm[s0 : s0 + h_len] += hat

        # Iconic Phonk Cowbell Hook
        cf = cowbell_riff[step16]
        if cf > 0 and t_step >= 0.40:
            c_len = min(int(0.14 * sr), n_samples - s0)
            clt = np.arange(c_len, dtype=np.float32) / sr
            cb = (
                np.sign(np.sin(2.0 * math.pi * cf * clt)) * 0.55
                + np.sign(np.sin(2.0 * math.pi * (cf * 1.498) * clt)) * 0.45
            ) * np.exp(-clt * 22.0) * (0.10 if t_step > 15.0 else 0.072)
            bgm[s0 : s0 + c_len] += cb

        # Dark Neon Arena Synth Arp (kicks in from Act 3 & peaks in Act 5!)
        if t_step >= 6.25 and step16 % 2 == 0:
            sf = synth_arp[(i // 2) % len(synth_arp)] * (1.5 if t_step > 15.4 else 1.0)
            a_len = min(int(0.15 * sr), n_samples - s0)
            alt = np.arange(a_len, dtype=np.float32) / sr
            arp = np.sin(2.0 * math.pi * sf * alt) * np.exp(-alt * 16.0) * (0.085 if t_step > 15.4 else 0.055)
            bgm[s0 : s0 + a_len] += arp

    # Smooth 0.9s tail fade on BGM at the very end (21.6s..22.5s)
    fade_n = int(0.90 * sr)
    if fade_n < n_samples:
        bgm[-fade_n:] *= np.linspace(1.0, 0.08, fade_n, dtype=np.float32)

    # =====================================================================
    # 0.00s NUCLEAR HOOK SOUND: BOXING BELL CLANG + SUB SLAM!
    # =====================================================================
    bell_len = min(int(0.75 * sr), n_samples)
    blt = np.arange(bell_len, dtype=np.float32) / sr
    bell = (
        np.sin(2.0 * math.pi * 880.0 * blt) * 0.24
        + np.sin(2.0 * math.pi * 1765.0 * blt) * 0.16
        + np.sin(2.0 * math.pi * 2642.0 * blt) * 0.10
    ) * np.exp(-blt * 5.2)
    sfx[:bell_len] += bell
    slam_len = min(int(0.24 * sr), n_samples)
    slt0 = np.arange(slam_len, dtype=np.float32) / sr
    sfx[:slam_len] += np.tanh(np.sin(2.0 * math.pi * np.cumsum(220.0 * np.exp(-slt0 * 18.0) + 42.0) / sr) * 2.0) * np.exp(-slt0 * 9.0) * 0.36

    # =====================================================================
    # FRAME-ACCURATE BOXING GAME EVENT SFX
    # =====================================================================
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        idx0 = int(t0 * sr)
        if idx0 >= n_samples:
            continue
        kind = ev.get("type")

        if kind == "dodge":
            e_len = min(int(0.11 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 11)
            sfx[idx0 : idx0 + e_len] += rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 26.0) * 0.14

        elif kind == "upper_warn":
            e_len = min(int(0.32 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(320.0, 1180.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 5.0) * 0.24

        elif kind == "sweep_warn":
            e_len = min(int(0.24 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(720.0, 260.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 6.5) * 0.20

        elif kind in ("blocked", "player_guard_hit"):
            e_len = min(int(0.11 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            sfx[idx0 : idx0 + e_len] += np.sign(np.sin(2.0 * math.pi * 195.0 * lt)) * np.exp(-lt * 30.0) * 0.18

        elif kind in ("guard_break", "just_parry"):
            e_len = min(int(0.32 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 91)
            shatter = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 14.0) * 0.26
            chime = np.sin(2.0 * math.pi * np.cumsum(np.linspace(520.0, 1580.0, e_len)) / sr) * np.exp(-lt * 10.0) * 0.28
            sfx[idx0 : idx0 + e_len] += shatter + chime

        elif kind == "just_slip":
            e_len = min(int(0.28 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            drop = np.sin(2.0 * math.pi * np.cumsum(190.0 * np.exp(-lt * 16.0) + 46.0) / sr) * np.exp(-lt * 9.0) * 0.34
            zing = np.sin(2.0 * math.pi * np.cumsum(np.linspace(720.0, 1680.0, e_len)) / sr) * np.exp(-lt * 18.0) * 0.22
            sfx[idx0 : idx0 + e_len] += drop + zing

        elif kind in ("counter_hit", "punch_hit"):
            heavy = kind == "counter_hit"
            e_len = min(int((0.20 if heavy else 0.12) * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 33)
            thud = np.tanh(np.sin(2.0 * math.pi * np.cumsum(175.0 * np.exp(-lt * 24.0) + 44.0) / sr) * 2.2) * np.exp(-lt * 14.0) * (0.38 if heavy else 0.24)
            crack = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 42.0) * (0.28 if heavy else 0.16)
            ring = np.sin(2.0 * math.pi * 1046.5 * lt) * np.exp(-lt * 20.0) * (0.14 if heavy else 0.0)
            sfx[idx0 : idx0 + e_len] += thud + crack + ring

        elif kind in ("ko_hit", "ultra_hit", "ko_finish"):
            e_len = min(int(0.85 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 77)
            mega_sub = np.tanh(np.sin(2.0 * math.pi * np.cumsum(190.0 * np.exp(-lt * 10.0) + 34.0) / sr) * 2.6) * np.exp(-lt * 3.8) * 0.50
            shatter = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 9.0) * 0.30
            ko_bell = (
                np.sin(2.0 * math.pi * 920.0 * lt) * 0.20
                + np.sin(2.0 * math.pi * 1845.0 * lt) * 0.14
            ) * np.exp(-lt * 4.5)
            sfx[idx0 : idx0 + e_len] += mega_sub + shatter + ko_bell

        elif kind in ("cut_act2", "cut_act3", "cut_montage", "cut_finale"):
            e_len = min(int(0.10 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(1200.0, 260.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 24.0) * 0.20

    # =====================================================================
    # NON-OVERLAPPING DYNAMIC VOICEOVER SCHEDULER + SMOOTH SIDECHAIN DUCK
    # =====================================================================
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day06_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.12 * sr)
        for idx, (cue_t, line_txt) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.86
                # Guarantee zero overlap with previous cue!
                s0 = max(int(cue_t * sr), prev_end_s + int(0.18 * sr))
                if s0 + len(arr) > n_samples - int(0.35 * sr):
                    # Gently time-compress if needed so last word NEVER clips!
                    avail = max(int(0.5 * sr), n_samples - int(0.35 * sr) - s0)
                    if len(arr) > avail:
                        ratio = min(1.35, len(arr) / float(avail))
                        fast_wav = tts_tmp / f"cue_{idx}_fast.wav"
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", str(cue_wav), "-af", f"atempo={ratio:.3f}", "-ar", str(sr), "-ac", "1", str(fast_wav)],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        arr = load_wav_mono(fast_wav)
                        peak2 = float(np.max(np.abs(arr))) if len(arr) else 0.0
                        if peak2 > 0.01:
                            arr = (arr / peak2) * 0.86
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    prev_end_s = s0 + s_len
                    # Smooth duck envelope around voice
                    d0 = max(0, s0 - ramp_n)
                    d1 = min(n_samples, s0 + s_len + ramp_n)
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.24)
                    if s0 > d0:
                        duck[d0:s0] = np.minimum(duck[d0:s0], np.linspace(1.0, 0.24, s0 - d0, dtype=np.float32))
                    if d1 > s0 + s_len:
                        duck[s0 + s_len : d1] = np.minimum(duck[s0 + s_len : d1], np.linspace(0.24, 1.0, d1 - (s0 + s_len), dtype=np.float32))
                    print(f"  Voice cue {idx}: {s0/sr:.2f}s .. {(s0+s_len)/sr:.2f}s ({line_txt})")
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    mixed = bgm * duck + sfx * 0.84 + voice
    mixed = np.tanh(mixed * 1.18) * 0.90
    pcm = np.clip(mixed * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# =========================================================================
# NEW VIRAL FIGHT-NIGHT VISUAL POST-FX (CHROMATIC IMPACT + SLANTED PPV BANNERS)
# =========================================================================
def apply_chromatic_split(img: Image.Image, shift: int) -> Image.Image:
    if shift <= 0:
        return img
    r, g, b = img.split()
    r = ImageChops.offset(r, shift, 0)
    b = ImageChops.offset(b, -shift, 0)
    return Image.merge("RGB", (r, g, b))


def draw_fight_night_overlay(
    frame_img: Image.Image,
    t: float,
    tag_text: str,
    main_text: str,
    sub_text: str,
    accent_rgb: tuple,
    seg_start: float,
    impact_pulse: float,
    font_tag,
    font_big,
    font_med,
    font_sub,
) -> Image.Image:
    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.BILINEAR)

    # Chromatic RGB aberration burst on heavy impacts & fast cuts!
    if impact_pulse > 0.15:
        frame_img = apply_chromatic_split(frame_img, int(14 * impact_pulse))

    img = frame_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size

    # Subtle manga radial impact bursts on peak moments
    if impact_pulse > 0.25:
        cx, cy = W // 2, int(H * 0.44)
        for i in range(24):
            ang = (i / 24.0) * math.tau + t * 5.0
            r1 = 360 + (i % 3) * 45
            r2 = 1050
            x1 = cx + int(math.cos(ang) * r1)
            y1 = cy + int(math.sin(ang) * r1)
            x2 = cx + int(math.cos(ang) * r2)
            y2 = cy + int(math.sin(ang) * r2)
            col = (*accent_rgb, int(170 * impact_pulse))
            draw.line((x1, y1, x2, y2), fill=col, width=7 if i % 2 == 0 else 3)

    # Top-center PPV Slanted Kinetic Slam Banner (tucked cleanly under the enemy HP HUD!)
    if main_text:
        age = max(0.0, t - seg_start)
        slam_drop = int(34 * math.exp(-age * 18.0))
        fnt = font_big if len(main_text) <= 13 else font_med
        tb = draw.textbbox((0, 0), main_text, font=fnt, stroke_width=10)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]

        box_cx = W // 2
        box_cy = 344 - slam_drop
        pad_x = 46
        pad_y = 22
        bw = min(W - 60, tw + pad_x * 2)
        bh = th + pad_y * 2
        x0 = box_cx - bw // 2
        x1 = box_cx + bw // 2
        y0 = box_cy - bh // 2
        y1 = box_cy + bh // 2
        skew = 18

        # Slanted obsidian Fight-Night speed-ribbon backing
        poly_shadow = [(x0 + skew + 8, y0 + 10), (x1 + skew + 8, y0 + 10), (x1 - skew + 8, y1 + 10), (x0 - skew + 8, y1 + 10)]
        draw.polygon(poly_shadow, fill=(0, 0, 0, 170))
        poly = [(x0 + skew, y0), (x1 + skew, y0), (x1 - skew, y1), (x0 - skew, y1)]
        draw.polygon(poly, fill=(10, 12, 22, 232))

        # Neon left/right speed accent stripes
        stripe_l = [(x0 + skew, y0), (x0 + skew + 18, y0), (x0 - skew + 18, y1), (x0 - skew, y1)]
        stripe_r = [(x1 + skew - 14, y0), (x1 + skew, y0), (x1 - skew, y1), (x1 - skew - 14, y1)]
        draw.polygon(stripe_l, fill=(*accent_rgb, 255))
        draw.polygon(stripe_r, fill=(*accent_rgb, 255))

        # Top/bottom accent hairline
        draw.line([(x0 + skew, y0), (x1 + skew, y0)], fill=(*accent_rgb, 240), width=5)
        draw.line([(x0 - skew, y1), (x1 - skew, y1)], fill=(*accent_rgb, 240), width=5)

        # Mini Kicker Tag overlapping top-left of ribbon
        if tag_text:
            ttb = draw.textbbox((0, 0), tag_text, font=font_tag)
            ttw = ttb[2] - ttb[0]
            tth = ttb[3] - ttb[1]
            tx0 = x0 + 24
            ty0 = y0 - tth - 16
            draw.polygon(
                [(tx0 + 8, ty0), (tx0 + ttw + 38, ty0), (tx0 + ttw + 28, ty0 + tth + 14), (tx0 - 2, ty0 + tth + 14)],
                fill=(*accent_rgb, 255),
            )
            draw.text((tx0 + 14, ty0 + 4), tag_text, font=font_tag, fill=(10, 12, 22, 255))

        # Main Punchy Headline
        tx = box_cx - tw // 2
        ty = box_cy - th // 2 - 4
        draw.text(
            (tx, ty),
            main_text,
            font=fnt,
            fill=(255, 255, 255, 255),
            stroke_width=10,
            stroke_fill=(8, 10, 18, 255),
        )

        # Sub-caption punchline just beneath ribbon
        if sub_text:
            stb = draw.textbbox((0, 0), sub_text, font=font_sub, stroke_width=8)
            stw = stb[2] - stb[0]
            stx = (W - stw) // 2
            sty = y1 + 14
            draw.text(
                (stx, sty),
                sub_text,
                font=font_sub,
                fill=(*accent_rgb, 255),
                stroke_width=8,
                stroke_fill=(8, 10, 18, 255),
            )

    # Bottom Viral Beat-Progress Bar (sleek 10px neon energy bar at very bottom)
    prog = min(1.0, t / 22.5)
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
  background: radial-gradient(circle at 75% 45%, #7f1d1d 0%, #1e1b4b 42%, #070812 100%);
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  color:#ffffff;display:flex;align-items:center;justify-content:space-between;
  padding:46px 56px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2.5px solid rgba(253,224,71,0.38);border-radius:22px;pointer-events:none;
}}
.left{{width:725px;z-index:2;}}
.badge{{
  display:inline-block;padding:8px 22px;border-radius:999px;
  background:linear-gradient(90deg,#f43f5e,#f59e0b);color:#ffffff;
  font-weight:900;font-size:22px;letter-spacing:0.06em;margin-bottom:18px;
  box-shadow:0 8px 24px rgba(244,63,94,0.45);
}}
h1{{
  font-size:74px;line-height:1.02;font-weight:900;letter-spacing:0.01em;
  color:#ffffff;margin-bottom:16px;
  text-shadow:0 8px 24px rgba(0,0,0,0.7);
}}
h1 span{{color:#fde047;}}
.sub{{
  font-size:32px;font-weight:900;color:#e2e8f0;line-height:1.38;margin-bottom:26px;
}}
.sub strong{{color:#38bdf8;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(15,23,42,0.85);
  border:2px solid rgba(253,224,71,0.65);font-size:19px;font-weight:800;color:#ffffff;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #fde047;
  box-shadow:0 24px 60px rgba(0,0,0,0.75), 0 0 46px rgba(244,63,94,0.55);
  transform:rotate(2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:30px;left:-42px;transform:rotate(-8deg);
  padding:10px 24px;border-radius:14px;background:linear-gradient(90deg,#ef4444,#f59e0b);
  border:3.5px solid #ffffff;color:#ffffff;font-weight:900;font-size:28px;
  box-shadow:0 12px 28px rgba(0,0,0,0.6);
}}
</style></head><body>
  <div class="left">
    <div class="badge">GAME DAY 06 ｜ Three.js 一人称3Dボクシング</div>
    <h1>COUNTER <span>KO 3D</span></h1>
    <div class="sub"><strong>上下左右の見切り</strong>×<strong>2本指ガード</strong><br>4難度×5連戦（全20強敵）を0遅延で粉砕！</div>
    <div class="chips">
      <div class="chip">⚡ Three.js ネオン3D</div>
      <div class="chip">🛡 2本指ガード＆崩し</div>
      <div class="chip">🥊 4難度×5試合＝20強敵</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">一撃KO!!</div>
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


def main():
    browser = find_browser()
    srv, port = start_static_server(ROOT)
    dbg_port = 9286
    profile_dir = tempfile.mkdtemp(prefix="cdp_day06_")
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
    total_dur = 22.5
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
            "width": 540, "height": 960, "deviceScaleFactor": 1.5, "mobile": True
        })

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day06-counter-ko-3d/index.html?shorts=1"})
        for _ in range(60):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true;")

        font_tag = ImageFont.truetype(FONT_SANS, 28)
        font_big = ImageFont.truetype(FONT_SANS, 62)
        font_med = ImageFont.truetype(FONT_SANS, 48)
        font_sub = ImageFont.truetype(FONT_SANS, 38)

        # Full 22.5s Fight-Night PPV Caption Script (zero tofu boxes!)
        caption_plan = [
            (0.00, 1.80, "0.1秒見切り", "一撃カウンターKO!!", "Three.js リアルネオン3Dボクシング!!", (253, 224, 71)),
            (1.80, 3.45, "新機能 2本指ガード", "2本指同時押しでパリィ!!", "直前ガードで0ダメージ＆カウンター!!", (0, 229, 255)),
            (3.45, 5.45, "鉄壁3Dガード", "上アッパーでガード粉砕!!", "連打は弾かれる → 上スワイプで崩せ!!", (0, 229, 255)),
            (5.45, 6.25, "上下左右の読み合い", "緑の薙ぎ払いは下ダック!!", "横逃げ不可!! 潜って反撃!!", (74, 222, 128)),
            (6.25, 7.65, "駆け引き", "フックはダックで回避!", "しかし次の瞬間…", (163, 230, 53)),
            (7.65, 10.80, "ダック狩りアッパー", "しゃがみ連打は即死!!", "赤アッパーは横へ見切れ!!", (244, 63, 94)),
            (10.80, 15.40, "4難度 × 5連戦", "勝つほど強敵が進化!!", "EASY / NORMAL / HARD / VERY HARD", (250, 204, 21)),
            (15.40, 18.48, "20人目の裏世界王者", "4方向見切り＆2本指パリィ!!", "右!! 下!! ガード!! 左見切り!!", (0, 229, 255)),
            (18.48, 22.55, "ULTRA COUNTER KO", "ベリーハード5連戦制覇できる？", "リンクから今すぐ無料プレイ ▼", (253, 224, 71)),
        ]

        # Peaks where chromatic RGB split + manga impact lines fire!
        impact_peaks = [0.00, 0.14, 0.42, 1.80, 2.28, 4.52, 5.96, 6.25, 8.22, 9.52, 10.80, 12.15, 13.70, 15.40, 17.24, 18.08, 18.62]

        thumb_src_path = OUT_DIR / "_thumb_src.png"

        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            cdp.eval_js(f"window.__stepFrame({dt_sec:.6f});")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 93})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            # Capture crisp mid-impact ULTRA COUNTER KO frame (0.46s)
            if f_idx == 11:
                raw_img.resize((1080, 1920), Image.Resampling.LANCZOS).save(thumb_src_path)

            tag, main_txt, sub_txt, accent, s0 = "", "", "", (253, 224, 71), t
            for seg in caption_plan:
                if seg[0] <= t < seg[1]:
                    s0, _, tag, main_txt, sub_txt, accent = seg
                    break

            # Compute impact chromatic pulse intensity
            pulse = 0.0
            for pt in impact_peaks:
                if 0.0 <= (t - pt) < 0.22:
                    pulse = max(pulse, math.exp(-(t - pt) * 14.0))

            frame = draw_fight_night_overlay(
                raw_img, t, tag, main_txt, sub_txt, accent, s0, pulse,
                font_tag, font_big, font_med, font_sub,
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=92)

        events_json = cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]"
        events = json.loads(events_json)
        cdp.close()

        wav_path = OUT_DIR / "audio.wav"
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day06_short.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%04d.jpg"),
                "-i", str(wav_path),
                "-c:v", "libx264",
                "-preset", "fast",
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

        print(f"Generated Day 06 Viral Fight-Night Short: {out_mp4} ({out_mp4.stat().st_size // 1024} KB)")
        print(f"Recorded events: {len(events)}")
    finally:
        proc.terminate()
        shutil.rmtree(profile_dir, ignore_errors=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
