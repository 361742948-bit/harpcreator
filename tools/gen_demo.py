#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成一段无版权的示例音频（4 个和弦的分解旋律，C → Am → F → G），
用来让没有音频文件的人也能直接试试变调效果。

输出：static/demo.wav（再用 ffmpeg 转成 demo.mp3）
"""

import math
import struct
import wave
import os

SR = 44100
CHORDS = [
    [261.63, 329.63, 392.00, 523.25],  # C
    [220.00, 261.63, 329.63, 440.00],  # Am
    [174.61, 220.00, 261.63, 349.23],  # F
    [196.00, 246.94, 293.66, 392.00],  # G
]
CHORD_SEC = 2.0


def envelope(t, dur):
    """软起音 + 指数衰减，听感像拨弦"""
    attack = min(1.0, t / 0.02) if t < 0.02 else 1.0
    decay = math.exp(-2.2 * t / dur)
    return attack * decay


def render():
    frames = []
    total = CHORD_SEC
    n_total = int(SR * total)
    for chord in CHORDS:
        buf = [0.0] * n_total
        for i, f in enumerate(chord):
            # 每个音错开 0.12 秒进入，像分解和弦
            delay = i * 0.12
            for n in range(int(delay * SR), n_total):
                t = (n / SR) - delay
                env = envelope(t, CHORD_SEC - delay)
                # 基频 + 二次谐波，听起来更饱满
                v = 0.55 * math.sin(2 * math.pi * f * t)
                v += 0.12 * math.sin(4 * math.pi * f * t)
                v += 0.05 * math.sin(6 * math.pi * f * t)
                buf[n] += v * env
        # 结尾 0.06 秒淡出，避免爆音
        fade = int(0.06 * SR)
        for n in range(fade):
            buf[n_total - 1 - n] *= n / fade
        # 归一化到 0.75 峰值
        peak = max(1e-9, max(abs(v) for v in buf))
        gain = 0.75 / peak
        frames.extend(int(max(-1.0, min(1.0, v * gain)) * 32767) for v in buf)
    return frames


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "static", "demo.wav")
    frames = render()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack("<%dh" % len(frames), *frames))
    print("已生成", os.path.normpath(out), "时长 %.1fs" % (len(frames) / SR))


if __name__ == "__main__":
    main()
