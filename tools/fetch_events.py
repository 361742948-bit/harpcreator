#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
活动自动抓取：从上海乐历（shanghaiconcerts.com）拉取竖琴 / 古筝 / 钢琴场次，
解析出日期、时间、场馆、票价、海报，写进 data/events.json。

为什么要挑这个源：
- 它的月度演出页里有 JSON-LD 结构化数据，场次和链接能稳定解析；
- 详情页是服务端渲染的，日期/时间/场馆/票价都写在正文里；
- 大麦、秀动是 JS + 反爬，抓不了。

范围限制（重要）：
- 只覆盖上海的场次。杭州 / 苏州 / 无锡 需要人工核实后手工加进 events.json。
- 手工加的活动（"manual": true）不会被这个脚本覆盖。

用法：
  python3 tools/fetch_events.py [--months 3] [--dry-run]
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
POSTERS = os.path.join(ROOT, "posters")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

KEYWORDS = {
    "竖琴": ("竖琴", "harp"),
    "古筝": ("古筝", "筝"),
    "钢琴": ("钢琴",),
}
# 抓多少条钢琴场次（钢琴演出太多，限制数量，页面上竖琴/古筝优先）
MAX_PER_INSTRUMENT = {"钢琴": 8, "竖琴": 6, "古筝": 6}


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def months_ahead(n=3):
    """返回从本月起的 n 个月，格式 YYYY-MM"""
    now = time.localtime()
    y, m = now.tm_year, now.tm_mon
    out = []
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def list_items(month):
    """拉某个月的演出列表，返回 [(name, url)]"""
    items = []
    for form in ("folk", "chamber", "classical"):
        url = "https://shanghaiconcerts.com/concerts?month=%s&form=%s" % (month, form)
        try:
            page = fetch(url)
        except Exception as e:  # noqa: BLE001
            print("  列表抓取失败 %s：%s" % (url, e))
            continue
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue

            def walk(o):
                if isinstance(o, dict):
                    if o.get("@type") == "ListItem" and o.get("name"):
                        items.append((html.unescape(o["name"]), o.get("url") or ""))
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(data)
    # 去重
    seen, out = set(), []
    for name, url in items:
        if url and url not in seen:
            seen.add(url)
            out.append((name, url))
    return out


def classify(name):
    for instrument, words in KEYWORDS.items():
        if any(w in name.lower() for w in words):
            return instrument
    return None


def parse_detail(url):
    """从演出详情页解析日期 / 时间 / 场馆 / 票价 / 海报"""
    page = fetch(url)
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))

    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if not m:
        return None
    date = "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    t = re.search(r"\b(\d{1,2}):(\d{2})\b", text[m.end():m.end() + 120])
    tm = "%02d:%s" % (int(t.group(1)), t.group(2)) if t else ""

    price = ""
    pm = re.search(r"¥\s?(\d+)(?:\s?[-–~]\s?¥?\s?(\d+))?", text[m.end():m.end() + 400])
    if pm:
        price = "¥" + pm.group(1) + ("–¥" + pm.group(2) if pm.group(2) else "")

    venue = ""
    vm = re.search(r"(上海[\u4e00-\u9fff·]{0,18}(?:音乐厅|大剧院|剧院|剧场|东方艺术中心|文化广场))", text)
    if vm:
        venue = vm.group(1)

    og = re.search(r'property="og:image"[^>]+content="([^"]+)"', page)
    poster_url = og.group(1) if og else ""

    return {"date": date, "time": tm, "venue": venue, "price": price, "poster_url": poster_url}


def save_poster(url):
    """把海报下载到 posters/，返回本地路径；失败返回空字符串"""
    if not url:
        return ""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".jpg"
    name = "auto_" + hashlib.md5(url.encode()).hexdigest()[:12] + ext
    local = os.path.join(POSTERS, name)
    if os.path.exists(local):
        return "/poster/" + name
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) < 5000:  # 太小多半是占位图
            return ""
        with open(local, "wb") as f:
            f.write(data)
        return "/poster/" + name
    except Exception as e:  # noqa: BLE001
        print("    海报下载失败：%s" % e)
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(POSTERS, exist_ok=True)
    today = time.strftime("%Y-%m-%d")

    # 1) 收集候选
    candidates = []
    for month in months_ahead(args.months):
        print("扫描月份:", month)
        for name, url in list_items(month):
            instrument = classify(name)
            if instrument:
                candidates.append({"name": name, "url": url, "instrument": instrument})
        time.sleep(0.3)

    # 同一场次可能在不同 form 里重复
    uniq, seen = [], set()
    for c in candidates:
        key = c["url"]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    print("关键词命中场次:", len(uniq))

    # 2) 逐条解析详情，跳过过期 / 解析失败
    picked, used = [], {"竖琴": 0, "古筝": 0, "钢琴": 0}
    for c in uniq:
        if used[c["instrument"]] >= MAX_PER_INSTRUMENT[c["instrument"]]:
            continue
        try:
            d = parse_detail(c["url"])
        except Exception as e:  # noqa: BLE001
            print("  详情解析失败：%s（%s）" % (c["name"][:30], e))
            continue
        if not d:
            continue
        if d["date"] < today:
            continue
        poster = "" if args.dry_run else save_poster(d["poster_url"])
        picked.append({
            "title": c["name"],
            "date": d["date"],
            "time": d["time"] or "以现场为准",
            "city": "上海",
            "venue": d["venue"] or "以购票页为准",
            "price": d["price"] or "以购票页为准",
            "summary": "%s 类演出，来自上海乐历演出日历；具体曲目与阵容请以购票页为准。" % c["instrument"],
            "poster": poster,
            "url": c["url"],
            "source": "上海乐历 shanghaiconcerts.com（自动抓取）",
            "instrument": c["instrument"],
            "tags": [c["instrument"], "上海", "自动收录"],
            "auto": True,
        })
        used[c["instrument"]] += 1
        print("  收录 %s %s %s" % (d["date"], c["instrument"], c["name"][:36]))

    # 3) 合并：手工条目保留（manual 或 auto 不为 true），自动条目整体替换
    path = os.path.join(DATA, "events.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:  # noqa: BLE001
        old = []

    # 手工条目里如果和自动抓的是同一场（URL 相同），以自动的为准，避免重复
    auto_urls = {e["url"] for e in picked}
    manual = [e for e in old if not e.get("auto") and e.get("url") not in auto_urls]
    mixed = manual + picked
    mixed.sort(key=lambda e: (e.get("date") or "", e.get("time") or ""))

    out = {
        "fetchedAt": time.strftime("%Y-%m-%d %H:%M"),
        "sourceNote": "上海场次由上海乐历自动抓取；杭州/苏州/无锡为人工核实",
        "events": mixed,
    }

    if args.dry_run:
        print("（dry-run）将写入 %d 条：自动 %d + 手工 %d" % (len(mixed), len(picked), len(manual)))
        for e in mixed:
            print("  ", e["date"], e.get("city"), e["title"][:40])
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("已写入 events.json：自动 %d 条，手工 %d 条，共 %d 条" % (len(picked), len(manual), len(mixed)))


if __name__ == "__main__":
    main()
