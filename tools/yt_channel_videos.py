#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 YouTube 频道页（/videos）读取视频清单：ID、标题、发布时间、播放量。

只读取公开页面上的 ytInitialData，不下载任何音视频文件。
用法：
    python3 tools/yt_channel_videos.py @sarahlbhalla [--sort popular]
    python3 tools/yt_channel_videos.py @sarahlbhalla --json out.json
"""
import argparse
import json
import re
import sys
import time
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def fetch(url, tries=3):
    """取页面；YouTube 偶尔会临时返回验证页或 404，重试几次再放弃。"""
    last = None
    for i in range(tries):
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            if "ytInitialData" in html:
                return html
            last = RuntimeError("页面里没有 ytInitialData（可能被要求验证）")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 + i * 2)
    raise SystemExit("取频道页失败：%s" % last)


def initial_data(html):
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        m = re.search(r'window\["ytInitialData"\] = (\{.*?\});', html, re.S)
    if not m:
        raise SystemExit("页面里没有 ytInitialData，可能被要求登录或验证")
    return json.loads(m.group(1))


def walk(node, key):
    """深度优先找出所有 key 对应的节点。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, key)


def text_of(node):
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if "simpleText" in node:
        return node["simpleText"]
    if "runs" in node:
        return "".join(r.get("text", "") for r in node["runs"])
    return ""


def parse_views(s):
    """把 '1.2M views' / '3.4万次观看' 统一成整数。"""
    s = s.replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*([KMB万亿]?)", s)
    if not m:
        return 0
    n = float(m.group(1))
    unit = m.group(2)
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "万": 1e4, "亿": 1e8, "": 1}[unit]
    return int(n * mult)


def videos(handle, sort=""):
    if not handle.startswith("@"):
        handle = "@" + handle
    base = f"https://www.youtube.com/{handle}/videos"
    url = base + ("?view=0&sort=p" if sort == "popular" else "")
    data = initial_data(fetch(url))
    seen = set()
    out = []

    # 旧版布局：videoRenderer
    for v in walk(data, "videoRenderer"):
        vid = v.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        out.append({
            "videoId": vid,
            "title": text_of(v.get("title")),
            "published": text_of(v.get("publishedTimeText")),
            "views": parse_views(text_of(v.get("viewCountText"))),
            "viewsText": text_of(v.get("viewCountText")),
            "length": text_of(v.get("lengthText")),
        })

    # 新版布局：lockupViewModel（2025 起频道页改用它）
    for v in walk(data, "lockupViewModel"):
        vid = v.get("contentId")
        if not vid or vid in seen or v.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            continue
        seen.add(vid)
        meta = (v.get("metadata") or {}).get("lockupMetadataViewModel") or {}
        title = (meta.get("title") or {}).get("content", "")
        parts = []
        rows = (((meta.get("metadata") or {}).get("contentMetadataViewModel") or {})
                .get("metadataRows")) or []
        for row in rows:
            for part in row.get("metadataParts") or []:
                label = (part.get("accessibilityLabel") or "").strip()
                t = ((part.get("text") or {}).get("content") or "").strip()
                if t:
                    parts.append((t, label))
        # 播放量：优先看无障碍标签里的“X 回視聴 / X 次观看 / X views”
        views_text = ""
        published = ""
        for t, label in parts:
            if re.search(r"視聴|观看|觀看|views|회", label or t):
                views_text = t
            elif not published:
                published = t
        if not views_text:
            # 退路：纯数字开头的那一段当播放量
            for t, label in parts:
                if re.match(r"^[\d.]+\s*[KMB万亿]?$", t):
                    views_text = t
                    break
        length = ""
        for badge in walk(v.get("contentImage"), "thumbnailBadgeViewModel"):
            if re.fullmatch(r"\d+:\d+(:\d+)?", (badge.get("text") or "").strip()):
                length = badge["text"].strip()
                break
        out.append({
            "videoId": vid,
            "title": title,
            "published": published,
            "views": parse_views(views_text),
            "viewsText": views_text,
            "length": length,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--sort", default="", help="popular 表示按播放量")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    rows = videos(args.handle if args.handle.startswith("@") else "@" + args.handle, args.sort)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    for r in rows:
        print(f"{r['videoId']}\t{r['viewsText']}\t{r['published']}\t{r['title']}")
    print(f"共 {len(rows)} 条", file=sys.stderr)


if __name__ == "__main__":
    main()
