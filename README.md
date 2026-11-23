# 星声 · 变调工坊

本地跑的音乐小站：

1. **变调台**：传一首歌，选原调和目标调（G → 降 E 这种），音高变了、速度不变，能试听也能下载 mp3。
2. **竖琴专区**：Sarah Bhalla 与 Isolde Harp 的 YouTube 视频用官方嵌入播放（不下载文件）；
   有公开发行曲谱的曲子直接给 IMSLP 公有领域谱子链接，每首都有跟练方法；
   还能用本地合成引擎**生成一首竖琴曲**（选情绪 / 调性 / 速度 / 时长）。
3. **曲谱区**：放公有领域乐谱链接，也能查看自己放进 `scores/` 的 PDF / 图片。
4. **抒情现场**：手动维护的线下活动列表（读 `data/events.json`）。

## 怎么启动

```bash
cd starmusic
PYTHONPATH=$PWD/../vendor python3 server.py 8765
```

然后浏览器打开 <http://127.0.0.1:8765>。换端口就改最后的数字。

需要的东西都已放在 `../vendor`（`imageio-ffmpeg` 自带的 ffmpeg 7.1 静态二进制），
不用装 Python 包、不用装 node、不用联网。

## 怎么用

1. 把音频拖进上传区（mp3 / wav / m4a / flac / ogg，单个 ≤ 60MB）。
   手上没文件就先点「没有文件？用示例片段试试」，带一段无版权的示范和弦。
2. 选「原调」和「目标调」，比如 G（sol）→ E♭（降 mi）。
   「方向」默认「最近」，会挑半音最少的那条路（G→E♭ 是降 4 个，不是升 8 个）；
   想强制往上或往下就选「只升 / 只降」。
3. 半音滑块和调名是联动的：拖滑块会反过来改目标调，适合微调。
4. 点「开始变调」，几秒后出结果，可以试听、下载 mp3。

### 调名和半音的对应

一个半音 = 钢琴上相邻的一个键。常用换算：

| 变调 | 半音数 |
| --- | --- |
| G → E♭ | 降 4 |
| G → D | 降 5 |
| G → A | 升 2 |
| C → E♭ | 升 3 / 降 9（「最近」会给升 3） |

页面会自动算，这里只是方便你核对。

## 下载

变调结果会一直留在 `output/` 里，下载链接不会失效。
下载下来的文件名是「歌名 降4半音.mp3」这种，不带上传时的时间戳。
如果手动清空过 `output/`，旧链接会返回一个提示页，重新点一次「开始变调」再下载即可。

## 竖琴专区

### 视频

视频清单在 `data/videos.json`：

```json
{
  "videoId": "oFMKHdj_aeY",
  "title": "Peaceful Harp in the Moss Forest",
  "date": "2014-01-09",
  "note": "一句简介",
  "tips": {
    "goal": "练习目标",
    "points": ["跟练要点"],
    "steps": ["练习步骤"],
    "listenFor": ["听的时候注意什么"]
  }
}
```

页面用 `youtube-nocookie.com/embed/<videoId>` 官方嵌入，点「在页面里播放」才加载 iframe，
**不下载任何视频或音频文件**。加新视频只要往 JSON 里加一条。

### 曲谱

- 本地谱：把 PDF / 图片（png / jpg / webp / svg）放进 `scores/` 目录，页面自动收录，
  点「查看」直接在页面里打开；标题、说明、授权写在 `data/scores.json`。
- 外链：`data/scores.json` 里只写 `url` 的条目会显示成外链，比如 IMSLP 的公有领域乐谱。

### 为什么没有 Sarah Bhalla 的曲谱

她的频道里是一小时的自然环境 + 即兴竖琴，**没有公开发行过曲谱**；
这类即兴演奏也没有固定谱面可抄。所以每首配的是「听—跟—练」的引导，
而不是逐音照弹的谱子。要练具体曲目，走 `scores/` 里你自己有的谱子，
或者 IMSLP 上公有领域的竖琴曲。

## 竖琴曲生成器

页面「竖琴专区」顶部，选情绪、调性、速度、时长，点「生成」，两秒内出一首竖琴曲。
生成完可以播放、下载 mp3，或者点「拿去变调」直接丢进变调台换个调再听。

