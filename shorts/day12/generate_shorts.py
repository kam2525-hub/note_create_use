#!/usr/bin/env python3
"""
Day 12 YouTube Shorts (1080x1920, 24fps, 23.0s) — WARIBASHI MASTER 3D
Follows shorts/SHORTS_RULES.md:
- 0.00-1.80s: Cold open climax (fast dramatic split + splinters + tension!)
- 1.80-5.80s: Moving Green Tension Gauge vs Red-Zone Instant Snap ("ポキッ!! 折損即死!!")
- 5.80-10.50s: 3D Knots & Grain Drift ("ほぼ爪楊枝 Dランク") vs Counter-Steer ("⚡ JUST節見切り!!")
- 10.50-15.00s: 5 Brutal Tiers ("初級〜神域【極】") & 50.00 : 50.00 Golden Ratio Challenge
- 15.00-19.00s: Mandatory Subscribe CTA over continuous 3D splitting
- 19.00-23.00s: Mandatory Comment Request CTA over continuous 3D splitting
- Outputs:
    shorts/day12/output/day12_short.mp4
    shorts/day12/output/note_thumbnail.png
    shorts/day12/output/youtube_metadata.txt
"""

import argparse
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

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "shorts" / "day12" / "output"
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


class SimpleCDP:
    def __init__(self, ws_url: str):
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

    def _send(self, text: str):
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
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _recv_exact(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            c = self.sock.recv(n - len(out))
            if not c:
                raise ConnectionError("WebSocket closed")
            out.extend(c)
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
            if b2 & 0x80:
                mask = self._recv_exact(4)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._recv_exact(ln)))
            else:
                data = self._recv_exact(ln)
            if op == 8:
                raise ConnectionError("WebSocket closed")
            if op == 1:
                return data.decode("utf-8", errors="replace")

    def call(self, method: str, params=None):
        self.msg_id += 1
        mid = self.msg_id
        self._send(json.dumps({"id": mid, "method": method, "params": params or {}}))
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


NARRATION_CUES = [
    (0.05, "ただ割り箸を綺麗に割るだけの一人称3Dゲーム作ったら、激ムズすぎた！", "+19%", "+3Hz"),
    (2.35, "緑のゲージを外れて赤ゾーンに入ると、ポキッと折れて即死！", "+17%", "+2Hz"),
    (5.90, "しかも3Dの節に逆ステアを合わせないと、一瞬でほぼ爪楊枝になります！", "+17%", "+2Hz"),
    (10.55, "難易度は5段階！誤差0.15%以内の神域50対50を目指せ！", "+17%", "+3Hz"),
    (15.05, "100日後にバズるゲームを見たい人は、チャンネル登録よろしく！", "+15%", "+2Hz"),
    (19.05, "作ってほしいゲームがあったら、コメント欄で教えてね！", "+16%", "+2Hz"),
]


def synthesize_tts_line(text: str, out_wav: Path, rate: str = "+17%", pitch: str = "+2Hz", sr: int = 44100) -> bool:
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
                "highpass=f=85,"
                "equalizer=f=200:t=q:w=1.2:g=2.0,"
                "equalizer=f=3200:t=q:w=1.4:g=2.4,"
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


