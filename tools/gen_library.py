#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成曲库用的原创示范音频（全部程序合成，没有版权问题）。

产出：media/*.mp3 + data/tracks.json
- 夜灯       A 小调慢速琶音，钢琴感
- 雨后       D 大调铺底 pad + 高音旋律
- 示范和弦   C-Am-F-G 分解和弦（页面上的示例）

用法：python3 tools/gen_library.py
"""

import math
import os
import random
import struct
import subprocess
import wave

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MEDIA = os.path.join(ROOT, "media")
DATA = os.path.join(ROOT, "data")
FFMPEG = os.path.join(os.path.dirname(ROOT), "vendor", "imageio_ffmpeg", "binaries",
                      "ffmpeg-macos-aarch64-v7.1")

# 音名 → 频率（十二平均律，A4 = 440）
def note(name):
    names = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4,
             "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * (2 ** ((names[pitch] + (octave - 4) * 12) / 12.0))


def pluck(freq, dur, amp=0.5, bright=1.0):
    """拨弦/钢琴感：基频 + 递减泛音 + 指数衰减"""
    n = int(SR * dur)
    out = [0.0] * n
    for h in range(1, 7):
        if freq * h > SR / 2:
            break
        a = amp * (bright ** (h - 1)) / (h ** 1.6)
        w = 2 * math.pi * freq * h / SR
        for i in range(n):
            t = i / SR
            out[i] += a * math.sin(w * i) * math.exp(-(1.1 + 0.5 * h) * t)
    return out


def pad(freq, dur, amp=0.3):
    """铺底：慢起音、轻微颤音"""
    n = int(SR * dur)
    out = [0.0] * n
    for h in (1, 2, 3):
        w = 2 * math.pi * freq * h / SR
        gain = amp / (h ** 1.8)
        for i in range(n):
            t = i / SR
            env = min(1.0, t / (dur * 0.35)) * (1 - t / dur) ** 0.6
            vib = 1 + 0.0015 * math.sin(2 * math.pi * 4.5 * t)
            out[i] += gain * math.sin(w * i * vib) * env
    return out


def mix_into(buf, src, at_sec, gain=1.0):
    start = int(at_sec * SR)
    for i, v in enumerate(src):
        j = start + i
        if j >= len(buf):
            break
        if j >= 0:
            buf[j] += v * gain


def reverb(buf, taps=((0.11, 0.32), (0.23, 0.2), (0.37, 0.12), (0.53, 0.07))):
    """廉价的反馈延迟混响，让声音别太干"""
    out = list(buf)
    for delay, gain in taps:
        d = int(delay * SR)
        for i in range(d, len(out)):
            out[i] += out[i - d] * gain
    return out


def normalize(buf, peak=0.82):
    m = max(1e-9, max(abs(v) for v in buf))
    return [v / m * peak for v in buf]


def write_mp3(buf, path):
    wav = path.replace(".mp3", ".wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack("<%dh" % len(buf), *[int(max(-1, min(1, v)) * 32767) for v in buf]))
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", wav, "-c:a", "libmp3lame", "-q:a", "4", path], check=True)
    os.remove(wav)


def track_night_lamp():
    """夜灯：A 小调，慢琶音 A-C-E，右手旋律"""
    prog = [["A3", "C4", "E4"], ["F3", "A3", "C4"], ["C3", "E3", "G3"], ["G3", "B3", "D4"]]
    beat = 0.42
    total = len(prog) * 4 * beat
    buf = [0.0] * int(SR * (total + 3))
    random.seed(7)
    melody = ["E5", "D5", "C5", "B4", "C5", "A4", "G4", "A4",
              "C5", "E5", "D5", "C5", "B4", "A4", "A4", "G4"]
    for bar, chord in enumerate(prog):
        for k in range(4):
            t = (bar * 4 + k) * beat
            mix_into(buf, pluck(note(chord[k % 3]), 2.2, 0.42, 0.55), t)
            mix_into(buf, pluck(note(chord[(k + 1) % 3]) / 2, 2.6, 0.22, 0.4), t)
    for i, nm in enumerate(melody):
        mix_into(buf, pluck(note(nm), 1.8, 0.3, 0.45), i * beat * 1.0 + 0.1)
    return normalize(reverb(buf))


def track_after_rain():
    """雨后：D 大调 pad 铺底 + 零星高音"""
    prog = [["D3", "F#3", "A3", "D4"], ["B2", "D3", "F#3", "B3"],
            ["G2", "B2", "D3", "G3"], ["A2", "C#3", "E3", "A3"]]
    seg = 3.2
    buf = [0.0] * int(SR * (len(prog) * seg + 4))
    random.seed(11)
    for bar, chord in enumerate(prog):
        for nm in chord:
            mix_into(buf, pad(note(nm), seg + 1.6, 0.16), bar * seg)
    tones = ["D5", "A4", "F#5", "E5", "D5", "B4", "A4", "F#4"]
    for i, nm in enumerate(tones):
        mix_into(buf, pluck(note(nm), 2.4, 0.26, 0.4), 1.2 + i * 1.15)
    return normalize(reverb(buf, taps=((0.17, 0.34), (0.31, 0.22), (0.47, 0.13))))


def track_demo_chords():
    """示范和弦：C - Am - F - G，一段 8 秒的分解和弦"""
    prog = [["C4", "E4", "G4", "C5"], ["A3", "C4", "E4", "A4"],
            ["F3", "A3", "C4", "F4"], ["G3", "B3", "D4", "G4"]]
    seg = 2.0
    buf = [0.0] * int(SR * len(prog) * seg)
    for bar, chord in enumerate(prog):
        for i, nm in enumerate(chord):
            mix_into(buf, pluck(note(nm), 2.0 - i * 0.12, 0.4, 0.5), bar * seg + i * 0.12)
    return normalize(reverb(buf, taps=((0.09, 0.22), (0.19, 0.12))))



def track_street_light():
    """街灯下的节奏：105BPM 的流行循环，C-G-Am-F，带底鼓和军鼓"""
    prog = [["C3", "E3", "G3"], ["G2", "B2", "D3"], ["A2", "C3", "E3"], ["F2", "A2", "C3"]]
    bpm = 105
    beat = 60.0 / bpm
    bar = 4 * beat
    buf = [0.0] * int(SR * (len(prog) * bar + 2))
    for i, chord in enumerate(prog):
        t0 = i * bar
        # 根音铺底
        mix_into(buf, pad(note(chord[0]) / 2, bar * 0.95, 0.22), t0)
        # 反拍和弦
        for k in range(4):
            at = t0 + k * beat + beat * 0.5
            for nm in chord:
                mix_into(buf, pluck(note(nm) * 2, beat * 0.9, 0.17, 0.6), at)
        # 底鼓：低频短促
        for k in (0, 2):
            for j in range(int(0.12 * SR)):
                idx = int((t0 + k * beat) * SR) + j
                if idx < len(buf):
                    t = j / SR
                    buf[idx] += 0.5 * math.sin(2 * math.pi * 55 * t) * math.exp(-28 * t)
        # 军鼓：噪声
        for k in (1, 3):
            start = int((t0 + k * beat) * SR)
            for j in range(int(0.09 * SR)):
                idx = start + j
                if idx < len(buf):
                    t = j / SR
                    buf[idx] += 0.22 * random.uniform(-1, 1) * math.exp(-45 * t)
    # 主旋律：五声音阶，落在后半段
    mel = ["E5", "G5", "A5", "G5", "E5", "D5", "C5", "D5",
           "E5", "G5", "A5", "C6", "A5", "G5", "E5", "D5"]
    for i, nm in enumerate(mel):
        mix_into(buf, pluck(note(nm), beat * 1.8, 0.24, 0.55), 1.0 + i * beat * 0.5)
    return normalize(reverb(buf, taps=((0.13, 0.2), (0.27, 0.1))))

TRACKS = [
    ("夜灯.mp3", track_night_lamp, {
        "title": "夜灯",
        "artist": "程序合成 · 原创示范",
        "tags": ["抒情", "钢琴", "A 小调"],
        "license": "本项目程序生成，可自由使用",
        "source": "本地生成",
    }),
    ("雨后.mp3", track_after_rain, {
        "title": "雨后",
        "artist": "程序合成 · 原创示范",
        "tags": ["抒情", "氛围", "D 大调"],
        "license": "本项目程序生成，可自由使用",
        "source": "本地生成",
    }),
    ("街灯下的节奏.mp3", track_street_light, {
        "title": "街灯下的节奏",
        "artist": "程序合成 · 原创示范",
        "tags": ["流行", "节奏", "C 大调"],
        "license": "本项目程序生成，可自由使用",
        "source": "本地生成",
    }),
    ("示范和弦.mp3", track_demo_chords, {
        "title": "示范和弦 C-Am-F-G",
        "artist": "程序合成 · 原创示范",
        "tags": ["示例", "和弦"],
        "license": "本项目程序生成，可自由使用",
        "source": "本地生成",
    }),
]


def main():
    os.makedirs(MEDIA, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    meta = []
    for name, fn, info in TRACKS:
        path = os.path.join(MEDIA, name)
        if os.path.exists(path):
            print("已存在，跳过：", name)
        else:
            print("生成中：", name)
            write_mp3(fn(), path)
        meta.append(dict(info, file=name))
    import json
    with open(os.path.join(DATA, "tracks.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("曲库就绪：", MEDIA)


if __name__ == "__main__":
    main()
