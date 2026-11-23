#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给演奏专区批量补充视频：从各 YouTube 频道取播放量靠前的条目，写进 data/videos.json。

只记录视频 ID 和元信息，视频本身用 YouTube 官方嵌入播放，不下载任何音视频。
练习建议按乐器 + 曲目类型生成（同一类型共用一套练法，不是逐句扒谱）。

用法：
    python3 tools/add_videos.py                  # 补齐到每个音乐人 12 条
    python3 tools/add_videos.py --target 14      # 自定义每人至少多少条
    python3 tools/add_videos.py --dry-run        # 只打印将要添加的内容
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_channel_videos import videos as channel_videos  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEOS_FILE = os.path.join(ROOT, "data", "videos.json")

# 只收用户指定的六位演奏者
CHANNELS = [
    ("竖琴", "Sarah Bhalla", "sarahlbhalla", "nature"),
    ("竖琴", "Isolde Harp", "IsoldeHarp", "classical"),
    ("古筝", "碰碰彭碰彭Jingxuan", "jingxuanGuzheng", "street"),
    ("古筝", "崔江卉古筝", "cuijianghui", "studio"),
    ("钢琴", "夜色钢琴曲 赵海洋", "yesegangqin", "original"),
    ("钢琴", "Nice piano sheets", "Nicepianosheets", "piano_cover"),
]

MIN_SECONDS = 60  # 太短的短视频没有完整的跟练价值


def length_seconds(text):
    if not text:
        return 0
    parts = text.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return 0
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def human_views(n):
    if n >= 10000:
        v = n / 10000
        return ("%.1f" % v).rstrip("0").rstrip(".") + " 万"
    return str(n)


def clean_title(artist, title):
    """把频道里那种一长串标题收拾成能看的曲名。"""
    t = title.strip()
    t = re.sub(r"\s*\|\s*Sarah Bhalla\s*$", "", t)
    t = re.sub(r"\s*\(1 Hour\)", "", t, flags=re.I)
    if artist == "Nice piano sheets":
        m = re.search(r"【Piano Cover】(.+?)(?:｜|$)", t)
        if m:
            return m.group(1).strip()
    if artist == "夜色钢琴曲 赵海洋":
        m = re.search(r"「([^」]+)」", t)
        if m:
            return m.group(1).strip()
    if artist == "崔江卉古筝":
        m = re.search(r"《([^》]+)》", t)
        if m:
            return "《%s》" % m.group(1).strip()
        m = re.search(r"【([^】]+)】", t)
        if m:
            return m.group(1).strip()
    if artist == "碰碰彭碰彭Jingxuan":
        # 街拍标题常是【地点｜乐器】“曲名”+ 一大串英文，优先取引号里的曲名
        m = re.search(r"“([^”]{2,40})”", t)
        if m:
            return m.group(1).strip()
        parts = [x.strip() for x in re.split(r"[|｜]", t) if x.strip()]
        drop = {"法国街头", "美国街头", "古筝", "竖琴", "大提琴", "中西合璧",
                "中国传统乐器合奏", "国乐快闪"}
        rest = [x for x in parts if x.strip("【】 ") not in drop]
        if rest:
            return rest[0].strip("【】 ")[:60]
    # 去掉 “|” 之后的频道宣传语和英文说明
    t = re.split(r"\s*[|｜]\s*", t)[0]
    t = re.sub(r"Chinese instrument Guzheng Cover.*$", "", t).strip()
    return t[:80]


