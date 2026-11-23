#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
星声变调工坊 —— 本地音乐变调 + 抒情活动页 服务端

功能：
1. 上传本地音频文件（mp3/wav/m4a/flac/ogg 等 ffmpeg 能解的都行）
2. 按半音数变调，并保持原时长不变（改音高不改速度）
3. 返回可试听、可下载的 mp3
4. 提供抒情活动数据接口（读取 data/events.json）

启动：  python3 server.py [端口]
依赖：  vendor/ 里的 imageio-ffmpeg（自带的 ffmpeg 二进制）
"""

import json
import os
import re
import subprocess
import sys
import time
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------- 路径配置 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# vendor 里装了 numpy（生成器要用），先放进搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(BASE_DIR), "vendor"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LIBRARY_DIR = os.path.join(BASE_DIR, "media")   # 曲库：放你自己的音频文件，页面自动收录
SCORE_DIR = os.path.join(BASE_DIR, "scores")     # 曲谱：放 PDF / 图片，页面自动收录
GENERATED_DIR = os.path.join(BASE_DIR, "generated")  # 生成的竖琴曲
POSTER_DIR = os.path.join(BASE_DIR, "posters")       # 活动海报（从活动页取，标注来源）
DATA_DIR = os.path.join(BASE_DIR, "data")

for d in (STATIC_DIR, UPLOAD_DIR, OUTPUT_DIR, LIBRARY_DIR, SCORE_DIR, GENERATED_DIR, POSTER_DIR, DATA_DIR):
    os.makedirs(d, exist_ok=True)

# 上传大小上限：60MB，够放一首无损以外的普通歌曲
MAX_UPLOAD = 60 * 1024 * 1024
# 简单限流：公开分享后防止被刷（按客户端 IP 计数，进程内有效）
RATE_LIMIT = {
    "generate": (20, 60),   # 每人每分钟最多生成 20 次
    "upload": (10, 60),     # 每人每分钟最多上传 10 次
    "transpose": (30, 60),  # 每人每分钟最多变调 30 次
}
_rate_hits = {}
# 允许的扩展名
ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}


def get_ffmpeg():
    """
    拿到 ffmpeg 可执行文件的路径。
    优先用 vendor 里的 imageio-ffmpeg（本机开发用），
    换到 Linux 服务器上就退回系统安装的 ffmpeg。
    """
    sys.path.insert(0, os.path.join(os.path.dirname(BASE_DIR), "vendor"))
    sys.path.insert(0, os.path.join(BASE_DIR, "..", "vendor"))
    try:
        import imageio_ffmpeg  # noqa: E402

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    except Exception:
        pass

    import shutil

    system = shutil.which("ffmpeg")
    if system:
        return system
    raise RuntimeError("找不到 ffmpeg：请装 imageio-ffmpeg 或系统 ffmpeg")


FFMPEG = None


def ffmpeg_path():
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = get_ffmpeg()
    return FFMPEG


def safe_name(name):
    """把用户传来的文件名压成安全的名字：去掉括号，其余非法字符换成下划线"""
    name = os.path.basename(name or "audio")
    name = re.sub(r"[（）()\[\]【】{}《》]", "", name)  # 括号直接去掉，别变成 _
    name = re.sub(r"[^\w.\-\s\u4e00-\u9fff]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] or "audio"


def atempo_chain(factor):
    """
    atempo 单级只吃 0.5~2.0，超出范围就串联多级。
    factor 是“时长倍率”，用来把变调后变快的音频拉回原速。
    """
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append("atempo=%.6f" % factor)
    return ",".join(parts)


def pitch_shift(src_path, dst_path, semitones, sample_rate=44100):
    """
    变调核心：先把采样率“改”一下让音高整体升高/降低（asetrate），
    再把时长拉回原来（atempo 反向补偿），最终输出 mp3。
    ratio = 2^(n/12)
    """
    ratio = 2.0 ** (semitones / 12.0)
    # 统一重采样到 44100 再变形，避免不同源的采样率造成奇怪结果
    chain = "aresample=%d,asetrate=%d*%.8f,aresample=%d,%s" % (
        sample_rate,
        sample_rate,
        ratio,
        sample_rate,
        atempo_chain(1.0 / ratio),
    )
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", src_path,
        "-af", chain,
        "-vn",
        "-c:a", "libmp3lame", "-q:a", "2",
        dst_path,
    ]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg 变调失败: " + (proc.stderr or "").strip()[-500:])
    return time.time() - started


def probe_duration(path):
    """用 ffmpeg 读时长（秒），失败返回 None"""
    try:
        proc = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-i", path],
            capture_output=True, text=True,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return round(h * 3600 + mi * 60 + s, 2)
    except Exception:
        pass
    return None


AUDIO_EXT = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".aiff", ".aif")


def read_json_file(path, default):
    """读 JSON 文件；坏文件或不存在就返回默认值，别让整页挂掉"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_file(path, obj):
    """先写临时文件再原子替换，避免写一半崩了把数据弄坏"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def library_tracks():
    """
    曲库 = media 目录里实际的音频文件 + tracks.json 里的元信息。
    把文件丢进 media/ 就自动出现在页面上，不用改代码。
    """
    meta_list = read_json_file(os.path.join(DATA_DIR, "tracks.json"), [])
    lessons = {}
    for l in read_json_file(os.path.join(DATA_DIR, "lessons.json"), []):
        if isinstance(l, dict) and l.get("file"):
            lessons[l["file"]] = l
    meta = {}
    for m in meta_list:
        if isinstance(m, dict) and m.get("file"):
            meta[m["file"]] = m

    try:
        files = sorted(os.listdir(LIBRARY_DIR))
    except FileNotFoundError:
        files = []

    tracks = []
    for name in files:
        if not name.lower().endswith(AUDIO_EXT):
            continue
        info = meta.get(name, {})
        lesson = lessons.get(name)
        tracks.append({
            "id": name,
            "title": info.get("title") or os.path.splitext(name)[0],
            "artist": info.get("artist") or "未标注",
            "category": info.get("category") or "其他",
            "level": info.get("level") or "",
            "tags": info.get("tags") or [],
            "license": info.get("license") or "",
            "source": info.get("source") or "",
            "sourceUrl": info.get("sourceUrl") or "",
            "url": "/lib/" + urllib.parse.quote(name),
            "duration": probe_duration(os.path.join(LIBRARY_DIR, name)),
            "lesson": lesson,  # 学习内容：目标、重难点、练习步骤、调性
        })
    return tracks


SCORE_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")


def library_scores():
    """
    曲谱 = scores/ 目录里的 PDF / 图片 + scores.json 里的条目（也含纯外链的推荐来源）。
    """
    meta_list = read_json_file(os.path.join(DATA_DIR, "scores.json"), [])
    by_file = {}
    links = []
    for m in meta_list:
        if not isinstance(m, dict):
            continue
        if m.get("file"):
            by_file[m["file"]] = m
        elif m.get("url"):
            links.append({
                "id": m.get("id") or m["url"],
                "title": m.get("title") or m["url"],
                "kind": "link",
                "url": m["url"],
                "license": m.get("license") or "",
                "note": m.get("note") or "",
            })

    items = []
    try:
        files = sorted(os.listdir(SCORE_DIR))
    except FileNotFoundError:
        files = []

    for name in files:
        if not name.lower().endswith(SCORE_EXT):
            continue
        info = by_file.get(name, {})
        items.append({
            "id": name,
            "title": info.get("title") or os.path.splitext(name)[0],
            "kind": "file",
            "url": "/score/" + urllib.parse.quote(name),
            "isPdf": name.lower().endswith(".pdf"),
            "license": info.get("license") or "",
            "note": info.get("note") or "",
        })
    return items + links


def all_comments():
    return read_json_file(os.path.join(DATA_DIR, "comments.json"), [])


YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


def generated_history(limit=60):
    """
    已生成的竖琴曲列表。文件名格式：竖琴曲_<情绪>_<调>_<月日>-<时分秒>.mp3
    解析不出来也能列，只是标题退化成文件名。
    """
    items = []
    try:
        names = os.listdir(GENERATED_DIR)
    except FileNotFoundError:
        return items

    for name in names:
        if not name.lower().endswith(".mp3"):
            continue
        full = os.path.join(GENERATED_DIR, name)
        mood, key_name = "", ""
        m = re.match(r"竖琴曲_([^_]+)_([A-G][#♯]?)_(\d{4}-\d{6})", name)
        if m:
            mood, key_name = m.group(1), m.group(2)
        items.append({
            "id": name,
            "mood": mood,
            "key": key_name,
            # 情绪决定大小调：温柔/明快是大调，空灵/忧伤是小调
            "title": (mood + " · " + key_name +
                      (" 小调" if mood in ("空灵", "忧伤", "电音融合") else " 大调"))
                     if mood else os.path.splitext(name)[0],
            "url": "/generated/" + urllib.parse.quote(name),
            "download": "/generated/%s?dl=%s" % (urllib.parse.quote(name), urllib.parse.quote(name)),
            "mtime": os.path.getmtime(full),
            "time": time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(full))),
            "duration": probe_duration(full),
        })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def rate_ok(action, ip):
    """返回 True 表示这次请求放行；超限返回 False"""
    limit, window = RATE_LIMIT.get(action, (1000, 60))
    now = time.time()
    hits = [t for t in _rate_hits.get((action, ip), []) if now - t < window]
    if len(hits) >= limit:
        _rate_hits[(action, ip)] = hits
        return False
    hits.append(now)
    _rate_hits[(action, ip)] = hits
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "StarMusic/1.0"

    # ---------- 基础工具 ----------
    def log_message(self, fmt, *args):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args), flush=True)

    def _send_json(self, obj, status=200, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type=None, as_attachment=None):
        if not os.path.isfile(path):
            page = (
                "<!DOCTYPE html><meta charset='utf-8'>"
                "<title>文件已不存在</title>"
                "<body style='font-family:-apple-system,sans-serif;background:#0b0d12;color:#eef1f7;"
                "padding:48px;line-height:1.8'>"
                "<h2>这个文件已经没了</h2>"
                "<p style='color:#9aa3b2'>变调结果是临时文件，被清理过就打不开了。</p>"
                "<p><a href='/' style='color:#4fd1c5'>回首页</a>，重新上传、再点一次「开始变调」就有了。</p>"
                "</body>"
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        size = os.path.getsize(path)
        ctype = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"

        # 支持 Range 请求：浏览器 <audio> 拖动进度条需要它，否则只能从头播
        start, end = 0, size - 1
        status = 200
        rng = self.headers.get("Range")
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                elif m.group(2):  # bytes=-N 取末尾 N 字节
                    start = max(0, size - int(m.group(2)))
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status, partial = 206, True

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        if as_attachment:
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''%s" % urllib.parse.quote(as_attachment),
            )
        self.end_headers()

        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD + 1024 * 1024:
            raise ValueError("文件超过 60MB 上限")
        return self.rfile.read(length) if length else b""

    # ---------- 路由 ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path == "/api/health":
            self._send_json({"ok": True, "ffmpeg": os.path.basename(ffmpeg_path())})
            return

        if path == "/api/events":
            events_file = os.path.join(DATA_DIR, "events.json")
            data = read_json_file(events_file, [])
            # 兼容两种格式：纯数组（老）和 {events, fetchedAt}（自动抓取后）
            if isinstance(data, dict):
                self._send_json({
                    "ok": True,
                    "events": data.get("events") or [],
                    "fetchedAt": data.get("fetchedAt") or "",
                    "sourceNote": data.get("sourceNote") or "",
                })
            else:
                self._send_json({"ok": True, "events": data or []})
            return

        if path == "/api/tracks":
            tracks = library_tracks()
            # 把点评数量和平均分并进曲目，前端一次拿全
            coms = all_comments()
            for t in tracks:
                mine = [c for c in coms if c.get("track") == t["id"]]
                t["commentCount"] = len(mine)
                stars = [c.get("stars") for c in mine if c.get("stars")]
                t["avgStars"] = round(sum(stars) / len(stars), 1) if stars else None
            self._send_json({"ok": True, "tracks": tracks})
            return

        if path.startswith("/generated/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/generated/"):]))
            target = os.path.normpath(os.path.join(GENERATED_DIR, name))
            if not target.startswith(GENERATED_DIR + os.sep):
                self._send_json({"ok": False, "error": "路径非法"}, 403)
                return
            self._send_file(target, as_attachment=self.query_name(parsed))
            return

        if path == "/api/generated":
            self._send_json({"ok": True, "tracks": generated_history()})
            return

        if path == "/api/videos":
            videos = read_json_file(os.path.join(DATA_DIR, "videos.json"), [])
            self._send_json({"ok": True, "videos": videos})
            return

        if path == "/api/scores":
            self._send_json({"ok": True, "scores": library_scores()})
            return

        if path == "/api/comments":
            q = urllib.parse.parse_qs(parsed.query)
            track = q.get("track", [""])[0]
            coms = [c for c in all_comments() if not track or c.get("track") == track]
            coms.sort(key=lambda c: c.get("ts", 0), reverse=True)
            self._send_json({"ok": True, "comments": coms})
            return

        # 活动海报
        if path.startswith("/poster/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/poster/"):]))
            target = os.path.normpath(os.path.join(POSTER_DIR, name))
            if not target.startswith(POSTER_DIR + os.sep):
                self._send_json({"ok": False, "error": "路径非法"}, 403)
                return
            self._send_file(target)
            return

        # 曲谱文件（PDF / 图片）
        if path.startswith("/score/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/score/"):]))
            target = os.path.normpath(os.path.join(SCORE_DIR, name))
            if not target.startswith(SCORE_DIR + os.sep):
                self._send_json({"ok": False, "error": "路径非法"}, 403)
                return
            self._send_file(target)
            return

        # 曲库文件（不是上传目录，别放混了）
        if path.startswith("/lib/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/lib/"):]))
            self._send_file(os.path.join(LIBRARY_DIR, name))
            return

        # /media/<上传的文件> 与 /out/<变调结果>
        # 这里只取 basename 并校验目录，不能用 safe_name——它会改名字导致取不到文件
        if path.startswith("/media/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/media/"):]))
            target = os.path.normpath(os.path.join(UPLOAD_DIR, name))
            if not target.startswith(UPLOAD_DIR + os.sep):
                self._send_json({"ok": False, "error": "路径非法"}, 403)
                return
            self._send_file(target)
            return
        if path.startswith("/out/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/out/"):]))
            target = os.path.normpath(os.path.join(OUTPUT_DIR, name))
            if not target.startswith(OUTPUT_DIR + os.sep):
                self._send_json({"ok": False, "error": "路径非法"}, 403)
                return
            self._send_file(target, as_attachment=self.query_name(parsed))
            return

        # 静态页面
        if path in ("/", "/index.html"):
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return
        rel = path.lstrip("/")
        target = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not target.startswith(STATIC_DIR):
            self._send_json({"ok": False, "error": "路径非法"}, 403)
            return
        self._send_file(target)

    @staticmethod
    def query_name(parsed):
        q = urllib.parse.parse_qs(parsed.query)
        return q.get("dl", [None])[0]

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/upload":
                self.handle_upload()
            elif path == "/api/transpose":
                self.handle_transpose()
            elif path == "/api/comments":
                self.handle_comment()
            elif path == "/api/generate":
                self.handle_generate()
            elif path == "/api/musicians":
                self.handle_add_musician()
            elif path == "/api/load_generated":
                self.handle_load_generated()
            elif path == "/api/load":
                self.handle_load_from_library()
            else:
                self._send_json({"ok": False, "error": "没有这个接口"}, 404)
        except ValueError as e:
            self._send_json({"ok": False, "error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(e)}, 500)

    # ---------- 曲库：把曲库里的一首拿到变调台 ----------
    def handle_load_from_library(self):
        data = json.loads(self._read_body().decode("utf-8") or "{}")
        # 曲库文件名是原样保存的（可能带括号、空格），只做路径校验，别套 safe_name
        name = os.path.basename(str(data.get("id", "")))
        src = os.path.join(LIBRARY_DIR, name)
        if not name or not os.path.isfile(src):
            raise ValueError("曲库里没有这首")

        uid = "%d_%s" % (int(time.time()), name)
        dst = os.path.join(UPLOAD_DIR, uid)
        with open(src, "rb") as f:
            payload = f.read()
        with open(dst, "wb") as f:
            f.write(payload)

        self._send_json({
            "ok": True,
            "id": uid,
            "name": name,
            "url": "/media/" + urllib.parse.quote(uid),
            "size": len(payload),
            "duration": probe_duration(dst),
        })

    # ---------- 添加音乐人 ----------
    def handle_add_musician(self):
        data = json.loads(self._read_body().decode("utf-8") or "{}")
        name = str(data.get("name") or "").strip()
        instrument = str(data.get("instrument") or "").strip()
        video = str(data.get("video") or "").strip()
        title = str(data.get("title") or "").strip()
        note = str(data.get("note") or "").strip()

        if not name or len(name) > 30:
            raise ValueError("音乐人名字必填，最多 30 字")
        if instrument not in ("竖琴", "古筝", "钢琴"):
            raise ValueError("乐器只能选竖琴 / 古筝 / 钢琴")

        m = YOUTUBE_ID.search(video)
        if m:
            video_id = m.group(1)
        elif re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            video_id = video
        else:
            raise ValueError("视频链接不对，支持 watch?v= / youtu.be/ / shorts/ 或 11 位视频 ID")

        videos_file = os.path.join(DATA_DIR, "videos.json")
        videos = read_json_file(videos_file, [])
        if any(v.get("videoId") == video_id for v in videos):
            raise ValueError("这个视频已经在库里了")

        entry = {
            "videoId": video_id,
            "title": title or ("%s 的演奏" % name),
            "artist": name,
            "instrument": instrument,
            "date": time.strftime("%Y-%m-%d"),
            "note": note or "由访客添加",
            "addedBy": "访客",
            "addedAt": time.strftime("%Y-%m-%d %H:%M"),
        }
        videos.append(entry)
        write_json_file(videos_file, videos)
        self._send_json({"ok": True, "video": entry, "total": len(videos)})

    # ---------- 生成竖琴曲 ----------
    def handle_generate(self):
        if not rate_ok("generate", self.client_address[0]):
            self._send_json({"ok": False, "error": "请求太频繁，歇一分钟再试"}, 429)
            return
        import harpgen  # 延迟导入：numpy 加载失败时页面其它功能不受影响

        data = json.loads(self._read_body().decode("utf-8") or "{}")
        mood = data.get("mood") or "温柔"
        if mood not in harpgen.MOODS:
            raise ValueError("未知情绪：%s" % mood)
        try:
            key_index = int(data.get("key") or 0) % 12
            tempo = int(data.get("tempo") or 0)
            seconds = int(data.get("seconds") or 30)
        except (TypeError, ValueError):
            raise ValueError("参数格式不对")
        if not 10 <= seconds <= 90:
            raise ValueError("时长请控制在 10~90 秒")
        if tempo and not 40 <= tempo <= 160:
            raise ValueError("速度请控制在 40~160 拍/分")

        seed = data.get("seed")
        try:
            seed = int(seed) if seed is not None else int(time.time() * 1000) % 1000000
        except (TypeError, ValueError):
            seed = int(time.time() * 1000) % 1000000

        harpgen.set_ffmpeg(ffmpeg_path())
        stamp = time.strftime("%m%d-%H%M%S")
        name = "竖琴曲_%s_%s_%s.mp3" % (mood, harpgen.NOTE_NAMES[key_index], stamp)
        out_path = os.path.join(GENERATED_DIR, name)

        started = time.time()
        info = harpgen.render_mp3(out_path, mood, key_index, tempo or None, seconds, seed)
        took = time.time() - started

        self._send_json({
            "ok": True,
            "url": "/generated/" + urllib.parse.quote(name),
            "filename": name,
            "download": "/generated/%s?dl=%s" % (urllib.parse.quote(name), urllib.parse.quote(name)),
            "duration": info["seconds"],
            "info": info,
            "seconds_taken": round(took, 2),
        })

    def handle_load_generated(self):
        """把生成的曲子送到变调台"""
        data = json.loads(self._read_body().decode("utf-8") or "{}")
        name = os.path.basename(str(data.get("id", "")))
        src = os.path.join(GENERATED_DIR, name)
        if not name or not os.path.isfile(src):
            raise ValueError("找不到这首生成的曲子")

        uid = "%d_%s" % (int(time.time()), name)
        dst = os.path.join(UPLOAD_DIR, uid)
        with open(src, "rb") as f:
            payload = f.read()
        with open(dst, "wb") as f:
            f.write(payload)

        self._send_json({
            "ok": True,
            "id": uid,
            "name": name,
            "url": "/media/" + urllib.parse.quote(uid),
            "size": len(payload),
            "duration": probe_duration(dst),
        })

    # ---------- 点评 ----------
    def handle_comment(self):
        data = json.loads(self._read_body().decode("utf-8") or "{}")
        track = os.path.basename(str(data.get("track", "")))
        text = (data.get("text") or "").strip()
        name = (data.get("name") or "").strip() or "匿名听众"
        try:
            stars = int(data.get("stars") or 0)
        except (TypeError, ValueError):
            stars = 0

        if not track or not os.path.isfile(os.path.join(LIBRARY_DIR, track)):
            raise ValueError("这首曲子不在曲库里")
        if not text:
            raise ValueError("点评内容不能为空")
        if len(text) > 500:
            raise ValueError("点评最多 500 字")
        if stars < 1 or stars > 5:
            raise ValueError("请先选 1~5 星")
        if len(name) > 20:
            name = name[:20]

        comment = {
            "track": track,
            "name": name,
            "text": text,
            "stars": stars,
            "ts": int(time.time()),
            "time": time.strftime("%Y-%m-%d %H:%M"),
        }
        coms = all_comments()
        coms.append(comment)
        write_json_file(os.path.join(DATA_DIR, "comments.json"), coms)

        mine = [c for c in coms if c.get("track") == track]
        stars_all = [c["stars"] for c in mine]
        self._send_json({
            "ok": True,
            "comment": comment,
            "commentCount": len(mine),
            "avgStars": round(sum(stars_all) / len(stars_all), 1),
        })

    # ---------- 上传 ----------
    def handle_upload(self):
        if not rate_ok("upload", self.client_address[0]):
            self._send_json({"ok": False, "error": "上传太频繁，歇一分钟再试"}, 429)
            return
        """
        解析 multipart/form-data，取第一个文件字段。
        手写解析，避免 cgi 模块在不同 Python 版本上的兼容问题。
        """
        ctype = self.headers.get("Content-Type", "")
        m = re.search(r'boundary="?([^";]+)"?', ctype)
        if "multipart/form-data" not in ctype or not m:
            raise ValueError("请用 multipart/form-data 上传")
        boundary = m.group(1).encode()
        raw = self._read_body()
        if len(raw) > MAX_UPLOAD:
            raise ValueError("文件超过 60MB 上限")

        filename, payload = None, None
        for part in raw.split(b"--" + boundary):
            if b"\r\n\r\n" not in part:
                continue
            head, body = part.split(b"\r\n\r\n", 1)
            head_text = head.decode("utf-8", "replace")
            if 'name="file"' not in head_text:
                continue
            fn = re.search(r'filename="([^"]*)"', head_text)
            if not fn:
                continue
            filename = fn.group(1)
            payload = body[:-2] if body.endswith(b"\r\n") else body
            break

        if not payload:
            raise ValueError("没有收到音频文件")

        name = safe_name(filename or "audio.mp3")
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_EXT:
            raise ValueError("不支持的格式：%s（支持 %s）" % (ext, " ".join(sorted(ALLOWED_EXT))))

        uid = "%d_%s" % (int(time.time()), name)
        dst = os.path.join(UPLOAD_DIR, uid)
        with open(dst, "wb") as f:
            f.write(payload)

        self._send_json({
            "ok": True,
            "id": uid,
            "name": name,
            "url": "/media/" + uid,
            "size": len(payload),
            "duration": probe_duration(dst),
        })

    def handle_transpose(self):
        if not rate_ok("transpose", self.client_address[0]):
            self._send_json({"ok": False, "error": "变调太频繁，歇一分钟再试"}, 429)
            return
        try:
            data = json.loads(self._read_body().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise ValueError("请求体不是合法 JSON")

        uid = safe_name(data.get("id", ""))
        semitones = float(data.get("semitones", 0))
        if not uid or not os.path.isfile(os.path.join(UPLOAD_DIR, uid)):
            raise ValueError("找不到源音频，请重新上传")
        if semitones == 0:
            raise ValueError("半音数为 0，不需要变调")
        if semitones < -12 or semitones > 12:
            raise ValueError("半音数请控制在 -12 到 +12 之间")

        src = os.path.join(UPLOAD_DIR, uid)
        stem = os.path.splitext(uid)[0]
        sign = "up" if semitones > 0 else "down"
        out_name = "%s_%s%s.mp3" % (stem, sign, ("%g" % abs(semitones)).replace(".", "p"))
        dst = os.path.join(OUTPUT_DIR, out_name)

        elapsed = pitch_shift(src, dst, semitones)

        # 下载时给个人看得懂的文件名：去掉上传时的时间戳前缀
        base = re.sub(r"^\d+_", "", os.path.splitext(os.path.basename(uid))[0])
        word = "升" if semitones > 0 else "降"
        dl_name = "%s %s%g半音.mp3" % (base, word, abs(semitones))

        self._send_json({
            "ok": True,
            "id": out_name,
            "url": "/out/" + out_name,
            "download": "/out/%s?dl=%s" % (out_name, urllib.parse.quote(dl_name)),
            "filename": dl_name,
            "semitones": semitones,
            "duration": probe_duration(dst),
            "seconds": round(elapsed, 2),
        })


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8765"))
    # 部署到服务器时设 HOST=0.0.0.0；默认只听本机
    host = os.environ.get("HOST", "127.0.0.1")
    srv = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print("星声变调工坊已启动： http://%s:%d（监听 %s）" % (shown, port, host), flush=True)
    print("按 Ctrl+C 停止", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止", flush=True)
        srv.server_close()


if __name__ == "__main__":
    main()
