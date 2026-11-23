#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竖琴曲生成引擎 —— 用和声规则 + 加性合成在本地生成一首竖琴曲。

不是云端 AI 模型，是"规则作曲 + 物理感合成"：
1. 按情绪选和弦进行（大调 / 小调），按拍子铺低音、琶音、旋律；
2. 每个音用衰减泛音合成（类似拨弦/竖琴的泛音结构）；
3. 加立体声摆位和反馈延迟混响，最后归一化。

好处：不联网、不花钱、每次都能得到新曲子，给同一个 seed 能复现。
"""

import math
import random
import struct
import subprocess
import wave

import numpy as np

SR = 32000  # 竖琴能量集中在 8kHz 以下，32k 采样足够，生成更快
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]

# 四种情绪：音阶、和弦进行（音阶级数，0 = 主和弦）、速度建议、琶音密度、音色亮度
MOODS = {
    "温柔": {
        "scale": MAJOR, "prog": [0, 5, 3, 4], "tempo": 66,
        "arp_per_bar": 8, "bright": 0.66, "melody_chance": 0.72,
        "label": "大调 I–vi–IV–V，慢速分解和弦",
    },
    "空灵": {
        "scale": MINOR, "prog": [0, 5, 2, 6], "tempo": 58,
        "arp_per_bar": 6, "bright": 0.5, "melody_chance": 0.5,
        "label": "小调 i–VI–III–VII，稀疏琶音 + 长混响",
    },
    "明快": {
        "scale": MAJOR, "prog": [0, 4, 5, 3], "tempo": 92,
        "arp_per_bar": 8, "bright": 0.8, "melody_chance": 0.85,
        "label": "大调 I–V–vi–IV，速度快、琶音密",
    },
    "忧伤": {
        "scale": MINOR, "prog": [0, 3, 5, 4], "tempo": 62,
        "arp_per_bar": 6, "bright": 0.45, "melody_chance": 0.6,
        "label": "小调 i–iv–VI–v，低音沉、旋律少",
    },
    # 电音融合走 compose_electronic()，这里只放默认参数和说明
    "电音融合": {
        "scale": MINOR, "prog": [0, 5, 2, 6], "tempo": 118,
        "arp_per_bar": 8, "bright": 0.55, "melody_chance": 0.5,
        "label": "小调 i–VI–III–VII + 四拍底鼓、反拍贝斯、侧链 pad",
    },
}


def midi_to_freq(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def pluck(freq, dur, amp=0.5, bright=0.6):
    """
    加性合成一个拨弦音：多次谐波各自衰减，高次谐波衰减更快。
    bright 越大，高次谐波越强，声音越亮。
    """
    n = int(SR * dur) + 1
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)

    # 起音包络：快速拉起，避免爆音
    attack = 1.0 - np.exp(-t / 0.006)
    for k in range(1, 10):
        f = freq * k
        if f > SR / 2 - 300:
            break
        a = amp * (bright ** (k - 1)) / (k ** 1.75)
        tau = dur / (1.4 + 0.85 * k)  # 高频泛音衰得更快
        out += a * np.sin(2 * np.pi * f * t + 0.37 * k) * np.exp(-t / tau)
    out *= attack

    # 收尾淡出，防止截断的咔哒声
    fade = min(int(0.02 * SR), n)
    if fade > 1:
        out[-fade:] *= np.linspace(1.0, 0.0, fade)
    return out


def compose(mood="温柔", key_index=0, tempo=None, seconds=30, seed=None):
    """
    生成一首竖琴曲，返回 (立体声 numpy 数组, 信息字典)。

    key_index: 主音在 12 个半音里的序号（0 = C）
    tempo: 每分钟拍数，None 表示用该情绪的建议速度
    """
    if mood == "电音融合":
        return compose_electronic(key_index, tempo, seconds, seed)

    cfg = MOODS.get(mood) or MOODS["温柔"]
    rng = random.Random(seed)
    tempo = int(tempo or cfg["tempo"])
    seconds = max(10, min(90, int(seconds)))

    beat = 60.0 / tempo
    bar = 4 * beat
    bars = max(2, int(round(seconds / bar)))

    total = bars * bar + 2.5  # 留出尾音
    n_total = int(SR * total)
    # 三路分轨：低音在左、琶音在右、旋律居中
    bass_bus = np.zeros(n_total)
    arp_bus = np.zeros(n_total)
    mel_bus = np.zeros(n_total)

    scale = cfg["scale"]
    prog = cfg["prog"]

    def scale_midi(degree, octave=4):
        """音阶级数 → MIDI 音高（可跨八度）"""
        octv, deg = divmod(degree, 7)
        return 60 + key_index + scale[deg] + (octave - 4) * 12 + octv * 12

    def add(bus, sig, at, gain):
        i0 = int(max(0.0, at) * SR)
        if i0 >= n_total:
            return
        seg = sig[: max(0, n_total - i0)] * gain
        bus[i0:i0 + len(seg)] += seg

    last_mel = 2
    for b in range(bars):
        degree = prog[b % len(prog)]
        chord = [degree, degree + 2, degree + 4]

        # 低音：每小节第 1、3 拍
        for k, at_beat in enumerate((0, 2)):
            m = scale_midi(chord[0], 2 - k)
            add(bass_bus, pluck(midi_to_freq(m), bar * 0.9, 0.42, bright=cfg["bright"] * 0.8),
                b * bar + at_beat * beat, 0.85)

        # 琶音：和弦音 + 高八度循环
        steps = cfg["arp_per_bar"]
        tone_cycle = chord + [degree + 7]
        for i in range(steps):
            at = b * bar + i * (bar / steps) + rng.uniform(-0.008, 0.008)
            idx = i % len(tone_cycle)
            m = scale_midi(tone_cycle[idx], 4)
            if i >= len(tone_cycle):  # 后半小节翻上去
                m += 12
            add(arp_bus, pluck(midi_to_freq(m), bar * 0.62, 0.3, bright=cfg["bright"]),
                at, rng.uniform(0.42, 0.55))

        # 旋律：每半拍起一个音，有时休止
        at_beat = 0.0
        while at_beat < 4:
            dur_beats = rng.choice([0.5, 0.5, 1, 1, 2])
            if rng.random() < cfg["melody_chance"]:
                strong = at_beat in (0, 2)
                if strong:
                    # 强拍落在和弦音上，听起来才“对”
                    deg = chord[rng.choice(range(3))] % 7 + 7
                else:
                    # 弱拍走级进，但不出音阶范围
                    deg = max(0, min(13, last_mel + rng.choice([-2, -1, 1, 1, 2])))
                last_mel = deg
                m = scale_midi(deg, 5)
                add(mel_bus, pluck(midi_to_freq(m), bar * 0.8, 0.24, bright=cfg["bright"] * 1.15),
                    b * bar + at_beat * beat, 0.62)
            at_beat += dur_beats

    # 结尾：主和弦按住，让它自己衰减
    end = bars * bar
    for i, extra in enumerate([0, 2, 4, 7]):
        m = scale_midi(extra, 4)
        add(mel_bus, pluck(midi_to_freq(m), 2.4, 0.3, bright=cfg["bright"] * 0.9),
            end + i * 0.035, 0.7)
        add(bass_bus, pluck(midi_to_freq(m - 24), 2.4, 0.35, bright=cfg["bright"] * 0.6), end, 0.5)

    # 摆位混音
    mix_l = bass_bus * 0.95 + arp_bus * 0.55 + mel_bus * 0.75
    mix_r = bass_bus * 0.7 + arp_bus * 0.95 + mel_bus * 0.75

    # 反馈延迟做混响（简单但够用）
    for delay, g in ((0.11, 0.3), (0.19, 0.2), (0.29, 0.13), (0.41, 0.08)):
        d = int(delay * SR)
        mix_l[d:] += mix_l[:-d] * g
        mix_r[d:] += mix_r[:-d] * g * 0.95

    # 归一化 + 软限幅
    peak = max(1e-9, float(np.max(np.abs(mix_l))), float(np.max(np.abs(mix_r))))
    gain = 0.86 / peak
    mix_l = np.tanh(mix_l * gain)
    mix_r = np.tanh(mix_r * gain)

    # 首尾淡入淡出
    fade = int(0.03 * SR)
    mix_l[:fade] *= np.linspace(0, 1, fade)
    mix_r[:fade] *= np.linspace(0, 1, fade)
    mix_l[-fade:] *= np.linspace(1, 0, fade)
    mix_r[-fade:] *= np.linspace(1, 0, fade)

    stereo = np.stack([mix_l, mix_r], axis=1)
    info = {
        "mood": mood,
        "key": NOTE_NAMES[key_index % 12] + ("大调" if cfg["scale"] == MAJOR else "小调"),
        "tempo": tempo,
        "seconds": round(total, 2),
        "requested": seconds,
        "bars": bars,
        "progression": cfg["label"],
        "seed": seed,
    }
    return stereo, info


def _kick(n_total, SR):
    """底鼓：频率从 130Hz 快速扫到 45Hz，带一点点击噪声"""
    n = int(0.42 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 45.0 + 85.0 * np.exp(-t / 0.055)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase).astype(np.float32) * np.exp(-t / 0.26)
    click = (np.random.rand(n).astype(np.float32) - 0.5) * np.exp(-t / 0.004) * 0.35
    return body + click


def _snare(n_total, SR):
    """军鼓：噪声 + 高通（差分）"""
    n = int(0.22 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = np.random.rand(n).astype(np.float32) - 0.5
    noise = np.diff(noise, prepend=0.0)  # 粗略高通，去掉低频
    return noise * np.exp(-t / 0.075) * 0.9


def _hat(SR, short=True):
    """踩镲：更短的噪声，高通两次"""
    n = int((0.055 if short else 0.09) * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = np.random.rand(n).astype(np.float32) - 0.5
    noise = np.diff(noise, prepend=0.0)
    noise = np.diff(noise, prepend=0.0)
    return noise * np.exp(-t / (0.018 if short else 0.035)) * 0.55


def _saw(freq, dur, amp, harmonics=6):
    """接近锯齿波的音色：奇偶谐波都有，高次衰减"""
    n = int(dur * SR) + 1
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)
    for k in range(1, harmonics + 1):
        if freq * k > SR / 2 - 300:
            break
        out += (amp / k) * np.sin(2 * np.pi * freq * k * t).astype(np.float32)
    env = np.minimum(1.0, t / 0.005) * np.exp(-t / (dur * 0.55))
    return out * env


def compose_electronic(key_index=0, tempo=None, seconds=30, seed=None):
    """
    电音融合：竖琴琶音 + 四拍底鼓 + 反拍贝斯 + 侧链 pad。
    结构与 compose() 一样返回 (stereo, info)。
    """
    cfg = MOODS["电音融合"]
    rng = random.Random(seed)
    tempo = int(tempo or cfg["tempo"])
    seconds = max(10, min(90, int(seconds)))

    beat = 60.0 / tempo
    bar = 4 * beat
    bars = max(2, int(round(seconds / bar)))
    total = bars * bar + 2.0
    n_total = int(SR * total)

    kick_bus = np.zeros(n_total, dtype=np.float32)
    snare_bus = np.zeros(n_total, dtype=np.float32)
    hat_bus = np.zeros(n_total, dtype=np.float32)
    bass_bus = np.zeros(n_total, dtype=np.float32)
    pad_bus = np.zeros(n_total, dtype=np.float32)
    arp_bus = np.zeros(n_total, dtype=np.float32)

    scale = MINOR
    prog = cfg["prog"]

    def scale_midi(degree, octave=4):
        octv, deg = divmod(degree, 7)
        return 60 + key_index + scale[deg] + (octave - 4) * 12 + octv * 12

    def place(bus, sig, at, gain=1.0):
        i0 = int(max(0.0, at) * SR)
        if i0 >= n_total:
            return
        seg = sig[: max(0, n_total - i0)] * gain
        bus[i0:i0 + len(seg)] += seg

    kick_pat = _kick(n_total, SR)
    snare_pat = _snare(n_total, SR)
    hat_short = _hat(SR, True)

    # 侧链包络：每拍底鼓打进来到下一拍的恢复曲线
    dip_len = int(beat * SR)
    t_dip = np.arange(dip_len, dtype=np.float32) / SR
    dip = (1.0 - 0.62 * np.exp(-t_dip / 0.075)).astype(np.float32)
    sidechain = np.ones(n_total, dtype=np.float32)

    for b in range(bars):
        degree = prog[b % len(prog)]
        chord = [degree, degree + 2, degree + 4]
        bar_at = b * bar

        # 第一小节只留 pad + 琶音，做前奏；最后一小节加满
        drums_on = b >= 1
        for k in range(4):
            at = bar_at + k * beat
            if drums_on:
                place(kick_bus, kick_pat, at, 0.95)
                # 侧链：每拍都压一下
                i0 = int(at * SR)
                seg = min(dip_len, n_total - i0)
                if seg > 0:
                    sidechain[i0:i0 + seg] = np.minimum(sidechain[i0:i0 + seg], dip[:seg])
                # 反拍踩镲
                place(hat_bus, hat_short, at + beat * 0.5, 0.55)
                if k in (1, 3):
                    place(snare_bus, snare_pat, at, 0.8)

        # 贝斯：8 分音符泵，反拍更突出
        for i in range(8):
            at = bar_at + i * beat * 0.5
            m = scale_midi(chord[0], 2)
            gain = 0.85 if i % 2 == 1 else 0.55
            place(bass_bus, _saw(midi_to_freq(m), beat * 0.42, 0.5), at, gain)

        # pad：三和弦长音，会被侧链压出“呼吸”
        for j, extra in enumerate(chord):
            m = scale_midi(extra, 4)
            for k in range(1, 4):
                f = midi_to_freq(m + 12) * (1 + 0.002 * (j - 1))
                n = int(bar * SR) + 1
                t = np.arange(n, dtype=np.float32) / SR
                seg = (np.sin(2 * np.pi * f * k * t) * 0.18 / k).astype(np.float32)
                env = np.minimum(1.0, t / (bar * 0.25)) * np.exp(-t / (bar * 1.6))
                place(pad_bus, seg * env, bar_at)

        # 竖琴琶音：16 分音符穿插
        steps = 8
        for i in range(steps):
            at = bar_at + i * (bar / steps)
            deg = chord[i % 3] + 7
            m = scale_midi(deg, 5)
            place(arp_bus, pluck(midi_to_freq(m), beat * 0.55, 0.26, bright=0.72),
                  at + rng.uniform(-0.004, 0.004), rng.uniform(0.5, 0.68))

    # 尾声：主和弦长音
    end = bars * bar
    for i, extra in enumerate([0, 2, 4, 7]):
        m = scale_midi(extra, 4)
        place(arp_bus, pluck(midi_to_freq(m), 1.8, 0.3, bright=0.7), end + i * 0.03, 0.7)

    # 侧链作用到 pad
    ref_len = min(len(pad_bus), len(sidechain))
    pad_bus[:ref_len] *= sidechain[:ref_len]

    # 混音：鼓在中间，贝斯居中，pad 稍宽，琶音偏右
    drum_mix = kick_bus * 0.95 + snare_bus * 0.5 + hat_bus * 0.35
    mix_l = drum_mix + bass_bus * 0.55 + pad_bus * 0.75 + arp_bus * 0.8
    mix_r = drum_mix + bass_bus * 0.55 + pad_bus * 0.7 + arp_bus * 0.95

    # 混响：电音用短一点的尾巴，别糊
    for delay, g in ((0.085, 0.22), (0.145, 0.14), (0.23, 0.08)):
        d = int(delay * SR)
        mix_l[d:] += mix_l[:-d] * g
        mix_r[d:] += mix_r[:-d] * g * 0.92

    peak = max(1e-9, float(np.max(np.abs(mix_l))), float(np.max(np.abs(mix_r))))
    gain = 0.9 / peak
    mix_l = np.tanh(mix_l * gain)
    mix_r = np.tanh(mix_r * gain)

    fade = int(0.03 * SR)
    mix_l[:fade] *= np.linspace(0, 1, fade)
    mix_r[:fade] *= np.linspace(0, 1, fade)
    mix_l[-fade:] *= np.linspace(1, 0, fade)
    mix_r[-fade:] *= np.linspace(1, 0, fade)

    stereo = np.stack([mix_l, mix_r], axis=1)
    info = {
        "mood": "电音融合",
        "key": NOTE_NAMES[key_index % 12] + "小调",
        "tempo": tempo,
        "seconds": round(total, 2),
        "requested": seconds,
        "bars": bars,
        "progression": cfg["label"],
        "seed": seed,
    }
    return stereo, info


def write_wav(path, stereo):
    pcm = np.clip(stereo, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def render_mp3(path, mood, key_index, tempo, seconds, seed):
    """生成并直接落成 mp3，返回信息字典"""
    stereo, info = compose(mood=mood, key_index=key_index, tempo=tempo, seconds=seconds, seed=seed)
    wav_path = path + ".wav"
    write_wav(wav_path, stereo)
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", wav_path,
         "-c:a", "libmp3lame", "-q:a", "3", path],
        check=True,
    )
    os_remove(wav_path)
    info["path"] = path
    return info


def os_remove(p):
    import os
    try:
        os.remove(p)
    except OSError:
        pass


FFMPEG = None


def set_ffmpeg(path):
    global FFMPEG
    FFMPEG = path


if __name__ == "__main__":
    # 直接跑这个文件可以试生成四个情绪的样例
    import sys
    set_ffmpeg(sys.argv[1] if len(sys.argv) > 1 else "ffmpeg")
    for mood in MOODS:
        p = "/tmp/harp_%s.mp3" % mood
        info = render_mp3(p, mood, 0, None, 20, 42)
        print(mood, info)
