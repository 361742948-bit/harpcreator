#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估计一首曲子的调性（大调 / 小调），纯标准库实现，不依赖 numpy。

做法：
1. ffmpeg 把音频解成 11.025kHz 单声道 wav（只取前 30 秒，够判断调性）；
2. 分帧，用 Goertzel 算法量 12 个音级（跨 3 个八度）的能量，累加成色度向量；
3. 和 Krumhansl 的大调 / 小调调性轮廓做相关系数，取最高分。

用法：python3 tools/analyze_key.py <音频文件> [更多文件...]
"""

import math
import os
import struct
import subprocess
import sys
import tempfile
import wave

SR = 11025
FRAME = 4096
SECONDS = 30
FFMPEG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      "vendor", "imageio_ffmpeg", "binaries", "ffmpeg-macos-aarch64-v7.1")

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl & Kessler 的调性轮廓
MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def decode(path, out_wav):
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-t", str(SECONDS), "-i", path,
         "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", out_wav],
        check=True,
    )


def read_wav(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        data = struct.unpack("<%dh" % n, w.readframes(n))
    return data


def goertzel(samples, freq, sr=SR):
    """单频点能量：判断样本里这个频率有多强"""
    k = 2.0 * math.pi * freq / sr
    c = 2.0 * math.cos(k)
    s1 = s2 = 0.0
    for v in samples:
        s0 = c * s1 - s2 + v
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - c * s1 * s2


def chroma(samples, sr=SR):
    """12 个音级的能量向量（跨 3 个八度求和）"""
    vec = [0.0] * 12
    frames = 0
    for start in range(0, len(samples) - FRAME, FRAME):
        block = samples[start:start + FRAME]
        # 加汉宁窗，减少边界泄漏
        win = [block[i] * (0.5 - 0.5 * math.cos(2 * math.pi * i / (FRAME - 1)))
               for i in range(FRAME)]
        for pc in range(12):
            e = 0.0
            for octv in (3, 4, 5):
                f = 440.0 * (2 ** ((pc - 9 + (octv - 4) * 12) / 12.0))
                if f < 60 or f > sr / 2 - 50:
                    continue
                e += goertzel(win, f)
            vec[pc] += e
        frames += 1
    if frames:
        vec = [v / frames for v in vec]
    return vec


def correlate(a, b):
    """皮尔逊相关系数"""
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    return num / (da * db) if da and db else 0.0


def estimate(vec):
    """
    遍历 12 个主音 × 大/小调，取相关系数最高的一组。
    关系大小调（如 C 大调 / A 小调）用的是同一批音，得分往往很接近，
    这种情况把另一个也报出来，别假装很确定。
    """
    scores = {}
    best = None
    for root in range(12):
        for mode, profile in (("大调", MAJOR), ("小调", MINOR)):
            rotated = [profile[(i - root) % 12] for i in range(12)]
            r = correlate(vec, rotated)
            scores[(root, mode)] = r
            if best is None or r > best[2]:
                best = (root, mode, r)

    root, mode, r = best
    twin = None
    other_mode = "小调" if mode == "大调" else "大调"
    # 关系大小调：大调主音往下 3 个半音 = 小调主音（C 大调 ↔ A 小调）
    rel_root = (root - 3) % 12 if mode == "大调" else (root + 3) % 12
    alt = scores.get((rel_root, other_mode))
    if alt is not None and r - alt < 0.06:
        twin = (rel_root, other_mode)
    return (root, mode, r, twin)


def analyze(path):
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        decode(path, tmp)
        samples = read_wav(tmp)
        vec = chroma(samples)
        root, mode, r, twin = estimate(vec)
        top = sorted(range(12), key=lambda i: vec[i], reverse=True)[:3]
        key = NAMES[root] + " " + mode
        if twin:
            key += "（也接近 " + NAMES[twin[0]] + " " + twin[1] + "，关系大小调）"
        return {
            "key": key,
            "confidence": round(r, 3),
            "top_notes": [NAMES[i] for i in top],
            "vector": [round(v / max(vec), 2) for v in vec] if max(vec) else [],
        }
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    files = sys.argv[1:]
    if not files:
        print("用法：python3 tools/analyze_key.py <音频文件>...")
        return
    for f in files:
        try:
            r = analyze(f)
            print("%-42s → %-6s 置信度 %s  主要音级 %s" % (
                os.path.basename(f), r["key"], r["confidence"], "/".join(r["top_notes"])))
        except Exception as e:  # noqa: BLE001
            print("%-42s → 分析失败：%s" % (os.path.basename(f), e))


if __name__ == "__main__":
    main()
