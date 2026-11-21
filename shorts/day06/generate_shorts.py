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


# High-retention punchy Japanese narration timed around beats & KO impacts
NARRATION_CUES = [
    (0.02, "零点一秒の見切りから、一撃カウンターKO！"),
    (1.90, "ゼロフレーム遅延スワイプの一人称3Dボクシング！"),
    (4.65, "ただし、しゃがみ連打はダック狩りアッパーで即死！"),
    (7.45, "三つの難度、全十五人の強敵をなぎ倒せ！"),
    (10.50, "三連見切りからの必殺アッパー！ベリーハード制覇できる？"),
]


def synthesize_tts_line(text: str, out_wav: Path, sr: int = 44100) -> bool:
    tmp_mp3 = out_wav.with_suffix(".mp3")
    if not os.environ.get("REQUESTS_CA_BUNDLE") and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    # Try edge-tts energetic male voice (KeitaNeural) first for fresh Fight-Night taste!
    try:
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(text, voice="ja-JP-KeitaNeural", rate="+22%", pitch="+4Hz")
            await asyncio.wait_for(comm.save(str(tmp_mp3)), timeout=8.0)

        asyncio.run(_gen())
        if tmp_mp3.exists() and tmp_mp3.stat().st_size > 500:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(tmp_mp3),
                    "-af", "acompressor=threshold=-16dB:ratio=3:attack=5:release=60,highpass=f=90",
                    "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", str(out_wav),
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            tmp_mp3.unlink(missing_ok=True)
            return True
    except Exception as exc:
        print(f"edge-tts fallback to gTTS for '{text}': {exc}")
        tmp_mp3.unlink(missing_ok=True)

    # Fallback: gTTS with fast punchy pitch shift
    try:
        from gtts import gTTS

        gTTS(text=text, lang="ja").save(str(tmp_mp3))
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(tmp_mp3),
                "-af", "atempo=1.32,asetrate=44100*0.92,aresample=44100",
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
    # 144 BPM DARK PHONK / FIGHT-NIGHT TRAP BOXING BEAT (NEW AUDIO TASTE!)
    # =====================================================================
    bpm = 144.0
    step_dur = 60.0 / bpm / 4.0  # 16th-note grid for crisp trap hats & cowbell!
    # Dark aggressive Phonk minor bassline (E1 -> G1 -> A1 -> F#1)
    bass_notes = [41.20, 41.20, 49.00, 41.20, 55.00, 55.00, 46.25, 49.00]
    # Iconic viral Phonk cowbell riff (E5, G5, B5, A5, G5, F#5, E5, B4)
    cowbell_riff = [659.25, 0, 783.99, 0, 987.77, 0, 880.00, 783.99,
                    659.25, 0, 739.99, 0, 659.25, 493.88, 659.25, 0]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        t_step = i * step_dur
        s0 = int(t_step * sr)
        s_len = min(int(step_dur * 1.45 * sr), n_samples - s0)
        if s_len <= 0:
            break
        lt = np.arange(s_len, dtype=np.float32) / sr

        # Heavy Distorted 808 Sub-Kick on beats 0, 6, 8, 14
        step16 = i % 16
        if step16 in (0, 6, 8, 14):
            bf = bass_notes[(i // 8) % len(bass_notes)]
            pitch_env = bf + 95.0 * np.exp(-lt * 34.0)
            sub = np.tanh(np.sin(2.0 * math.pi * np.cumsum(pitch_env) / sr) * 2.4) * np.exp(-lt * 6.5) * 0.25
            bgm[s0 : s0 + s_len] += sub

        # Punchy Trap Snare on 4 and 12
        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 404)
            sn_len = min(int(0.11 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            snare = (
                rng.uniform(-1.0, 1.0, sn_len).astype(np.float32) * np.exp(-slt * 34.0) * 0.17
                + np.sin(2.0 * math.pi * (210.0 * np.exp(-slt * 22.0) + 120.0) * slt) * np.exp(-slt * 28.0) * 0.14
            )
            bgm[s0 : s0 + sn_len] += snare

        # Crisp Trap Hi-Hats (with 32nd-note rolls before drops!)
        if step16 % 2 == 0 or t_step > 7.35:
            rng = np.random.default_rng(seed=i + 808)
            h_len = min(int(0.032 * sr), n_samples - s0)
            hlt = np.arange(h_len, dtype=np.float32) / sr
            hat = rng.uniform(-1.0, 1.0, h_len).astype(np.float32) * np.exp(-hlt * 110.0) * 0.048
            bgm[s0 : s0 + h_len] += hat

        # Iconic Phonk Cowbell Hook (kicks in hard right after 0.40s cold-open impact!)
        cf = cowbell_riff[step16]
        if cf > 0 and t_step >= 0.40:
            c_len = min(int(0.14 * sr), n_samples - s0)
            clt = np.arange(c_len, dtype=np.float32) / sr
            # Classic 808 cowbell uses two detuned square-ish partials (ratio ~1.50)
            cb = (
                np.sign(np.sin(2.0 * math.pi * cf * clt)) * 0.55
                + np.sign(np.sin(2.0 * math.pi * (cf * 1.498) * clt)) * 0.45
            ) * np.exp(-clt * 22.0) * (0.095 if t_step > 7.35 else 0.070)
            bgm[s0 : s0 + c_len] += cb

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
    # Instant attention-grabbing 808 impact slam at frame 0
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
            # Crimson siren rise for Duck-Hunting Uppercut!
            e_len = min(int(0.32 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(320.0, 1180.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 5.0) * 0.24

        elif kind == "just_slip":
            # Time-slow bass drop + electric crystalline flash!
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
            # MONUMENTAL JAW-SHATTERING ULTRA KO BOOM + BELL + CROWD ROAR!
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
            # Crisp vinyl/glitch riser swipe on fast cut!
            e_len = min(int(0.10 * sr), n_samples - idx0)
            lt = np.arange(e_len, dtype=np.float32) / sr
            freq = np.linspace(1200.0, 260.0, e_len, dtype=np.float32)
            sfx[idx0 : idx0 + e_len] += np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-lt * 24.0) * 0.20

    # Mix Japanese Narration with clean sidechain BGM ducking
    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day06_"))
    try:
        for idx, (cue_t, line_txt) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, sr=sr):
                arr = load_wav_mono(cue_wav)
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.82
                s0 = int(cue_t * sr)
                s_len = min(len(arr), n_samples - s0)
                if s_len > 0:
                    voice[s0 : s0 + s_len] += arr[:s_len]
                    duck[s0 : s0 + s_len] = np.minimum(duck[s0 : s0 + s_len], 0.30)
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    mixed = bgm * duck + sfx * 0.88 + voice
    mixed = np.tanh(mixed * 1.20) * 0.90
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
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.LANCZOS)

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

    # Bottom Viral Beat-Progress Bar (sleek 8px crimson/gold energy bar at very bottom)
    prog = min(1.0, t / 14.5)
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
    <div class="badge">GAME DAY 06 ｜ 一人称3Dボクシング</div>
    <h1>COUNTER <span>KO 3D</span></h1>
    <div class="sub"><strong>0.1秒見切り</strong>×<strong>ダック狩りアッパー</strong><br>0フレーム遅延スワイプで全15強敵を粉砕！</div>
    <div class="chips">
      <div class="chip">⚡ 0フレーム遅延スワイプ</div>
      <div class="chip">⚠ ダック狩りアッパー</div>
      <div class="chip">🥊 3難度×全15強敵</div>
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
    dbg_port = 9286
    profile_dir = tempfile.mkdtemp(prefix="cdp_day06_")
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
    total_dur = 14.5
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

        # New Fight-Night PPV Caption Script (zero tofu boxes!)
        # (t0, t1, kicker_tag, main_headline, sub_punchline, accent_rgb)
        caption_plan = [
            (0.00, 1.15, "0.1秒見切り", "一撃カウンターKO!!", "一人称3Dボクシング爆誕!!", (253, 224, 71)),
            (1.15, 2.75, "0フレーム遅延", "指の動きに即反応!!", "スワイプ見切り → カウンター連打!!", (56, 189, 248)),
            (2.75, 4.10, "厳格タイミング", "早すぎ回避は即被弾!!", "ギリギリで避けろ!!", (56, 189, 248)),
            (4.10, 5.10, "駆け引き", "フックは下ダックで回避!", "しかし次の瞬間…", (163, 230, 53)),
            (5.10, 7.40, "ダック狩りアッパー", "しゃがみ連打は即死!!", "赤アッパーは横へ見切れ!!", (244, 63, 94)),
            (7.40, 9.45, "全3難度 × 5戦", "全15人の強敵に挑め!!", "EASY / HARD / VERY HARD", (250, 204, 21)),
            (9.45, 11.60, "裏世界最強 15人目", "3連ラッシュを全見切り!!", "左!! 右!! アッパー回避!!", (56, 189, 248)),
            (11.60, 14.55, "ULTRA COUNTER KO", "ベリーハード制覇できる？", "プロフィール/リンクから無料プレイ ▼", (253, 224, 71)),
        ]

        # Peaks where chromatic RGB split + manga impact lines fire!
        impact_peaks = [0.00, 0.14, 0.42, 1.15, 1.60, 2.38, 4.10, 5.60, 6.60, 7.40, 8.40, 9.45, 11.24, 11.98]

        thumb_src_path = OUT_DIR / "_thumb_src.png"

        for f_idx in range(total_frames):
            t = f_idx * dt_sec
            cdp.eval_js("window.__stepFrame(1/60);")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 95})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            # Capture crisp mid-impact ULTRA COUNTER KO frame (banner cleanly below face!)
            if f_idx == 28:
                raw_img.save(thumb_src_path)

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
