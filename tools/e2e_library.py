#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
曲库功能的真浏览器测试：开页面 → 点「点评」→ 打星 → 写内容 → 提交 →
检查点评出现在列表里，并把页面截下来。

用法：python3 tools/e2e_library.py <调试端口> <截图路径>
"""

import base64
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from e2e_browser import DevTools  # noqa: E402


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9334
    shot = sys.argv[2] if len(sys.argv) > 2 else "/tmp/library.png"

    dt = DevTools(port)
    dt.call("Page.enable")
    dt.call("Runtime.enable")
    dt.call("Page.navigate", url="http://127.0.0.1:8765/")

    # 1) 等曲库渲染出来
    dt.wait_js("document.querySelectorAll('.track-card').length >= 3", label="曲库渲染")
    n = dt.js("document.querySelectorAll('.track-card').length")
    print("[1/5] 曲库渲染了", n, "首")

    # 2) 音频能不能真的加载（readyState ≥ 1 说明元数据拿到了，可以播）
    dt.wait_js("""(() => {
      const a = document.querySelector('.track-card audio');
      return a && a.readyState >= 1 && a.duration > 0;
    })()""", label="音频元数据")
    info = dt.js("""(() => {
      const a = document.querySelector('.track-card audio');
      return a.duration.toFixed(2) + ' 秒, readyState=' + a.readyState;
    })()""")
    print("[2/5] 音频已加载：", info)

    # 3) 点开第一首的点评
    dt.js("document.querySelector('.track-card [data-act=\"comments\"]').click()")
    dt.wait_js("!!document.querySelector('.comment-box textarea')", label="点评框")
    print("[3/5] 点评框已展开")

    # 4) 打 4 星 + 写内容 + 提交
    dt.js("""(() => {
      const box = document.querySelector('.comment-box');
      box.querySelector('[data-value="4"]').click();
      box.querySelector('.cname').value = '浏览器测试';
      box.querySelector('.ctext').value = '在真浏览器里点了一遍，播放和点评都通了。';
    })()""")
    hint = dt.js("document.querySelector('.comment-box .star-hint').textContent")
    print("[4/5] 打分状态：", hint)
    dt.js("document.querySelector('.comment-box [data-act=\"send\"]').click()")

    # 5) 等点评出现在列表里
    dt.wait_js("""(() => {
      const cmts = document.querySelectorAll('.comment-box .cmt');
      return cmts.length > 0;
    })()""", timeout=20, label="点评出现在列表")
    latest = dt.js("""(() => {
      const c = document.querySelector('.comment-box .cmt');
      return c.querySelector('b').textContent + ' / ' + c.querySelector('.cmt-stars').textContent + ' / ' + c.querySelector('p').textContent;
    })()""")
    print("[5/5] 列表里的最新点评：", latest)

    data = dt.call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    with open(shot, "wb") as f:
        f.write(base64.b64decode(data["data"]))
    print("截图：", shot)


if __name__ == "__main__":
    main()
