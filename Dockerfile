# 星声变调工坊 —— 可部署镜像
# 本机开发用的是 vendor 里的 macOS ffmpeg 二进制，镜像里换成系统 ffmpeg。
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# 生成器需要 numpy；ffmpeg 用系统装的
RUN pip install --no-cache-dir numpy

ENV HOST=0.0.0.0
ENV PORT=8765
EXPOSE 8765

# 数据目录挂出来，重建容器不丢生成的曲子和点评
VOLUME ["/app/generated", "/app/uploads", "/app/output", "/app/scores"]

CMD ["python", "server.py", "8765"]