实现是 `harpgen.py`，**不是云端 AI 模型**，是规则作曲 + 加性合成：

| 情绪 | 和弦进行 | 特点 |
| --- | --- | --- |
| 温柔 | 大调 I–vi–IV–V | 66 拍/分，慢速分解和弦 |
| 空灵 | 小调 i–VI–III–VII | 58 拍/分，稀疏琶音 + 长混响 |
| 明快 | 大调 I–V–vi–IV | 92 拍/分，琶音密、音色亮 |
| 忧伤 | 小调 i–iv–VI–v | 62 拍/分，低音沉、旋律少 |
| 电音融合 | 小调 i–VI–III–VII | 118 拍/分，四拍底鼓 + 反拍踩镲 + 8 分音符贝斯 + 侧链 pad + 竖琴琶音 |

每首曲子由三路音轨混成：低音（偏左）、琶音（偏右）、旋律（居中），
每个音用 9 次谐波各自衰减来模拟拨弦，再叠四路反馈延迟做混响。
生成 30 秒约 0.7~1.6 秒（纯 Python + numpy）。

```bash
# 命令行试生成四种情绪
PYTHONPATH=../vendor python3 harpgen.py /path/to/ffmpeg
```

接口：

| 接口 | 说明 |
| --- | --- |
| `POST /api/generate` | `{mood, key, tempo, seconds, seed}` 生成一首 |
| `POST /api/load_generated` | `{id}` 把生成的曲子送进变调台 |
| `GET /generated/<文件名>` | 生成的 mp3（支持 Range） |

## 三层导航（乐器 → 演奏者 → 栏目）

演奏专区顶部有三排可点的标签：

1. **乐器**：竖琴 / 古筝 / 钢琴
2. **演奏者**：跟着乐器变，由 `data/videos.json` 的 `artist` 自动生成
3. **栏目**：演奏视频 / 生成（含电音融合）/ 曲谱

点乐器会重置演奏者并刷新视频；点「生成」显示竖琴曲生成器（五种风格里包含电音融合）；
点「曲谱」显示乐谱区。右上角标签实时显示「乐器 · 演奏者 · N 个」。

### 现有内容

| 乐器 | 演奏者 | 数量 |
| --- | --- | --- |
| 竖琴 | Sarah Bhalla | 12 |
| 竖琴 | Isolde Harp | 12 |
| 古筝 | 碰碰彭碰彭Jingxuan | 12 |
| 古筝 | 崔江卉古筝 | 12 |
| 钢琴 | 夜色钢琴曲 赵海洋 | 12 |
| 钢琴 | Nice piano sheets | 12 |

共 72 条，全部是 YouTube 官方嵌入，没有下载任何音视频。
每个音乐人的前 12 条 = 原有精讲条目 + 频道内播放量靠前的条目（按播放量排序后续补）。

### 往栏目里加内容

只改 `data/videos.json`，不用动代码：

```json
{
  "videoId": "YouTube 视频 ID（?v= 后面那串）",
  "title": "标题",
  "artist": "演奏者名（会成为第二排标签）",
  "instrument": "竖琴 / 古筝 / 钢琴",
  "date": "2026-11-20",
  "note": "一句简介",
  "scoreUrl": "有曲谱就填链接，没有就删掉",
  "tips": { "goal": "", "points": [], "steps": [], "listenFor": [] }
}
```

保存后刷新就生效。新 `instrument` 会自动在本排多一个标签，新 `artist` 会在对应乐器下多一个演奏者标签。

### 批量补充：按频道播放量抓视频清单

```bash
# 只看某个频道播放量靠前的视频（不写文件）
python3 tools/yt_channel_videos.py @sarahlbhalla

# 把六位音乐人都补齐到每人至少 12 条
python3 tools/add_videos.py --target 12

# 只预览会加哪些，不写文件
python3 tools/add_videos.py --dry-run
```

- `tools/yt_channel_videos.py` 只读频道公开页面，拿视频 ID、标题、时长、播放量，不下载文件。
- `tools/add_videos.py` 会跳过已有的视频 ID，过滤 1 分钟以下的短视频，按播放量从高到低补足。
- 跟练建议按「乐器 + 曲目类型」生成（氛围即兴 / 古典改编 / 街头实拍 / 录音室翻奏 /
  原创钢琴 / 流行改编），同一类型共用一套练法，**不是逐句扒谱**。
