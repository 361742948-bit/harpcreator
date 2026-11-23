#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学习功能的真浏览器测试：分类筛选 → 打开学习模式 → 勾选练习步骤 →
点「X 调」练唱 → 检查变调台是否设好 → 刷新页面看进度是否还在 → 截图。

用法：python3 tools/e2e_learn.py <调试端口> <截图路径>
"""

import base64
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from e2e_browser import DevTools  # noqa: E402


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9335
    shot = sys.argv[2] if len(sys.argv) > 2 else "/tmp/learn.png"

    dt = DevTools(port)
    dt.call("Page.enable")
    dt.call("Runtime.enable")
    dt.call("Page.navigate", url="http://127.0.0.1:8765/")

    dt.wait_js("document.querySelectorAll('.track-card').length >= 7", label="曲库")
    print("[1/7] 曲库", dt.js("document.querySelectorAll('.track-card').length"), "首")

    # 分类筛选
    dt.js("""(() => {
      document.querySelector('[data-filter="古典"]').click();
    })()""")
    time.sleep(0.3)
    n_classical = dt.js("document.querySelectorAll('.track-card').length")
    title = dt.js("document.querySelector('.track-card h3').textContent")
    print("[2/7] 点「古典」→", n_classical, "首：", title)

    dt.js("document.querySelector('[data-filter=\"全部\"]').click()")
    time.sleep(0.3)

    # 打开第一首的学习模式
    dt.js("document.querySelector('[data-act=\"lesson\"]').click()")
    dt.wait_js("!!document.querySelector('.lesson .points li')", label="学习面板")
    print("[3/7] 学习面板：重难点", dt.js("document.querySelectorAll('.lesson .points li').length"),
          "条 / 步骤", dt.js("document.querySelectorAll('.lesson .step-item').length"), "步")
    print("      调性：", dt.js("document.querySelector('.lesson-key').textContent"))

    # 勾选第一步
    dt.js("""(() => {
      const box = document.querySelector('.lesson [data-act="step"]');
      box.checked = true;
      box.dispatchEvent(new Event('change', {bubbles: true}));
    })()""")
    time.sleep(0.3)
    print("[4/7] 勾选后进度：", dt.js("document.querySelector('.lesson-progress').textContent"))

    # 点「C 调」练唱
    dt.js("""(() => {
      const btn = document.querySelector('[data-act="practice"]');
      btn.click();
    })()""")
    dt.wait_js("!!(document.getElementById('controls') && !document.getElementById('controls').hidden)", timeout=20, label="进入变调台")
    print("[5/7] 变调台：", dt.js("document.getElementById('fileName').textContent"), "|",
          dt.js("document.getElementById('shiftReadout').textContent"))
    print("      原调下拉 =", dt.js("document.getElementById('fromKey').selectedOptions[0].textContent"),
          "| 目标调 =", dt.js("document.getElementById('toKey').selectedOptions[0].textContent"))

    # 刷新页面，看练习进度是否保留（localStorage）
    dt.call("Page.navigate", url="http://127.0.0.1:8765/")
    dt.wait_js("document.querySelectorAll('.track-card').length >= 7", label="重新加载")
    dt.js("document.querySelector('[data-act=\"lesson\"]').click()")
    dt.wait_js("!!document.querySelector('.lesson-progress')", label="面板重开")
    print("[6/7] 刷新后进度：", dt.js("document.querySelector('.lesson-progress').textContent"),
          "| 勾选状态：", dt.js("document.querySelector('.lesson [data-act=\"step\"]').checked"))

    data = dt.call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    with open(shot, "wb") as f:
        f.write(base64.b64decode(data["data"]))
    print("[7/7] 截图：", shot)


if __name__ == "__main__":
    main()