def generate_audio(total_dur: float, events: list, wav_path: Path):
    import numpy as np

    sr = 44100
    n_samples = int(total_dur * sr)
    bgm_l = np.zeros(n_samples, dtype=np.float32)
    bgm_r = np.zeros(n_samples, dtype=np.float32)
    sfx_l = np.zeros(n_samples, dtype=np.float32)
    sfx_r = np.zeros(n_samples, dtype=np.float32)
    voice = np.zeros(n_samples, dtype=np.float32)

    def add_stereo(bl, br, idx, sig, pan=0.0, gain=1.0):
        if idx < 0 or idx >= len(bl):
            return
        ln = min(len(sig), len(bl) - idx)
        if ln <= 0:
            return
        ang = (pan + 1.0) * 0.25 * math.pi
        bl[idx : idx + ln] += sig[:ln] * math.cos(ang) * gain
        br[idx : idx + ln] += sig[:ln] * math.sin(ang) * gain

    # 138 BPM Fast Electro-Dojo Synth BGM
    bpm = 138.0
    step_dur = 60.0 / bpm / 4.0
    bar_dur = step_dur * 16.0
    chords = [
        (110.00, [220.00, 261.63, 329.63, 440.00]),
        (87.31,  [174.61, 220.00, 261.63, 349.23]),
        (130.81, [261.63, 329.63, 392.00, 523.25]),
        (98.00,  [196.00, 246.94, 293.66, 392.00]),
    ]
    arp_idx = [0, 2, 1, 3, 2, 3, 0, 2, 1, 3, 2, 0, 3, 2, 1, 3]

    num_steps = int(total_dur / step_dur)
    for i in range(num_steps):
        s0 = int(i * step_dur * sr)
        if s0 >= n_samples:
            break
        step16 = i % 16
        bar = i // 16
        bass_f, tones = chords[bar % len(chords)]

        if step16 in (0, 4, 8, 12) or (bar % 2 == 1 and step16 == 14):
            k_len = min(int(0.15 * sr), n_samples - s0)
            lt = np.arange(k_len, dtype=np.float32) / sr
            kf = 52.0 + 130.0 * np.exp(-lt * 36.0)
            kick = np.tanh(np.sin(2.0 * math.pi * np.cumsum(kf) / sr) * 2.4) * np.exp(-lt * 13.0)
            add_stereo(bgm_l, bgm_r, s0, kick, pan=0.0, gain=0.22)

        if step16 in (4, 12):
            rng = np.random.default_rng(seed=i + 111)
            sn_len = min(int(0.09 * sr), n_samples - s0)
            slt = np.arange(sn_len, dtype=np.float32) / sr
            bright = np.diff(rng.uniform(-1.0, 1.0, sn_len).astype(np.float32), prepend=0.0)
            add_stereo(bgm_l, bgm_r, s0, bright * np.exp(-slt * 30.0) * 0.65, pan=0.05 if step16 == 4 else -0.05, gain=0.13)

        if step16 % 2 == 0:
            blen = min(int(step_dur * 1.15 * sr), n_samples - s0)
            blt = np.arange(blen, dtype=np.float32) / sr
            bf = bass_f * (2.0 if step16 in (2, 6, 10, 14) else 1.0)
            bs = np.tanh(np.sin(2.0 * math.pi * bf * blt) * 1.5) * np.exp(-blt * 8.0)
            add_stereo(bgm_l, bgm_r, s0, bs, pan=0.0, gain=0.13)

            plen = min(int(0.12 * sr), n_samples - s0)
            plt = np.arange(plen, dtype=np.float32) / sr
            pf = tones[arp_idx[step16]] * 2.0
            pluck = np.sin(2.0 * math.pi * pf * plt) * np.exp(-plt * 22.0)
            add_stereo(bgm_l, bgm_r, s0, pluck, pan=-0.35 if (step16 // 2) % 2 == 0 else 0.35, gain=0.08)

    def add_crack(t_sec: float, gain: float = 0.25):
        idx = int(t_sec * sr)
        clen = int(0.05 * sr)
        ct = np.arange(clen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 17)
        sig = rng.uniform(-1.0, 1.0, clen).astype(np.float32) * np.exp(-ct * 75.0)
        add_stereo(sfx_l, sfx_r, idx, sig, pan=0.0, gain=gain)

    def add_snap(t_sec: float, broken: bool = False):
        idx = int(t_sec * sr)
        slen = int(0.32 * sr)
        st = np.arange(slen, dtype=np.float32) / sr
        rng = np.random.default_rng(seed=int(t_sec * 1000) + 55)
        crack = rng.uniform(-1.0, 1.0, slen).astype(np.float32) * np.exp(-st * 24.0) * 0.55
        freq = 120.0 if broken else 480.0
        thud = np.sin(2.0 * math.pi * np.cumsum(freq * np.exp(-st * 14.0) + 50.0) / sr) * np.exp(-st * 10.0) * 0.5
        add_stereo(sfx_l, sfx_r, idx, crack + thud, pan=0.0, gain=0.85)

    def add_ping(t_sec: float, f1: float = 1046.5, f2: float = 1567.98, gain: float = 0.38):
        idx = int(t_sec * sr)
        blen = int(0.36 * sr)
        bt = np.arange(blen, dtype=np.float32) / sr
        c1 = np.sin(2.0 * math.pi * f1 * bt) * np.exp(-bt * 12.0)
        d2 = int(0.08 * sr)
        c2 = np.zeros_like(c1)
        if d2 < blen:
            bt2 = np.arange(blen - d2, dtype=np.float32) / sr
            c2[d2:] = np.sin(2.0 * math.pi * f2 * bt2) * np.exp(-bt2 * 10.0)
        add_stereo(sfx_l, sfx_r, idx, c1 + c2, pan=0.0, gain=gain)

    last_crack_t = -1.0
    for ev in events:
        t0 = float(ev.get("t", 0.0))
        kind = ev.get("type")
        if kind == "crack":
            if t0 - last_crack_t >= 0.045:
                add_crack(t0, gain=0.22)
                last_crack_t = t0
        elif kind == "counter":
            add_ping(t0, f1=987.77, f2=1975.53, gain=0.42)
        elif kind == "snap_broken":
            add_snap(t0, broken=True)
        elif kind in ("snap_god", "snap_done"):
            add_snap(t0, broken=False)
            if kind == "snap_god":
                add_ping(t0 + 0.06, f1=1046.5, f2=1567.98, gain=0.40)

    add_ping(16.45, f1=1046.5, f2=1567.98, gain=0.36)  # Subscribe click bell
    add_crack(19.05, gain=0.25)

    duck = np.ones(n_samples, dtype=np.float32)
    tts_tmp = Path(tempfile.mkdtemp(prefix="tts_day12_"))
    try:
        prev_end_s = 0
        ramp_n = int(0.10 * sr)
        for idx, (cue_t, line_txt, rate, pitch) in enumerate(NARRATION_CUES):
            cue_wav = tts_tmp / f"cue_{idx}.wav"
            if synthesize_tts_line(line_txt, cue_wav, rate=rate, pitch=pitch, sr=sr):
                with wave.open(str(cue_wav), "rb") as wf:
                    arr = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                peak = float(np.max(np.abs(arr))) if len(arr) else 0.0
                if peak > 0.01:
                    arr = (arr / peak) * 0.92
                s0 = max(int(cue_t * sr), prev_end_s + int(0.05 * sr))
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
    finally:
        shutil.rmtree(tts_tmp, ignore_errors=True)

    mix_l = np.tanh((bgm_l * duck + sfx_l * 0.88 + voice * 0.96) * 1.12) * 0.92
    mix_r = np.tanh((bgm_r * duck + sfx_r * 0.88 + voice * 0.96) * 1.12) * 0.92
    stereo = np.empty(n_samples * 2, dtype=np.int16)
    stereo[0::2] = np.clip(mix_l * 32767.0, -32767, 32767).astype(np.int16)
    stereo[1::2] = np.clip(mix_r * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def draw_shorts_overlay(frame_img, t, total_dur, section_pill, accent_rgb, sub_lines, seg_start, impact_pulse, trans_flash, fonts):
    from PIL import Image, ImageChops, ImageDraw

    if frame_img.size != (1080, 1920):
        frame_img = frame_img.resize((1080, 1920), Image.Resampling.BILINEAR)

    if impact_pulse > 0.16:
        sh = int(12 * impact_pulse)
        r, g, b = frame_img.split()
        frame_img = Image.merge("RGB", (ImageChops.offset(r, sh, 0), g, ImageChops.offset(b, -sh, 0)))

    img = frame_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size

    def rbox(xy, rad, fill, outline=None, width=0):
        draw.rounded_rectangle(xy, radius=rad, fill=fill, outline=outline, width=width)

    def draw_rich_line(cx, y, tokens, font, outer=12, inner=5):
        widths = [draw.textlength(tx, font=font) for tx, _ in tokens]
        cur_x = cx - sum(widths) / 2.0
        for pass_i in range(3):
            px = cur_x
            for (tx, col), w in zip(tokens, widths):
                if pass_i == 0:
                    draw.text((px + 4, y + 6), tx, font=font, fill=(0, 0, 0, 210), stroke_width=outer + 2, stroke_fill=(0, 0, 0, 200))
                elif pass_i == 1:
                    draw.text((px, y), tx, font=font, fill=(8, 12, 22, 255), stroke_width=outer, stroke_fill=(8, 12, 22, 255))
                else:
                    draw.text((px, y), tx, font=font, fill=(*col, 255), stroke_width=inner, stroke_fill=(10, 16, 28, 255))
                px += w

    for gy in range(0, 420, 14):
        alpha = int(140 * (gy / 420.0) ** 1.4)
        draw.rectangle((0, H - 420 + gy, W, H - 420 + gy + 14), fill=(5, 9, 18, alpha))

    if impact_pulse > 0.22:
        cx, cy = W // 2, int(H * 0.44)
        for i in range(28):
            ang = (i / 28.0) * math.tau + t * 5.2
            draw.line(
                (cx + int(math.cos(ang) * 320), cy + int(math.sin(ang) * 320), cx + int(math.cos(ang) * 1120), cy + int(math.sin(ang) * 1120)),
                fill=(*accent_rgb, int(175 * impact_pulse)),
                width=7 if i % 2 == 0 else 3,
            )

    # Top Header Bar
    hy0, hy1 = 56, 120
    rbox((32, hy0, W - 32, hy1), 16, fill=(7, 11, 20, 224), outline=(190, 242, 100, 145), width=3)
    draw.polygon([(40, hy0 + 7), (195, hy0 + 7), (180, hy1 - 7), (40, hy1 - 7)], fill=(190, 242, 100, 255))
    draw.text((54, hy0 + 13), "DAY 12", font=fonts["chip_b"], fill=(7, 11, 20, 255))
    draw.text((208, hy0 + 14), "WARIBASHI MASTER 3D // 極限割り箸", font=fonts["chip"], fill=(242, 246, 255, 255))

    if section_pill:
        sw = int(draw.textlength(section_pill, font=fonts["chip_sm"])) + 40
        draw.polygon([(36, 132), (36 + sw, 132), (36 + sw - 12, 174), (36, 174)], fill=(*accent_rgb, 240))
        draw.text((50, 137), section_pill, font=fonts["chip_sm"], fill=(7, 11, 20, 255))

    # 0.00-1.80s Cold Open Hook
    if t < 1.80:
        bounce = int(30 * math.exp(-t * 16.0))
        ry = 246 - bounce
        r_txt, r_col = ("⚡ ただ割り箸を割るだけなのに…", (190, 242, 100)) if t < 0.85 else ("👑 50.00 : 50.00 が難しすぎる!!", (250, 204, 21))
        rw = int(draw.textlength(r_txt, font=fonts["ribbon"])) + 54
        rx0 = (W - rw) // 2
        rbox((rx0, ry, rx0 + rw, ry + 54), 12, fill=(7, 11, 20, 242), outline=(*r_col, 255), width=4)
        draw.text((rx0 + 27, ry + 8), r_txt, font=fonts["ribbon"], fill=(*r_col, 255))
        draw_rich_line(W // 2, ry + 72, [("一人称3D", (190, 242, 100)), ("割り箸ゲーム", (255, 255, 255))], fonts["hook_sm"], outer=14, inner=5)
        draw_rich_line(W // 2, ry + 148, [("激ムズすぎ!!", (250, 204, 21))], fonts["hook"], outer=16, inner=6)

    # 1.80-15.00s Subtitles
    if sub_lines and 1.80 <= t < 15.00:
        age = max(0.0, t - seg_start)
        pop_y = int(20 * math.exp(-age * 18.0))
        base_y = 1435 if len(sub_lines) == 2 else 1490
        for li, line_tokens in enumerate(sub_lines):
            draw_rich_line(W // 2, base_y + li * 80 + pop_y, line_tokens, fonts["sub_yt"], outer=13, inner=5)

    # 15.00-19.00s Mandatory Subscribe CTA
    if 15.00 <= t < 19.00:
        age = t - 15.00
        pop_y = int(42 * math.exp(-age * 14.0))
        clicked = t >= 16.45
        click_age = max(0.0, t - 16.45)
        cx = W // 2
        draw_rich_line(cx, 1085 + pop_y, [("100日後に", (190, 242, 100)), ("バズるゲーム", (255, 255, 255)), ("見たい人は", (255, 255, 255))], fonts["cta_head"], outer=13, inner=5)
        draw_rich_line(cx, 1165 + pop_y, [("チャンネル登録", (255, 72, 92)), ("よろしく!!", (255, 255, 255))], fonts["cta_head_lg"], outer=14, inner=5)

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1285 + pop_y, 1445 + pop_y
        rbox((x0 + 8, y0 + 12, x1 + 8, y1 + 12), 34, fill=(0, 0, 0, 175))
        rbox((x0, y0, x1, y1), 34, fill=(14, 18, 30, 246), outline=(190, 242, 100, 110), width=3)
        av_cx, av_cy = x0 + 82, (y0 + y1) // 2
        draw.ellipse((av_cx - 48, av_cy - 48, av_cx + 48, av_cy + 48), fill=(190, 242, 100, 255), outline=(255, 255, 255, 255), width=4)
        draw.text((av_cx - 32, av_cy - 18), "D12", font=fonts["chip_b"], fill=(7, 11, 20, 255))
        draw.text((x0 + 148, y0 + 36), "100日後にバズるゲーム", font=fonts["yt_name"], fill=(255, 255, 255, 255))
        draw.text((x0 + 148, y0 + 88), "毎日1本ゲーム開発中！", font=fonts["yt_meta"], fill=(160, 174, 198, 255))

        bcx, bcy = x1 - 155, (y0 + y1) // 2
        bw, bh = 265, 84
        bx0, by0, bx1, by1 = bcx - bw // 2, bcy - bh // 2, bcx + bw // 2, bcy + bh // 2
        if clicked:
            if click_age < 0.45:
                rr = int(45 + click_age * 240)
                ra = int(230 * (1.0 - click_age / 0.45))
                draw.ellipse((bcx - rr, bcy - rr, bcx + rr, bcy + rr), outline=(190, 242, 100, ra), width=7)
            rbox((bx0, by0, bx1, by1), 42, fill=(52, 58, 72, 255), outline=(255, 255, 255, 110), width=3)
            tw = draw.textlength("登録済み", font=fonts["yt_btn"])
            draw.text((bcx - tw / 2 - 12, bcy - 20), "登録済み", font=fonts["yt_btn"], fill=(235, 240, 248, 255))
            blx, bly = int(bcx + tw / 2 + 12), bcy
            draw.pieslice((blx - 13, bly - 16, blx + 13, bly + 10), 180, 360, fill=(250, 204, 21, 255))
            draw.rectangle((blx - 13, bly - 3, blx + 13, bly + 9), fill=(250, 204, 21, 255))
            draw.rectangle((blx - 17, bly + 8, blx + 17, bly + 13), fill=(250, 204, 21, 255))
        else:
            rbox((bx0, by0, bx1, by1), 42, fill=(230, 24, 42, 255), outline=(255, 224, 130, 255), width=4)
            tw = draw.textlength("チャンネル登録", font=fonts["yt_btn"])
            draw.text((bcx - tw / 2, bcy - 20), "チャンネル登録", font=fonts["yt_btn"], fill=(255, 255, 255, 255))

        if 15.45 <= t < 17.25:
            prog_c = min(1.0, max(0.0, (t - 15.45) / 0.95))
            ease = 1.0 - (1.0 - prog_c) ** 3
            px = int(bcx + 120 * (1.0 - ease))
            py = int(bcy + 145 * (1.0 - ease) + (8 if clicked and click_age < 0.14 else 0))
            draw.polygon([(px, py), (px, py + 46), (px + 13, py + 34), (px + 25, py + 50), (px + 33, py + 45), (px + 21, py + 29), (px + 36, py + 29)], fill=(255, 255, 255, 255), outline=(12, 16, 28, 255))

    # 19.00-23.00s Mandatory Comment Request CTA
    if t >= 19.00:
        age = t - 19.00
        pop_y = int(44 * math.exp(-age * 14.0))
        cx = W // 2
        draw_rich_line(cx, 1085 + pop_y, [("作ってほしいゲーム", (34, 211, 238)), ("があったら", (255, 255, 255))], fonts["cta_head"], outer=13, inner=5)
        draw_rich_line(cx, 1165 + pop_y, [("コメント欄", (190, 242, 100)), ("によろしく!!", (255, 255, 255))], fonts["cta_head_lg"], outer=14, inner=5)

        x0, x1 = cx - 430, cx + 430
        y0, y1 = 1288 + pop_y, 1468 + pop_y
        rbox((x0 + 8, y0 + 12, x1 + 8, y1 + 12), 30, fill=(0, 0, 0, 180))
        rbox((x0, y0, x1, y1), 30, fill=(14, 18, 30, 248), outline=(34, 211, 238, 245), width=4)
        draw.text((x0 + 38, y0 + 22), "コメント欄 // GAME REQUEST", font=fonts["yt_meta"], fill=(34, 211, 238, 255))
        rbox((x0 + 34, y0 + 68, x1 - 34, y1 - 24), 18, fill=(24, 32, 50, 255), outline=(255, 255, 255, 45), width=2)
        sample = "「50:50ムズすぎｗ 次は〇〇作って！」"
        chars = min(len(sample), int(age * 16.0) + 1)
        cursor = "|" if int(t * 6.0) % 2 == 0 else ""
        draw.text((x0 + 54, y0 + 90), sample[:chars] + cursor, font=fonts["yt_name"], fill=(245, 248, 255, 255))

    if trans_flash > 0.02:
        draw.rectangle((0, 0, W, H), fill=(255, 255, 255, int(125 * trans_flash)))

    prog = min(1.0, t / total_dur)
    draw.rectangle((0, H - 10, W, H), fill=(15, 23, 42, 200))
    draw.rectangle((0, H - 10, int(W * prog), H), fill=(*accent_rgb, 255))
    return Image.alpha_composite(img, overlay).convert("RGB")


def render_note_thumbnail(browser: str, raw_shot: Path, out_png: Path, day_num: int = 12):
    b64 = base64.b64encode(raw_shot.read_bytes()).decode()
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{width:1280px;height:670px;overflow:hidden;font-family:"Noto Sans JP","Hiragino Sans",sans-serif;
background:radial-gradient(circle at 24% 25%, #16331f 0%, #070b12 62%, #04060a 100%);color:#fff;position:relative;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(190,242,100,0.06) 1px,transparent 1px),linear-gradient(90deg,rgba(190,242,100,0.06) 1px,transparent 1px);background-size:48px 48px;}}
.wrap{{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;width:100%;height:100%;padding:48px 56px;gap:38px;}}
.left{{flex:1;display:flex;flex-direction:column;gap:20px;}}
.day-badge{{display:inline-flex;align-items:center;gap:14px;background:#bef264;color:#070b12;font-weight:900;font-size:34px;padding:10px 26px;border-radius:14px;width:fit-content;box-shadow:0 8px 28px rgba(190,242,100,0.4);letter-spacing:0.06em;}}
h1{{font-size:66px;line-height:1.12;font-weight:900;text-shadow:0 6px 24px rgba(0,0,0,0.65);}}
h1 span{{color:#bef264;}}
.sub{{font-size:27px;line-height:1.45;color:#cbd5e1;font-weight:700;}}
.chips{{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px;}}
.chip{{background:rgba(15,23,42,0.9);border:2px solid rgba(56,189,248,0.6);color:#38bdf8;font-size:21px;font-weight:900;padding:8px 18px;border-radius:999px;}}
.phone{{width:320px;height:570px;border-radius:34px;border:5px solid #bef264;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,0.8),0 0 36px rgba(190,242,100,0.28);flex-shrink:0;transform:rotate(2deg);background:#070b12;}}
.phone img{{width:100%;height:100%;object-fit:cover;}}
.stamp{{position:absolute;z-index:5;bottom:28px;right:356px;background:#ef4444;color:#fff;font-size:28px;font-weight:900;padding:10px 22px;border-radius:12px;transform:rotate(-5deg);border:3px solid #fff;box-shadow:0 10px 24px rgba(0,0,0,0.6);}}
</style></head><body>
<div class="grid"></div>
<div class="wrap">
  <div class="left">
    <div class="day-badge">DAY {day_num} // 100日後にバズるゲーム</div>
    <h1>WARIBASHI<br><span>MASTER 3D</span></h1>
    <div class="sub">ただ「割り箸を50:50に割る」だけなのに<br>鬼ムズすぎて脳汁が出る一人称3D物理!!</div>
    <div class="chips">
      <div class="chip">⚡ JUST節見切り</div>
      <div class="chip">💀 赤ゾーン即死</div>
      <div class="chip">🏆 5段階鬼難度</div>
    </div>
  </div>
  <div class="phone"><img src="data:image/png;base64,{b64}" /></div>
</div>
<div class="stamp">50.00 : 50.00 狙え!!</div>
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
    src = ROOT / "notes" / "day12" / "youtube_metadata.txt"
    if src.exists():
        out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumb-only", action="store_true", help="Only render note_thumbnail.png and youtube_metadata.txt")
    args = parser.parse_args()

    browser = find_browser()
    srv, port = start_static_server(ROOT)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
    profile_dir = tempfile.mkdtemp(prefix="cdp_day12_")
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
            raise RuntimeError("Failed to connect CDP")

        cdp = SimpleCDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", {"width": 540, "height": 960, "deviceScaleFactor": 1.0, "mobile": True})
        cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/games/day12-waribashi-3d/index.html?shorts=1"})

        for _ in range(80):
            time.sleep(0.15)
            if cdp.eval_js("typeof window.__stepFrame === 'function'"):
                break
        else:
            raise RuntimeError("Timed out waiting for __stepFrame")
        cdp.eval_js("window.__manualStep = true;")

        thumb_src = OUT_DIR / "_thumb_src.png"
        if args.thumb_only:
            cdp.eval_js("window.__shortsDemo.startTier(1, true);")
            for _ in range(28):
                cdp.eval_js("window.__shortsDemo.autoCounter(1.0); window.__stepFrame(0.041667);")
            res = cdp.call("Page.captureScreenshot", {"format": "png"})
            thumb_src.write_bytes(base64.b64decode(res["data"]))
            render_note_thumbnail(browser, thumb_src, OUT_DIR / "note_thumbnail.png", day_num=12)
            thumb_src.unlink(missing_ok=True)
            write_youtube_metadata(OUT_DIR / "youtube_metadata.txt")
            print(f"Generated {OUT_DIR / 'note_thumbnail.png'}")
            cdp.close()
            return

        from PIL import Image, ImageFont

        font_sans = find_jp_font()
        fonts = {
            "chip": ImageFont.truetype(font_sans, 25),
            "chip_b": ImageFont.truetype(font_sans, 27),
            "chip_sm": ImageFont.truetype(font_sans, 24),
            "ribbon": ImageFont.truetype(font_sans, 34),
            "hook_sm": ImageFont.truetype(font_sans, 58),
            "hook": ImageFont.truetype(font_sans, 82),
            "sub_yt": ImageFont.truetype(font_sans, 58),
            "cta_head": ImageFont.truetype(font_sans, 52),
            "cta_head_lg": ImageFont.truetype(font_sans, 70),
            "yt_name": ImageFont.truetype(font_sans, 34),
            "yt_meta": ImageFont.truetype(font_sans, 24),
            "yt_btn": ImageFont.truetype(font_sans, 32),
        }

        frames_dir = OUT_DIR / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for old in frames_dir.glob("*.*"):
            old.unlink()

        fps = 24
        dt_sec = 1.0 / fps
        total_dur = 23.0
        total_frames = int(fps * total_dur)

        W_WHITE = (255, 255, 255)
        C_VOLT = (190, 242, 100)
        C_CYAN = (34, 211, 238)
        C_GOLD = (250, 204, 21)
        C_RED = (251, 113, 133)

        caption_plan = [
            (0.00, 1.80, "1ST-SEC CHALLENGE", C_VOLT, []),
            (1.80, 5.80, "赤ゾーン＝折損即死!!", C_RED, [
                [("力みすぎて", W_WHITE), ("赤ゾーン", C_RED), ("に入ると…", W_WHITE)],
                [("ポキッ!!", C_RED), ("真っ二つに折れて即死!!", W_WHITE)],
            ]),
            (5.80, 8.20, "3Dの節(フシ)の罠", C_GOLD, [
                [("3Dの", W_WHITE), ("「節（フシ）」", C_GOLD), ("に飲まれると", W_WHITE)],
                [("ほぼ爪楊枝", C_RED), ("になりますｗ", W_WHITE)],
            ]),
            (8.20, 10.50, "⚡ JUST節見切り!!", C_CYAN, [
                [("左右逆ステアで", W_WHITE), ("JUST節見切り!!", C_CYAN)],
            ]),
            (10.50, 15.00, "5段階鬼難度 // 神域50:50", C_VOLT, [
                [("鬼＆神域【極】", C_RED), ("で", W_WHITE)],
                [("奇跡の50.00:50.00", C_GOLD), ("を狙え!!", W_WHITE)],
            ]),
            (15.00, 19.00, "毎日開発中", C_RED, []),
            (19.00, 23.00, "リクエスト募集", C_CYAN, []),
        ]

        cut_times = [1.80, 5.80, 8.20, 10.50, 15.00, 19.00]
        impact_peaks = [0.95, 3.80, 7.60, 9.40, 13.80, 16.45, 21.20]

        print(f"Capturing {total_frames} frames ({total_dur}s @ {fps}fps)...")
        for f_idx in range(total_frames):
            t = f_idx * dt_sec

            # Scripted scene transitions matching voiceover beats!
            if f_idx == 0:
                cdp.eval_js("window.__shortsDemo.startTier(4, true);")
            elif f_idx == int(1.80 * fps):
                cdp.eval_js("window.__shortsDemo.startTier(1, false);")
            elif f_idx == int(5.80 * fps):
                cdp.eval_js("window.__shortsDemo.startTier(2, false);")
            elif f_idx == int(8.20 * fps):
                cdp.eval_js("window.__shortsDemo.startTier(2, true);")
            elif f_idx == int(10.50 * fps):
                cdp.eval_js("window.__shortsDemo.startTier(4, true);")
            elif f_idx == int(15.00 * fps):
                cdp.eval_js("window.__shortsDemo.startTier(3, true);")
            elif f_idx == int(19.00 * fps):
                cdp.eval_js("window.__shortsDemo.startTier(1, true);")

            # Per-frame AI steering to hit dramatic beats
            if t < 1.80:
                cdp.eval_js("window.__shortsDemo.autoCounter(1.1);")
            elif 1.80 <= t < 5.80:
                if t < 3.15:
                    cdp.eval_js("window.__shortsDemo.autoCounter(0.75);")
                else:
                    cdp.eval_js("window.__shortsDemo.forceRedSnap();")
            elif 5.80 <= t < 8.20:
                cdp.eval_js("window.__shortsDemo.setDrive(0.85, 0.0);")
            elif 8.20 <= t < 10.50:
                cdp.eval_js("window.__shortsDemo.autoCounter(1.0);")
            elif 10.50 <= t < 15.00:
                cdp.eval_js("window.__shortsDemo.autoCounter(0.82);")
            else:
                cdp.eval_js("window.__shortsDemo.autoCounter(0.65);")

            cdp.eval_js(f"window.__stepFrame({dt_sec:.6f});")
            res = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 93})
            raw_img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")

            if f_idx == int(1.10 * fps):
                raw_img.save(thumb_src)

            sec_pill, accent, sub_lines, s0 = "1ST-SEC CHALLENGE", C_VOLT, [], t
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

            frame = draw_shorts_overlay(raw_img, t, total_dur, sec_pill, accent, sub_lines, s0, pulse, t_flash, fonts)
            frame.save(frames_dir / f"frame_{f_idx:04d}.jpg", quality=92)

        events = json.loads(cdp.eval_js("JSON.stringify(window.__gameEvents)") or "[]")
        print(f"Captured {total_frames} frames, {len(events)} gameplay events.")
        cdp.close()

        wav_path = OUT_DIR / "audio.wav"
        print("Synthesizing Keita voiceover + 138 BPM BGM + SFX...")
        generate_audio(total_dur, events, wav_path)

        out_mp4 = OUT_DIR / "day12_short.mp4"
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

        if thumb_src.exists():
            render_note_thumbnail(browser, thumb_src, OUT_DIR / "note_thumbnail.png", day_num=12)
            thumb_src.unlink(missing_ok=True)

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