# ---------- 跟练建议：按乐器 + 类型套用，曲名会写进目标里 ----------
TIPS = {
    "nature": {
        "goal": "把《%s》当背景音，练“只听低音找和声”的耳朵。",
        "points": [
            "这类一小时的环境竖琴是即兴的，没有固定谱面，跟练目标是抓住和声走向和琶音型，不是弹对每一个音。",
            "先找一个 4 拍循环：只听最下面的低音，拍手打拍子，拍准了再动手。",
            "用最简单的上行琶音跟：根音 → 三音 → 五音；速度慢一半也没关系。",
            "句尾要留白。氛围感来自停顿，不是来自音多。",
        ],
        "steps": [
            "第一遍只听，不弹，跟着低音轻点手指。",
            "第二遍找一个反复出现的小节，记下它往上走还是往下走。",
            "第三遍用 C 大调白键琶音跟一小段，错音不要停。",
            "录音回听，检查自己有没有越弹越快。",
        ],
        "listenFor": [
            "低音什么时候换，换了往上还是往下",
            "两句之间空了几拍",
            "它在哪个时刻从“安静”变成“更安静”",
        ],
    },
    "classical": {
        "goal": "跟着《%s》练“把钢琴/管弦乐句子搬到竖琴上”的改编思维。",
        "points": [
            "这是改编曲：原曲的旋律线未必全在竖琴最亮的音区，先确认主旋律现在落在哪只手。",
            "长句靠持续音撑着，换踏板的时机比弹得快更重要；听到糊音就说明换早了或换晚了。",
            "遇到八度跨不过去的地方，把低音移低八度、或砍掉内声部，旋律保完整优先。",
            "结尾的渐慢要留够时间，竖琴的余音比钢琴长，收尾别急着抬手。",
        ],
        "steps": [
            "先只弹右手旋律，用节拍器 60 起步，确认每个乐句的呼吸点。",
            "再把左手低音单独弹一遍，标出必须换踏板的位置。",
            "双手合起来只练一个乐句，重复到不用看手。",
            "最后对照视频听一遍原速度，找出自己最赶的那一处。",
        ],
        "listenFor": [
            "主旋律现在由哪只手承担",
            "踏板换气声和和声变化是否同步",
            "渐慢是从哪一小节开始的",
        ],
    },
    "street": {
        "goal": "照着《%s》练“街头环境里的稳定输出”：音量、节奏、表情都不被外界带跑。",
        "points": [
            "街头演出有回声和环境噪音，视频里的速度是现场听感，跟练时先按自己的 70% 速度来。",
            "主旋律的滑音和按音是味道所在，先找准音位再追求滑得像，不要一上来就摇。",
            "低音扫弦是节奏骨架，扫弦的落点要一致，宁可少扫不要乱扫。",
            "曲目里如果有合奏乐器（大提琴、竖琴、鼓点），先听对方的进入点，别自己往前冲。",
        ],
        "steps": [
            "先听两遍，标出全曲反复出现的节奏型。",
            "把节奏型单独用手打出来，和视频对齐。",
            "旋律段慢速分手练，右手先过一遍按滑音的位置。",
            "最后连起来跟一段，录下来对比视频里的强弱。",
        ],
        "listenFor": [
            "扫弦在第几拍落下",
            "滑音是从上方还是下方进入",
            "合奏声部什么时候插进来",
        ],
    },
    "studio": {
        "goal": "跟《%s》练“录音室级的干净度”：音头清楚、按滑音准确、句子完整。",
        "points": [
            "录音室版本几乎没有环境声，任何杂音都会被放大，手指触弦要干净利落。",
            "按音的音准是这类曲子的命门，按下去先用耳朵确认高度，再考虑揉弦。",
            "快速指序的均匀度比速度重要，先用节拍器 60 练到每个音一样响。",
            "句子之间要有呼吸，别一口气从头弹到尾。",
        ],
        "steps": [
            "先听一遍，给全曲分句，标出每句的最后一个音。",
            "把最难的一个小节抽出来，单独循环 10 遍。",
            "慢速双手合，节拍器每次加 5 拍，直到接近原速。",
            "最后整段录一遍，只挑一处最不满意的继续练。",
        ],
        "listenFor": [
            "按音落下去的那一下音高是否准",
            "快速指序里有没有哪个音特别响",
            "每个乐句在哪里换气",
        ],
    },
    "original": {
        "goal": "跟《%s》练“自己给自己伴奏”的钢琴思维：左手铺底、右手说话。",
        "points": [
            "这类原创疗愈曲左手多是分解和弦，先固定左手型，再想右手。",
            "右手旋律不要弹满，留出空隙，留白就是这类曲子的情绪。",
            "踏板一小节一换，换在正拍前一点点，声音才不会断。",
            "力度从 pp 到 mp 就够，整首不要出现突强。",
        ],
        "steps": [
            "左手型单独循环一小节，弹到不用看手。",
            "右手旋律单独唱一遍再弹，先确定句子走向。",
            "双手合一个 8 小节段落，速度放到 60。",
            "再听原曲，对比自己哪里弹得太满。",
        ],
        "listenFor": [
            "左手型有没有变化",
            "旋律最高音落在哪一拍",
            "段落之间靠什么过渡",
        ],
    },
    "piano_cover": {
        "goal": "跟《%s》练“流行歌钢琴改编”：旋律突出、伴奏让路、附谱照着来。",
        "points": [
            "这类改编的右手是唱词，左手只是伴奏，音量比例大约是 6:4，别把左手弹成主角。",
            "副歌通常会加厚成八度或和弦，进副歌前先把主歌弹稳。",
            "换踏板跟着和声走，一个和弦一换，不要一小节死踩。",
            "遇到快速经过句，先慢速均匀，再加速，不要用蛮力砸。",
        ],
        "steps": [
            "先照谱分手练主歌 8 小节。",
            "右手单独唱旋律，确认每个字的落点。",
            "左手伴奏型循环，直到不用看手。",
            "合起来跟原速弹副歌，录音检查左手有没有盖过右手。",
        ],
        "listenFor": [
            "主歌到副歌的加厚方式",
            "踏板换在哪个和弦上",
            "旋律的换气点在哪里",
        ],
    },
}