- 频道里没有公开曲谱的曲子，不配曲谱链接；有 IMSLP 公有领域谱子的（Isolde Harp 的古典改编）另行标注。

## 已下线：曲库（试听 / 点评 / 学习模式）

按需求把曲库整块从页面移除了：曲目卡、试听、打星点评、学习面板都不再显示。
但没有删文件——`media/` 里的音频、`data/tracks.json`、`data/lessons.json`、
`data/comments.json` 都还在，`/api/tracks` `/api/comments` 接口也保留着。

要恢复的话，把 `static/index.html` 里的曲库 section 和 `static/app.js` 里对应的
`// ---------- 曲库：分类 + 试听 + 学习 + 点评 ----------` 整块加回去即可。

## 目录结构

```
starmusic/
├── server.py           本地服务：上传、变调、活动数据、静态文件
├── static/
│   ├── index.html      页面结构
│   ├── style.css       样式（深色，带一点光晕）
│   └── app.js          上传、变调、活动渲染的交互逻辑
├── generated/          生成的竖琴曲（运行时产生）
├── posters/            活动海报（仅用于活动列表展示）
├── Dockerfile          部署镜像（含系统 ffmpeg）
├── static/embed.css    嵌入模式样式（?embed=1 时加载）
├── harpgen.py          竖琴曲生成引擎（规则作曲 + 加性合成）
├── media/              旧曲库音频（页面已不显示，文件保留）
├── data/tracks.json    曲库元信息（标题、作者、分类、难度、授权）
├── data/lessons.json   学习内容（目标、重难点、步骤、练唱调）
├── data/videos.json    竖琴视频清单与跟练方法
├── scores/             本地曲谱（PDF / 图片，放进来就自动收录）
├── data/scores.json    曲谱元信息与外部乐谱来源
├── data/comments.json  点评数据
├── data/events.json    抒情活动数据
├── uploads/            上传的原始音频（运行时生成）
└── output/             变调后的 mp3（运行时生成）
```

## 免登录（账户已取消）

站点现在**打开就能用**，没有登录页、没有密码。

- 访问 `/` 直接进入页面；`/login.html` 已删除。
- 顶部只保留「＋ 添加音乐人」，任何人点开都能填。
- 之前那套手机号 + `123456` 的账户代码已整体移除；
  `data/users.json` 和 `data/session_secret.txt` 如果还在，是历史残留，可以删。
- 添加音乐人时 `addedBy` 记为「访客」。

注意：取消登录后，**拿到链接的任何人都能上传、生成、变调、加视频**。
所以限流就是唯一的保护，别把链接发到公开群。

## 添加音乐人

点顶部的「＋ 添加音乐人」，填：

- **音乐人名字**（会成为第二排演奏者标签）
- **乐器**：竖琴 / 古筝 / 钢琴
- **视频链接或 ID**：支持 `watch?v=`、`youtu.be/`、`shorts/`，或直接贴 11 位 ID
- 标题、备注可选

提交后会写进 `data/videos.json`（带 `addedBy` / `addedAt`），刷新就出现在对应乐器栏目下。
同一个视频重复添加会被拒绝。视频本身仍然是 YouTube 官方嵌入，不下载文件。

## 分享给别人（公网链接）

本机跑着，通过 Cloudflare 快速隧道映射成 https 链接，朋友点开就能用，不用注册。

```bash
cd starmusic
./share.sh            # 默认端口 8765
```

脚本会检查服务是否在跑（没跑就起来），然后建隧道并打印形如
`https://xxxx-xxxx.trycloudflare.com` 的地址，把这条发给朋友即可。

**注意这是临时链接**：

- 隧道进程一停、机器休眠或断网，链接就失效；重新运行 `share.sh` 会得到一个**新地址**。
- 只要机器和服务开着，链接就有效。
- 隧道是 Cloudflare 的「无账号快速隧道」，官方不保证可用性，适合分享给朋友短期使用。

### 想要固定链接

需要自己的域名 + 命名隧道，或者部署到服务器：

