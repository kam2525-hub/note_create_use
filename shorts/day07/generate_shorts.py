#!/usr/bin/env python3
"""
Day 07 YouTube Shorts (1080x1920, 24fps, 23.5s) — PHANTOM RUSH 3D
Features:
- NUCLEAR COLD-OPEN (0.00s..1.85s): Starts inside Crimson Torii Boss Dimension -> Golden CLASH -> Rush -> Finisher!
- Neon Rooftop Parkour, JUST SLASH!! 3D body split, Plasma Orb PARRY, OVERDRIVE MODE!
- Dedicated Boss Dimension Warp (Crimson Torii Shrine + Blood Moon) -> Shockwave Jump -> Clash -> Rapid Rush -> Finisher -> 3-Choice MOD Awakening!
- PERMANENT HIGH-CONVERTING CTAs (17.2s..23.5s over blazing Overdrive gameplay):
  1. Subscribe CTA: 「100日後にバズるゲームを見たい人、チャンネル登録よろしく！」 + glowing YouTube Red Subscribe Card
  2. Comment CTA:   「作って欲しいゲームがあったら、コメント欄によろしく！」 + Cyan/Gold Comment Request Card
- 142 BPM Cyber-Katana Phonk Beat + frame-accurate Katana/Clash/Warp/Finisher SFX + Japanese Voiceover (edge-tts KeitaNeural)
- Outputs: shorts/day07/output/day07_short.mp4 and shorts/day07/output/note_thumbnail.png
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
OUT_DIR = ROOT / "shorts" / "day07" / "output"
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


# High-retention Japanese narration cues (guaranteed non-overlapping & zero clipping across 23.5s!)
NARRATION_CUES = [
    (0.05, "100日後にバズるゲーム、7日目！一人称3D斬撃アクション！"),
    (3.10, "ネオン屋上を音速疾走！引きつけて斬るジャストスラッシュで敵を真っ二つ！"),
    (6.60, "敵の弾は刀でパリィ！ゲージ満タンで無敵のオーバードライブ！"),
    (9.70, "ボス戦は紅蓮の異界ステージへワープ！突進を弾き返し、超連打で一閃両断！"),
    (14.70, "ボス撃破で3択の能力が覚醒！"),
    (17.10, "100日後にバズるゲームを見たい人、チャンネル登録よろしく！"),
    (20.15, "作って欲しいゲームがあったら、コメント欄によろしく！"),
]


def synthesize_tts_line(text: str, out_wav: Path, sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    try:
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(text, voice="ja-JP-KeitaNeural", rate="+38%", pitch="+4Hz")
            await asyncio.wait_for(comm.save(str(tmp_mp3)), timeout=10.0)

        asyncio.run(_gen())
        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 500:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(tmp_mp3),
                    "-af", "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-42dB,areverse,silenceremove=start_periods=1:start_silence=0.04:start_threshold=-42dB,areverse,acompressor=threshold=-16dB:ratio=3:attack=5:release=60,highpass=f=95",
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            tmp_mp3.unlink(missing_ok=True)
            return True
    except Exception as exc:
        print(f"edge-tts fallback to gTTS for '{text}': {exc}")
        tmp_mp3.unlink(missing_ok=True)

    try:
        from gtts import gTTS

        gTTS(text=text, lang="ja").save(str(tmp_mp3))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_mp3),
                "-af", "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_silence=0.04:start_threshold=-40dB,areverse,atempo=1.40,asetrate=44100*0.92,aresample=44100",
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
    # 142 BPM CYBER-KATANA PHONK + SHAMISEN SYNTH BEAT
    # =====================================================================
    bpm = 142.0
    step_dur = 60.0 / bpm / 4.0
    bass_notes = [49.00, 49.00, 55.00, 49.00, 65.41, 65.41, 58.27, 55.00]
    lead_riff = [
        659.25, 0, 783.99, 987.77, 0, 880.00, 783.99, 659.25,
        587.33, 0, 659.25, 783.99, 0, 987.77, 1174.66, 0,
    ]
    pentatonic = [523.25, 587.33, 659.25, 783.99, 880.00, 1046.50, 1174.66, 1318.51]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        t_step = i * step_dur
        s0 = int(t_step * sr)
        s_len = min(int(step_dur * 1.45 * sr), n_samples - s0)
        if s_len <= 0:
            break
        lt = np.arange(s_len, dtype=np.float32) / sr
        step16 = i % 16
        is_boss_sec = (t_step < 1.85) or (9.45 <= t_step < 15.35)

        # Heavy 808 Cyber Kick
        if step16 in (0, 6, 8, 14):
            bf = bass_notes[(i // 8) % len(bass_notes)] * (0.85 if is_boss_sec else 1.0)
            pitch_env = bf + 108.0 * np.exp(-lt * 34.0)
            sub = np.tanh(np.sin(2.0 * math.pi * np.cumsum(pitch_env) / sr) * 2.6) * np.exp(-lt * 6.0) * 0.25
            bgm[s0 : s0 + s_len] += sub

        # Crisp Cyber Snare on 4 & 12
        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 707)
            sn_len = min(int(0.11 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            snare = (
                rng.uniform(-1.0, 1.0, sn_len).astype(np.float32) * np.exp(-slt * 34.0) * 0.16
                + np.sin(2.0 * math.pi * (220.0 * np.exp(-slt * 22.0) + 130.0) * slt) * np.exp(-slt * 26.0) * 0.13
            )
            bgm[s0 : s0 + sn_len] += snare

        # Fast Hi-Hats
        if step16 % 2 == 0 or t_step > 9.45:
            rng = np.random.default_rng(seed=i + 909)
            h_len = min(int(0.03 * sr), n_samples - s0)
            hlt = np.arange(h_len, dtype=np.float32) / sr
            hat = rng.uniform(-1.0, 1.0, h_len).astype(np.float32) * np.exp(-hlt * 115.0) * 0.048
            bgm[s0 : s0 + h_len] += hat

        # Cyber Shamisen / Phonk Lead
        lf = lead_riff[step16]
        if lf > 0:
            c_len = min(int(0.13 * sr), n_samples - s0)
            clt = np.arange(c_len, dtype=np.float32) / sr
            pl = (
                np.sign(np.sin(2.0 * math.pi * lf * clt)) * 0.45
                + np.sin(2.0 * math.pi * (lf * 2.0) * clt) * 0.35
            ) * np.exp(-clt * 20.0) * (0.09 if is_boss_sec else 0.068)
            bgm[s0 : s0 + c_len] += pl

    # Smooth tail fade on BGM at very end
    fade_n = int(0.90 * sr)
    if fade_n < n_samples:
        bgm[-fade_n:] *= np.linspace(1.0, 0.12, fade_n, dtype=np.float32)

    # =====================================================================
    # FRAME-ACCURATE KATANA & BOSS DIMENSION SFX
    # =====================================================================
    kill_counter = 0
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        idx0 = int(t0 * sr)
        if idx0 >= n_samples:
            continue
        kind = ev.get("type")

        if kind in ("slash_kill", "just_slash", "rush_hit"):
            kill_counter += 1
            is_just = kind != "slash_kill"
            e_len = min(int(0.28 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 17)
            steel = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 42.0) * 0.28
            sub = np.tanh(np.sin(2.0 * math.pi * np.cumsum(165.0 * np.exp(-lt * 20.0) + 36.0) / sr) * 2.2) * np.exp(-lt * 11.0) * (0.38 if is_just else 0.30)
            note = pentatonic[kill_counter % len(pentatonic)]
            chime = (
                np.sin(2.0 * math.pi * note * lt) * 0.18
                + np.sin(2.0 * math.pi * (note * 1.5) * lt) * (0.12 if is_just else 0.06)
            ) * np.exp(-lt * 10.0)
            sfx[idx0 : idx0 + e_len] += steel + sub + chime

        elif kind == "parry":
            e_len = min(int(0.32 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            ring = (
                np.sin(2.0 * math.pi * 1320.0 * lt) * 0.24
                + np.sin(2.0 * math.pi * 2640.0 * lt) * 0.18
            ) * np.exp(-lt * 9.0)
            sub = np.sin(2.0 * math.pi * np.cumsum(180.0 * np.exp(-lt * 18.0) + 42.0) / sr) * np.exp(-lt * 12.0) * 0.34
            sfx[idx0 : idx0 + e_len] += ring + sub

        elif kind == "clash":
            # Metallic Samurai Blade Clash ("KIIN!! DON!!")
            e_len = min(int(0.45 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 55)
            shatter = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 22.0) * 0.32
            clang = (
                np.sin(2.0 * math.pi * 1760.0 * lt) * 0.24
                + np.sin(2.0 * math.pi * 2637.0 * lt) * 0.20
                + np.sin(2.0 * math.pi * 3520.0 * lt) * 0.14
            ) * np.exp(-lt * 6.5)
            boom = np.tanh(np.sin(2.0 * math.pi * np.cumsum(170.0 * np.exp(-lt * 15.0) + 34.0) / sr) * 2.5) * np.exp(-lt * 7.5) * 0.44
            sfx[idx0 : idx0 + e_len] += shatter + clang + boom

        elif kind == "finisher":
            # Massive Execution Slash + Thunder Boom
            e_len = min(int(0.85 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            rng = np.random.default_rng(seed=idx0 + 99)
            shatter = rng.uniform(-1.0, 1.0, e_len).astype(np.float32) * np.exp(-lt * 8.5) * 0.34
            thunder = np.tanh(np.sin(2.0 * math.pi * np.cumsum(190.0 * np.exp(-lt * 9.0) + 28.0) / sr) * 2.8) * np.exp(-lt * 3.6) * 0.50
            chord = (
                np.sin(2.0 * math.pi * 1046.5 * lt) * 0.20
                + np.sin(2.0 * math.pi * 1568.0 * lt) * 0.16
                + np.sin(2.0 * math.pi * 2093.0 * lt) * 0.14
            ) * np.exp(-lt * 4.2)
            sfx[idx0 : idx0 + e_len] += shatter + thunder + chord

        elif kind in ("warp_boss", "warp_return", "overdrive"):
            e_len = min(int(0.40 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(180.0, 1480.0, e_len, dtype=np.float32)
            whoosh = np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 5.0) * 0.26
            sfx[idx0 : idx0 + e_len] += whoosh

        elif kind in ("cut", "mod_open"):
            e_len = min(int(0.12 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(1200.0, 280.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 22.0) * 0.18

    # =====================================================================
    # NON-OVERLAPPING DYNAMIC VOICEOVER SCHEDULER + SIDECHAIN DUCK
    # =====================================================================
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day07_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.10 * sr)
        for idx, (cue_t, line_txt) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.88
                s0 = max(int(cue_t * sr), prev_end_s + int(0.14 * sr))
                if s0 + len(arr) > n_samples - int(0.25 * sr):
                    avail = max(int(0.6 * sr), n_samples - int(0.25 * sr) - s0)
                    if len(arr) > avail:
                        ratio = min(1.38, len(arr) / float(avail))
                        fast_wav = tts_tmp / f"cue_{idx}_fast.wav"
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", str(cue_wav), "-af", f"atempo={ratio:.3f}", "-ar", str(sr), "-ac", "1", str(fast_wav)],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        arr = load_wav_mono(fast_wav)
                        peak2 = float(np.max(np.abs(arr))) if len(arr) else 0.0
                        if peak2 > 0.01:
                            arr = (arr / peak2) * 0.88
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    prev_end_s = s0 + s_len
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

    mixed = bgm * duck + sfx * 0.85 + voice
    mixed = np.tanh(mixed * 1.18) * 0.90
    pcm = np.clip(mixed * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def apply_chromatic_split(img: Image.Image, shift: int) -> Image.Image:
    if shift <= 0:
        return img
    r, g, b = img.split()
    r = ImageChops.offset(r, shift, 0)
    b = ImageChops.offset(b, -shift, 0)
    return Image.merge("RGB", (r, g, b))


def draw_rounded_box(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 0):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_shorts_overlay(
    frame_img: Image.Image,
    t: float,
    total_dur: float,
    tag_text: str,
    main_text: str,
    sub_text: str,
    accent_rgb: tuple,
    seg_start: float,
    impact_pulse: float,
    fonts: dict,
) -> Image.Image:
    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.BILINEAR)

    if impact_pulse > 0.15:
        frame_img = apply_chromatic_split(frame_img, int(14 * impact_pulse))

    img = frame_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size

    # Manga speed burst lines on peak slashes & finishers
    if impact_pulse > 0.24:
        cx, cy = W // 2, int(H * 0.45)
        for i in range(24):
            ang = (i / 24.0) * math.tau + t * 5.0
            r1 = 350 + (i % 3) * 45
            r2 = 1060
            x1 = cx + int(math.cos(ang) * r1)
            y1 = cy + int(math.sin(ang) * r1)
            x2 = cx + int(math.cos(ang) * r2)
            y2 = cy + int(math.sin(ang) * r2)
            draw.line((x1, y1, x2, y2), fill=(*accent_rgb, int(170 * impact_pulse)), width=7 if i % 2 == 0 else 3)

    # Top Slanted Kinetic Ribbon (tucked cleanly under top HUD!)
    if main_text:
        age = max(0.0, t - seg_start)
        slam_drop = int(32 * math.exp(-age * 18.0))
        fnt = fonts["big"] if len(main_text) <= 13 else fonts["med"]
        tb = draw.textbbox((0, 0), main_text, font=fnt, stroke_width=10)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]

        box_cx = W // 2
        box_cy = 395 - slam_drop
        bw = min(W - 64, tw + 88)
        bh = th + 44
        x0, x1 = box_cx - bw // 2, box_cx + bw // 2
        y0, y1 = box_cy - bh // 2, box_cy + bh // 2
        skew = 18

        draw.polygon(
            [(x0 + skew + 8, y0 + 10), (x1 + skew + 8, y0 + 10), (x1 - skew + 8, y1 + 10), (x0 - skew + 8, y1 + 10)],
            fill=(0, 0, 0, 175),
        )
        draw.polygon(
            [(x0 + skew, y0), (x1 + skew, y0), (x1 - skew, y1), (x0 - skew, y1)],
            fill=(10, 12, 24, 234),
        )
        draw.polygon([(x0 + skew, y0), (x0 + skew + 18, y0), (x0 - skew + 18, y1), (x0 - skew, y1)], fill=(*accent_rgb, 255))
        draw.polygon([(x1 + skew - 14, y0), (x1 + skew, y0), (x1 - skew, y1), (x1 - skew - 14, y1)], fill=(*accent_rgb, 255))
        draw.line([(x0 + skew, y0), (x1 + skew, y0)], fill=(*accent_rgb, 245), width=5)
        draw.line([(x0 - skew, y1), (x1 - skew, y1)], fill=(*accent_rgb, 245), width=5)

        if tag_text:
            ttb = draw.textbbox((0, 0), tag_text, font=fonts["tag"])
            ttw, tth = ttb[2] - ttb[0], ttb[3] - ttb[1]
            tx0, ty0 = x0 + 24, y0 - tth - 16
            draw.polygon(
                [(tx0 + 8, ty0), (tx0 + ttw + 38, ty0), (tx0 + ttw + 28, ty0 + tth + 14), (tx0 - 2, ty0 + tth + 14)],
                fill=(*accent_rgb, 255),
            )
            draw.text((tx0 + 14, ty0 + 3), tag_text, font=fonts["tag"], fill=(10, 12, 24, 255))

        draw.text(
            (box_cx - tw // 2, box_cy - th // 2 - 4),
            main_text,
            font=fnt,
            fill=(255, 255, 255, 255),
            stroke_width=10,
            stroke_fill=(8, 10, 18, 255),
        )

        if sub_text:
            stb = draw.textbbox((0, 0), sub_text, font=fonts["sub"], stroke_width=8)
            stw = stb[2] - stb[0]
            draw.text(
                ((W - stw) // 2, y1 + 14),
                sub_text,
                font=fonts["sub"],
                fill=(*accent_rgb, 255),
                stroke_width=8,
                stroke_fill=(8, 10, 18, 255),
            )

    # =====================================================================
    # PERMANENT HIGH-CONVERTING END CTAs (17.2s..23.5s) OVER LIVE GAMEPLAY!
    # Safe Zone: Centered, Y=1060..1490 (never hidden by YouTube Shorts UI!)
    # =====================================================================
    if t >= 17.20:
        sub_age = t - 17.20
        pop_y = int(40 * math.exp(-sub_age * 14.0))
        pulse_scale = 1.0 + 0.025 * math.sin(t * 11.0)
        card_w = int(860 * pulse_scale)
        cx = W // 2
        cy1 = 1155 + pop_y
        x0, x1 = cx - card_w // 2, cx + card_w // 2
        y0, y1 = cy1 - 92, cy1 + 92

        # Glowing YouTube Red Subscribe Card
        draw_rounded_box(draw, (x0 + 8, y0 + 10, x1 + 8, y1 + 10), 28, fill=(0, 0, 0, 185))
        draw_rounded_box(draw, (x0, y0, x1, y1), 28, fill=(220, 24, 48, 246), outline=(255, 212, 0, 255), width=6)

        line1 = "100日後にバズるゲームを見たい人"
        line2 = "▶ チャンネル登録よろしく！"
        b1 = draw.textbbox((0, 0), line1, font=fonts["cta_sm"])
        b2 = draw.textbbox((0, 0), line2, font=fonts["cta_lg"], stroke_width=6)
        draw.text((cx - (b1[2] - b1[0]) // 2, y0 + 22), line1, font=fonts["cta_sm"], fill=(255, 240, 150, 255))
        draw.text(
            (cx - (b2[2] - b2[0]) // 2, y0 + 78),
            line2,
            font=fonts["cta_lg"],
            fill=(255, 255, 255, 255),
            stroke_width=6,
            stroke_fill=(90, 0, 16, 255),
        )

    if t >= 20.15:
        com_age = t - 20.15
        pop_y2 = int(46 * math.exp(-com_age * 14.0))
        cx = W // 2
        cy2 = 1385 + pop_y2
        x0, x1 = cx - 430, cx + 430
        y0, y1 = cy2 - 84, cy2 + 84

        # Glowing Cyan/Gold Comment Request Card
        draw_rounded_box(draw, (x0 + 8, y0 + 10, x1 + 8, y1 + 10), 26, fill=(0, 0, 0, 185))
        draw_rounded_box(draw, (x0, y0, x1, y1), 26, fill=(10, 18, 36, 244), outline=(0, 229, 255, 255), width=6)

        c1 = "作って欲しいゲームがあったら"
        c2 = "コメント欄によろしく！！"
        cb1 = draw.textbbox((0, 0), c1, font=fonts["cta_sm"])
        cb2 = draw.textbbox((0, 0), c2, font=fonts["cta_lg"], stroke_width=5)
        draw.text((cx - (cb1[2] - cb1[0]) // 2, y0 + 18), c1, font=fonts["cta_sm"], fill=(0, 229, 255, 255))
        draw.text(
            (cx - (cb2[2] - cb2[0]) // 2, y0 + 72),
            c2,
            font=fonts["cta_lg"],
            fill=(255, 212, 0, 255),
            stroke_width=5,
            stroke_fill=(6, 10, 20, 255),
        )

    # Bottom Viral Beat Progress Bar
    prog = min(1.0, t / total_dur)
    draw.rectangle((0, H - 10, W, H), fill=(15, 23, 42, 210))
    draw.rectangle((0, H - 10, int(W * prog), H), fill=(*accent_rgb, 255))

    return Image.alpha_composite(img, overlay).convert("RGB")


def render_note_thumbnail(browser: str, game_png_path: Path, out_png: Path):
    b64 = base64.b64encode(game_png_path.read_bytes()).decode("ascii")
    html = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  width:1280px;height:670px;overflow:hidden;
  background: radial-gradient(circle at 75% 45%, #881337 0%, #1e1b4b 44%, #050712 100%);
  font-family:'Noto Sans JP','Hiragino Kaku Gothic ProN',sans-serif;
  color:#ffffff;display:flex;align-items:center;justify-content:space-between;
  padding:46px 56px;position:relative;
}}
body::before{{
  content:'';position:absolute;inset:16px;
  border:2.5px solid rgba(0,229,255,0.42);border-radius:22px;pointer-events:none;
}}
.left{{width:725px;z-index:2;}}
.badge{{
  display:inline-block;padding:8px 22px;border-radius:999px;
  background:linear-gradient(90deg,#00e5ff,#ff2a6d);color:#ffffff;
  font-weight:900;font-size:22px;letter-spacing:0.05em;margin-bottom:18px;
  box-shadow:0 8px 24px rgba(255,42,109,0.45);
}}
h1{{
  font-size:72px;line-height:1.02;font-weight:900;color:#ffffff;margin-bottom:16px;
  text-shadow:0 8px 24px rgba(0,0,0,0.75);
}}
h1 span{{color:#00e5ff;}}
.sub{{font-size:31px;font-weight:900;color:#e2e8f0;line-height:1.38;margin-bottom:26px;}}
.sub strong{{color:#ffd400;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;}}
.chip{{
  padding:10px 18px;border-radius:12px;background:rgba(15,23,42,0.88);
  border:2px solid rgba(255,212,0,0.68);font-size:19px;font-weight:800;color:#ffffff;
}}
.right{{
  position:relative;width:400px;height:590px;z-index:2;
  display:flex;align-items:center;justify-content:center;
}}
.phone{{
  width:326px;height:580px;border-radius:28px;overflow:hidden;
  border:4px solid #ffd400;
  box-shadow:0 24px 60px rgba(0,0,0,0.75), 0 0 46px rgba(255,42,109,0.6);
  transform:rotate(2deg);
}}
.phone img{{width:100%;height:100%;object-fit:cover;display:block;}}
.stamp{{
  position:absolute;bottom:28px;left:-46px;transform:rotate(-8deg);
  padding:10px 24px;border-radius:14px;background:linear-gradient(90deg,#ff2a6d,#ffd400);
  border:3.5px solid #ffffff;color:#080a12;font-weight:900;font-size:27px;
  box-shadow:0 12px 28px rgba(0,0,0,0.6);
}}
</style></head><body>
  <div class="left">
    <div class="badge">GAME DAY 07 ｜ Three.js 一人称3D斬撃アクション</div>
    <h1>PHANTOM <span>RUSH 3D</span></h1>
    <div class="sub"><strong>音速パルクール斬撃</strong>×<strong>異界ボス決戦</strong><br>弾き返し→超連打→一閃両断で能力覚醒!!</div>
    <div class="chips">
      <div class="chip">⛩ 紅蓮の異界BOSS戦</div>
      <div class="chip">⚔️ JUST SLASH＆真っ二つ</div>
      <div class="chip">🃏 3択MOD能力覚醒</div>
    </div>
  </div>
  <div class="right">
    <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
    <div class="stamp">一閃両断!!</div>
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
    dbg_port = 9287
    profile_dir = tempfile.mkdtemp(prefix="cdp_day07_")
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
    total_dur = 23.5
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

        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day07-phantom-rush-3d/index.html?shorts=1"})
        for _ in range(60):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true;")

        fonts = {
            "tag": ImageFont.truetype(FONT_SANS, 28),
            "big": ImageFont.truetype(FONT_SANS, 60),
            "med": ImageFont.truetype(FONT_SANS, 46),
            "sub": ImageFont.truetype(FONT_SANS, 36),
            "cta_sm": ImageFont.truetype(FONT_SANS, 34),
            "cta_lg": ImageFont.truetype(FONT_SANS, 54),
        }

        # 23.5s Kinetic Caption Script (zero tofu boxes!)
        caption_plan = [
            (0.00, 1.85, "100日後にバズるゲーム 7日目", "一人称3D斬撃アクション!!", "弾き返し→連打→一閃両断!!", (255, 212, 0)),
            (1.85, 5.80, "音速ネオンパルクール", "JUST SLASHで真っ二つ!!", "引きつけて斬るほど脳汁MAX!!", (0, 229, 255)),
            (5.80, 9.45, "弾パリィ＆OVERDRIVE", "敵の弾も刀で跳ね返せ!!", "ゲージ満タンで無敵爆走モード!!", (0, 255, 157)),
            (9.45, 11.90, "異界ステージへワープ!!", "紅蓮の機神・KUROGANE!!", "紅蓮斬波をジャンプで見切れ!!", (255, 42, 109)),
            (11.90, 15.35, "CLASH!! GUARD BREAK!!", "超連打からの一閃両断!!", "SLASH連打で一気に斬り刻め!!", (255, 212, 0)),
            (15.35, 17.35, "ボス撃破報酬", "3択サイバーMOD覚醒!!", "新能力を装備して都市へ帰還!!", (0, 229, 255)),
            (17.35, 20.15, "毎日1本ガチ開発中!!", "100日後にバズるゲーム!!", "無料で今すぐ遊べるよ ▼", (255, 42, 109)),
            (20.15, 23.60, "ゲーム案リクエスト募集!!", "次はどんなゲーム作る？", "コメント欄で教えてね ▼", (0, 229, 255)),
        ]

        impact_peaks = [0.24, 0.55, 1.05, 1.85, 4.10, 6.90, 9.45, 12.10, 12.60, 13.15, 14.00, 17.35]
        thumb_src_path = OUT_DIR / "_thumb_src.png"

        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            cdp.eval_js(f"window.__stepFrame({dt_sec:.6f});")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 93})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            # Capture crisp mid-Clash Boss Arena frame (12.17s -> frame 292) for note thumbnail
            if f_idx == 292:
                raw_img.resize((1080, 1920), Image.Resampling.LANCZOS).save(thumb_src_path)

            tag, main_txt, sub_txt, accent, s0 = "", "", "", (0, 229, 255), t
            for seg in caption_plan:
                if seg[0] <= t < seg[1]:
                    s0, _, tag, main_txt, sub_txt, accent = seg
                    break

            pulse = 0.0
            for pt in impact_peaks:
                if 0.0 <= (t - pt) < 0.22:
                    pulse = max(pulse, math.exp(-(t - pt) * 14.0))

            frame = draw_shorts_overlay(
                raw_img, t, total_dur, tag, main_txt, sub_txt, accent, s0, pulse, fonts
            )
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=92)
            if f_idx % 120 == 0:
                print(f"  Rendered frame {f_idx}/{total_frames} ({t:.1f}s)")

        events_json = cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]"
        events = json.loads(events_json)
        cdp.close()

        wav_path = OUT_DIR / "audio.wav"
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day07_short.mp4"
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

        print(f"Generated Day 07 Short: {out_mp4} ({out_mp4.stat().st_size // 1024} KB)")
        print(f"Recorded events: {len(events)}")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        shutil.rmtree(profile_dir, ignore_errors=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