def make_tips(artist, kind, title):
    tpl = TIPS[kind]
    return {
        "goal": tpl["goal"] % title,
        "points": list(tpl["points"]),
        "steps": list(tpl["steps"]),
        "listenFor": list(tpl["listenFor"]),
    }


def make_note(artist, kind, views):
    base = {
        "nature": "频道里播放量靠前的一小时氛围竖琴",
        "classical": "古典改编竖琴独奏",
        "street": "街头古筝实拍",
        "studio": "录音室古筝翻奏",
        "original": "原创治愈系钢琴",
        "piano_cover": "流行歌钢琴改编（频道附谱）",
    }[kind]
    return "%s · 约 %s 次观看" % (base, human_views(views))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=12, help="每个音乐人至少多少条")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    videos = json.load(open(VIDEOS_FILE, encoding="utf-8"))
    added = 0
    for instrument, artist, handle, kind in CHANNELS:
        have = [v for v in videos if v.get("artist") == artist]
        need = max(0, args.target - len(have))
        if not need:
            print("%s：已有 %d 条，跳过" % (artist, len(have)))
            continue
        rows = channel_videos(handle)
        rows = [r for r in rows if r["videoId"] and length_seconds(r["length"]) >= MIN_SECONDS]
        rows.sort(key=lambda r: r["views"], reverse=True)

        existing_ids = {v["videoId"] for v in videos}
        picked = 0
        for r in rows:
            if picked >= need:
                break
            if r["videoId"] in existing_ids:
                continue
            title = clean_title(artist, r["title"])
            entry = {
                "videoId": r["videoId"],
                "title": title,
                "date": "",
                "note": make_note(artist, kind, r["views"]),
                "tips": make_tips(artist, kind, title),
                "artist": artist,
                "instrument": instrument,
            }
            if args.dry_run:
                print("[dry] %s\t%s\t%s" % (artist, r["videoId"], title))
            else:
                videos.append(entry)
                existing_ids.add(r["videoId"])
            picked += 1
            added += 1
        print("%s：新增 %d 条（原有 %d，共 %d）" % (artist, picked, len(have), len(have) + picked))

    if not args.dry_run:
        with open(VIDEOS_FILE, "w", encoding="utf-8") as f:
            json.dump(videos, f, ensure_ascii=False, indent=1)
    print("合计新增 %d 条，总 %d 条" % (added, len(videos)))


if __name__ == "__main__":
    main()