```bash
cloudflared tunnel login
cloudflared tunnel create starmusic
cloudflared tunnel route dns starmusic music.你的域名.com
cloudflared tunnel run --url http://127.0.0.1:8765 starmusic
```

或者用 `Dockerfile` 部署到任意支持 Docker 的服务器，再套 Nginx + 自己的域名。

### 公开之后的安全注意

- 服务已经加了简单限流：每个 IP 每分钟最多生成 20 次、上传 10 次、变调 30 次，超了返回 429。
- 上传上限 60MB，文件只落在这台电脑的 `uploads/` 和 `output/`。
- 没有登录门禁：任何拿到链接的人都能上传、生成、变调、添加视频，请只发朋友。
- 页脚写的「服务运行在一台本地电脑上」是准确的——别在公网上承诺数据不出机器以外。

## 部署到公网 / 嵌进已有网站

### 先搞清楚一件事

这个站不是纯静态页面：**变调要 ffmpeg，生成竖琴曲要 numpy**，这些都在后端跑。
所以不能只把 html/css 传到你的网站了，需要一个能跑 Python 的地方，然后在你现有网站里
用 iframe 指过去。

### 1. 把后端跑起来

Docker（推荐，镜像里已装系统 ffmpeg）：

```bash
docker build -t starmusic .
docker run -d --name starmusic -p 8765:8765 \
  -v "$PWD/generated:/app/generated" \
  -v "$PWD/scores:/app/scores" \
  starmusic
```

没有 Docker 就直接跑：

```bash
pip install numpy            # 需要 numpy
HOST=0.0.0.0 PORT=8765 python3 server.py 8765
```

- `HOST=0.0.0.0` 才能被外部访问（默认只听本机 127.0.0.1）
- ffmpeg 优先用 `vendor/` 里的二进制，找不到就用系统 `ffmpeg`（`apt install ffmpeg`）
- 挂载 `generated/` 和 `scores/`，重建容器不丢数据

后面建议加一层 Nginx 反代 + HTTPS，把 `http://你的IP:8765` 变成一个域名。

### 2. 嵌进你的网站

任何支持自定义 HTML 的建站平台都能用：

- **WordPress**：加一个「自定义 HTML」区块
- **Wix / Squarespace**：用「Embed HTML」元素
- **自己写的前端**：直接贴

```html
<iframe
  src="https://你的域名/?embed=1"
  title="星声竖琴专区"
  style="width:100%;height:900px;border:0;border-radius:16px;overflow:hidden"
  loading="lazy"
  allow="autoplay; encrypted-media; picture-in-picture"
  referrerpolicy="no-referrer-when-downgrade">
</iframe>
```

`?embed=1` 是嵌入模式：隐藏页头、页脚、活动栏，只留变调台、竖琴专区和曲谱，
外边距也压过一遍（样式在 `static/embed.css`，不改设计师的 `style.css`）。

本机可以直接看效果：**<http://127.0.0.1:8765/embed-demo.html>**
那是一个模拟的「你的网站」页面，中间用 iframe 引用本应用，下面带可复制的嵌入代码。

高度按需调，移动端宽度 100% 就够；iframe 里滚动是独立的。

### 3. 上线前要改的

- 页脚「本地运行，音频不离开这台电脑」——公网部署后这句不准了，得改。
- 曲谱外链和 YouTube 嵌入在 https 下都正常；本站生成的音频是自己合成的，没有版权问题。
- `generated/` 会越存越多，需要的话加个定时清理。

## 变调原理（为什么速度不变）

```
重采样到 44.1k → asetrate（音高 × 2^(n/12)，同时时长变短/变长）
              → atempo（把时长按 1/2^(n/12) 拉回来，音高此时已被“锁住”）
              → 输出 mp3
```

实测：440Hz 的测试音调到 +12 后主频落在 880Hz，-2 后落在 392Hz，时长保持 5.0s 不变。

## 活动栏目（江浙沪竖琴 / 古筝）

只收上海、杭州、苏州、无锡等江浙沪的竖琴 / 古筝音乐会与工作坊，按日期升序排，
过期场次自动标「已结束」并把按钮改成「看回顾」。顶部可按城市筛选。

数据在 `data/events.json`：

