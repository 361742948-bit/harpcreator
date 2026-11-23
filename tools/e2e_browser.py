#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在真浏览器里跑一遍变调流程（无头 Chrome + DevTools 协议）。

步骤：打开页面 → 自动载入示例 → 设半音 -4 → 点「开始变调」→ 等结果 →
截图。这样能验证前端 JS 是否真的把流程走通了，而不是只测接口。

用法：python3 tools/e2e_browser.py <chrome调试端口> <截图输出路径>
"""

import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request


# ---------- 极简 WebSocket 客户端（只为连 DevTools，用标准库手写） ----------
class WS:
    def __init__(self, url):
        # url 形如 ws://127.0.0.1:9333/devtools/page/XXXX
        assert url.startswith("ws://")
        rest = url[5:]
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        hs = (
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)
        )
        self.sock.sendall(hs.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self._id = 0

    def _recv(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket 断开")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, obj):
        payload = json.dumps(obj).encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        n = len(payload)
        head = b"\x81"
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", n)
        self.sock.sendall(head + mask + masked)

    def recv(self):
        while True:
            b1, b2 = self._recv(2)
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._recv(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._recv(8))[0]
            data = self._recv(n) if n else b""
            if masked:
                data = bytes(c ^ data[i % 4] for i, c in enumerate(data))
            if opcode == 1:
                return json.loads(data.decode())
            if opcode == 8:
                raise ConnectionError("服务端关闭")
            if opcode == 9:  # ping → pong
                self.sock.sendall(b"\x8a\x80" + os.urandom(4))


class DevTools:
    def __init__(self, port):
        url = "http://127.0.0.1:%d/json/list" % port
        targets = json.load(urllib.request.urlopen(url, timeout=10))
        page = [t for t in targets if t.get("type") == "page"][0]
        self.ws = WS(page["webSocketDebuggerUrl"])
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        self.ws.send({"id": self.n, "method": method, "params": params})
        while True:
            msg = self.ws.recv()
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError("%s 失败: %s" % (method, msg["error"]))
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def wait_js(self, expr, timeout=25, label=""):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.js(expr):
                return True
            time.sleep(0.25)
        raise TimeoutError("等待超时：" + (label or expr))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    shot = sys.argv[2] if len(sys.argv) > 2 else "/tmp/e2e.png"
    page_url = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8765/?demo=1"

    dt = DevTools(port)
    dt.call("Page.enable")
    dt.call("Runtime.enable")
    dt.call("Page.navigate", url=page_url)

    # 1) 等页面脚本把示例音频传上去（控件出现 = 上传完成）
    dt.wait_js("!!(document.getElementById('controls') && !document.getElementById('controls').hidden)",
               label="示例音频上传完成")
    print("[1/4] 页面载入、示例音频已上传")

    # 2) 设成 G → 降 E（-4 半音），走的是同一套滑块逻辑
    dt.js("""
      (() => {
        const r = document.getElementById('semiRange');
        r.value = -4;
        r.dispatchEvent(new Event('input', {bubbles: true}));
        return document.getElementById('shiftReadout').textContent;
      })()
    """)
    readout = dt.js("document.getElementById('shiftReadout').textContent")
    print("[2/4] 变调说明：", readout)

    # 3) 点变调，等结果出现
    dt.js("document.getElementById('transposeBtn').click()")
    dt.wait_js("!document.getElementById('result').hidden", timeout=60, label="变调结果")
    badge = dt.js("document.getElementById('resultBadge').textContent")
    href = dt.js("document.getElementById('downloadBtn').getAttribute('href')")
    name = dt.js("document.getElementById('downloadBtn').getAttribute('download')")
    status = dt.js("document.getElementById('status').textContent")
    print("[3/4] 结果：", badge, "|", status)
    print("      下载链接：", href)
    print("      下载文件名：", name)

    # 4) 截图
    shot_data = dt.call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    with open(shot, "wb") as f:
        f.write(base64.b64decode(shot_data["data"]))
    print("[4/4] 截图已保存：", shot)


if __name__ == "__main__":
    main()