```json
{
  "title": "活动名称",
  "date": "2026-12-27",
  "time": "14:00",
  "city": "上海",
  "venue": "上海音乐厅 · 大厅",
  "price": "¥180",
  "summary": "一两句介绍，写清是不是古筝/竖琴专场",
  "poster": "/poster/xxx.jpg",
  "url": "购票或报名页面链接",
  "source": "信息来自哪个站，便于核对",
  "tags": ["古筝", "浙派"]
}
```

### 海报

海报放在 `posters/` 目录，`poster` 字段写 `/poster/文件名`；
没有海报就留空字符串，卡片会只显示文字，不会出错。

现有两张海报是从官方演出页取的宣传图，仅用于本地列展示，并保留了来源链接。
如果主办方有意见，删掉 `posters/` 里对应文件、把 `poster` 字段清空即可。

### 自动更新（每周一 09:00）

活动数据有定时任务自动滚动更新：每周一上午跑一次抓取，过期场次自动清掉，新场次自动补进来。

抓取脚本：

```bash
cd starmusic
python3 tools/fetch_events.py            # 正式抓取
python3 tools/fetch_events.py --dry-run  # 只看招不招得到，不写文件
python3 tools/fetch_events.py --months 4 # 往后看 4 个月
```

脚本做的事：

1. 扫上海乐历（shanghaiconcerts.com）未来 3 个月的演出日历，按「竖琴 / 古筝 / 钢琴」筛；
2. 逐场抓详情页，取日期、时间、场馆、票价、海报（海报下载到 `posters/auto_*.jpg`）；
3. 丢掉已过期的场次；
4. 手工条目（`"auto": false`）保留；同一场次 URL 重复时以自动的为准；
5. 写回 `data/events.json`，并带上 `fetchedAt`，页面会显示「数据更新于 …」。

### 覆盖范围的实话

- **自动抓取只覆盖上海**。上海乐历的数据是结构化 JSON-LD + 服务端渲染详情页，能稳定解析。
- **杭州 / 苏州 / 无锡靠人工核实**。大麦、秀动是 JS 渲染加反爬，抓不了；购票通类站点没有统一字段。
  定时任务里会额外用搜索查这三个城市，只收能核实到日期、场馆、购票链接的场次。
- 所以「自动」指的是上海那部分；其它城市宁可空着也不编。

## 已知限制

- 免登录、没有用户体系：同一个链接所有人看到的是同一份数据，谁都能加视频。
- 单个文件 60MB 上限，超长音频（比如整场演唱会录音）处理会慢。
- 变调用的是 ffmpeg 的 asetrate + atempo，**人声多了会有轻微“发飘”感**；要更自然得换
  rubberband 或 World 声码器（需要额外装东西）。
- 只支持整首整体移调，不做段落内变调、不变调主歌副歌。
- 调名只标了 12 个调，没区分大调小调（移调本身不受影响，只是显示）。
- 活动数据目前是手动维护的 JSON，还没有自动抓取。
- 不做搜索和排序，按 JSON 里的顺序展示。
- 点评没有账号、没有审核、不能删除或修改；写错了只能手动改 `data/comments.json`。
- 曲库只读本地文件，不联网抓任何音频；商业曲目请自行购买后把文件放进 `media/`。
- **不会从 YouTube 抓取商业录音**（版权 + 平台条款），要听就放自有文件或 CC/公有领域资源。
- 曲库（试听 / 点评 / 学习模式）已从页面下线，相关文件与接口保留。
- 活动数据靠人工核实，没有自动抓取；无锡目前没查到可核实的近期场次。
- 「钢琴」是后来加的乐器，和站点原来的竖琴定位不完全一致；若只想要竖琴/古筝，删掉钢琴的条目即可。
- 活动海报是官方宣传图，只做本地列表展示；不转售、不二次分发。
- 生成器是规则作曲，不是深度学习模型：同一情绪多生成几次会听出相似的骨架。
- 竖琴专区只有官方嵌入，没有下载；YouTube 若关闭了某条视频的嵌入权限，那张卡会空白。
- 曲谱区不做 OCR，也不识别 PDF 内容，只是把文件显示出来。
- 分类、难度都写死在 `data/tracks.json` 里，没有自动识别曲风的能力。
