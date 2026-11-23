// 星声变调工坊 —— 前端逻辑
// 说明：所有音频处理都在本机服务端（ffmpeg）完成，页面只负责上传、试听、下载。
(function () {
  "use strict";

  // ---------- 嵌入模式：被 iframe 引用时加 ?embed=1 ----------
  // 只加载一份补充样式，覆盖间距并隐藏页头页脚，不动设计师的 style.css
  if (new URLSearchParams(location.search).get("embed") === "1") {
    document.body.classList.add("embed");
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/embed.css";
    document.head.appendChild(link);
  }

  // ---------- 元素 ----------
  const $ = (id) => document.getElementById(id);

  // 转义 HTML：所有来自 JSON / 用户输入的内容都要过一遍
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  const dropzone = $("dropzone"), fileInput = $("fileInput"), pickBtn = $("pickBtn");
  const trackInfo = $("trackInfo"), fileName = $("fileName"), fileMeta = $("fileMeta");
  const origPlayer = $("origPlayer"), resetBtn = $("resetBtn");
  const controls = $("controls"), fromKeySel = $("fromKey"), toKeySel = $("toKey");
  const dirSel = $("direction"), shiftReadout = $("shiftReadout");
  const semiRange = $("semiRange"), semiOut = $("semiOut");
  const transposeBtn = $("transposeBtn"), statusEl = $("status");
  const result = $("result"), outPlayer = $("outPlayer"), resultBadge = $("resultBadge");
  const downloadBtn = $("downloadBtn"), newShiftBtn = $("newShiftBtn");
  const toast = $("toast"), ffmpegTag = $("ffmpegTag");
  const eventList = $("eventList"), eventCount = $("eventCount");

  // ---------- 状态 ----------
  let current = null; // { id, name, url, duration, size }

  // 12 个调（按琴键顺序）。一个调名对应 0~11，升号和降号是同一个键的两个叫法。
  const KEYS = [
    { sym: "C", alt: "", cn: "do" },
    { sym: "D♭", alt: "C♯", cn: "降re" },
    { sym: "D", alt: "", cn: "re" },
    { sym: "E♭", alt: "D♯", cn: "降mi" },
    { sym: "E", alt: "", cn: "mi" },
    { sym: "F", alt: "", cn: "fa" },
    { sym: "G♭", alt: "F♯", cn: "降sol" },
    { sym: "G", alt: "", cn: "sol" },
    { sym: "A♭", alt: "G♯", cn: "降la" },
    { sym: "A", alt: "", cn: "la" },
    { sym: "B♭", alt: "A♯", cn: "降si" },
    { sym: "B", alt: "", cn: "si" },
  ];
  // ---------- 小工具 ----------
  function showToast(msg, isErr) {
    toast.textContent = msg;
    toast.className = "toast" + (isErr ? " err" : "");
    toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { toast.hidden = true; }, 3200);
  }

  function fmtSize(bytes) {
    if (!bytes) return "-";
    return bytes > 1024 * 1024
      ? (bytes / 1024 / 1024).toFixed(1) + " MB"
      : Math.round(bytes / 1024) + " KB";
  }

  function fmtDur(sec) {
    if (sec == null) return "未知时长";
    const m = Math.floor(sec / 60), s = Math.round(sec % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  // 根据原调、目标调、方向算出要移动的半音数
  // 说明：调名只是叫法，实际移动量就是两个调在琴键上相差的键数
  function computeSemitones() {
    const from = Number(fromKeySel.value);
    const to = Number(toKeySel.value);
    const dir = dirSel.value;
    const up = (to - from + 12) % 12; // 向上走的半音数 0~11
    if (up === 0) return 0;
    if (dir === "up") return up;            // 只升：+up
    if (dir === "down") return up - 12;     // 只降：-(12-up)
    return up <= 6 ? up : up - 12;          // 最近：不超过 6 个半音
  }

  function dirWord(n) {
    if (n === 0) return "不变";
    return n > 0 ? "升 " + n + " 个半音" : "降 " + Math.abs(n) + " 个半音";
  }

  // 把两个下拉框 + 滑块 + 说明文字同步成同一个状态
  function syncFromKeys() {
    const n = computeSemitones();
    semiRange.value = n;
    semiOut.textContent = (n > 0 ? "+" : "") + n;

    const from = KEYS[Number(fromKeySel.value)];
    const to = KEYS[Number(toKeySel.value)];
    if (n === 0) {
      shiftReadout.innerHTML = "原调和目标调是同一个，不用变。换一个目标调试试。";
      return;
    }
    shiftReadout.innerHTML =
      from.sym + "（" + from.cn + "） → <b>" + to.sym + "（" + to.cn + "）</b>，" +
      dirWord(n) + "，速度不变。";
  }

  // 滑块被拖动时，反过来更新目标调
  function syncFromSlider() {
    const n = Number(semiRange.value);
    semiOut.textContent = (n > 0 ? "+" : "") + n;
    const to = (Number(fromKeySel.value) + n + 120) % 12;
    toKeySel.value = to;
    const from = KEYS[Number(fromKeySel.value)];
    shiftReadout.innerHTML = n === 0
      ? "原调和目标调是同一个，不用变。换一个目标调试试。"
      : from.sym + "（" + from.cn + "） → <b>" + KEYS[to].sym + "（" + KEYS[to].cn + "）</b>，" +
        dirWord(n) + "，速度不变。";
  }

  // ---------- 初始化调名下拉 ----------
  KEYS.forEach((k, i) => {
    [fromKeySel, toKeySel].forEach((sel) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = k.sym + "（" + k.cn + "）" + (k.alt ? " · 也写作 " + k.alt : "");
      sel.appendChild(opt);
    });
  });
  // 默认就按用户说的例子：G 调 → 降 E 调
  fromKeySel.value = "7";  // G
  toKeySel.value = "3";    // E♭

  // ---------- 引擎状态 ----------
  fetch("/api/health")
    .then((r) => r.json())
    .then((d) => {
      if (d.ok) {
        ffmpegTag.textContent = "变调引擎就绪";
        ffmpegTag.className = "tag ok";
      }
    })
    .catch(() => {
      ffmpegTag.textContent = "引擎离线";
      ffmpegTag.className = "tag bad";
    });

  // ---------- 上传 ----------
  function openPicker() { fileInput.click(); }
  pickBtn.addEventListener("click", openPicker);
  dropzone.addEventListener("click", (e) => {
    // 点示例按钮时不要弹文件选择框
    if (e.target === pickBtn || e.target.id === "demoBtn") return;
    openPicker();
  });

  // 示例音频：没有文件也能直接体验变调
  function loadDemo() {
    fetch("/demo.mp3")
      .then((r) => r.blob())
      .then((blob) => upload(new File([blob], "示例片段（C-Am-F-G）.mp3", { type: "audio/mpeg" })))
      .catch(() => showToast("示例音频加载失败", true));
  }
  $("demoBtn").addEventListener("click", loadDemo);
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) upload(fileInput.files[0]); });

  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("over"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("over"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) upload(f);
  });

  function upload(file) {
    if (!/^audio\//.test(file.type) && !/\.(mp3|wav|m4a|aac|flac|ogg|opus|wma|aiff?)$/i.test(file.name)) {
      showToast("这不是音频文件", true);
      return;
    }
    if (file.size > 60 * 1024 * 1024) {
      showToast("文件超过 60MB", true);
      return;
    }

    const dzHint = dropzone.querySelector(".dz-hint");
    dzHint.textContent = "上传中…（" + fmtSize(file.size) + "）";

    const fd = new FormData();
    fd.append("file", file);

    fetch("/api/upload", { method: "POST", body: fd })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "上传失败");
        loadIntoLab(d);
      })
      .catch((err) => showToast(err.message, true))
      .finally(() => {
        dzHint.textContent = "mp3 / wav / m4a / flac / ogg，单个不超过 60MB";
      });
  }

  // 把一段音频（上传的或曲库里的）装进变调台
  function loadIntoLab(d) {
    current = d;
    fileName.textContent = d.name;
    fileMeta.textContent = fmtSize(d.size) + " · " + fmtDur(d.duration);
    origPlayer.src = d.url;
    trackInfo.hidden = false;
    controls.hidden = false;
    result.hidden = true;
    statusEl.textContent = "";
    dropzone.hidden = true;
    syncFromKeys();
    showToast("已载入：" + d.name);
  }

  // ---------- 清空/换曲 ----------
  function resetAll() {
    current = null;
    origPlayer.pause();
    origPlayer.removeAttribute("src");
    outPlayer.pause();
    outPlayer.removeAttribute("src");
    trackInfo.hidden = true;
    controls.hidden = true;
    result.hidden = true;
    dropzone.hidden = false;
    semiRange.value = 0;
    fromKeySel.value = "7";
    toKeySel.value = "3";
    dirSel.value = "auto";
    statusEl.textContent = "";
    syncFromKeys();
  }
  resetBtn.addEventListener("click", resetAll);
  newShiftBtn.addEventListener("click", () => {
    result.hidden = true;
    statusEl.textContent = "已清空结果，调个新的半音再变一次。";
    window.scrollTo({ top: document.getElementById("lab").offsetTop - 20, behavior: "smooth" });
  });

  // ---------- 半音控制 ----------
  semiRange.addEventListener("input", syncFromSlider);
  fromKeySel.addEventListener("change", syncFromKeys);
  toKeySel.addEventListener("change", syncFromKeys);
  dirSel.addEventListener("change", syncFromKeys);
  document.querySelectorAll(".quick button").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.step === "reset") {
        semiRange.value = 0;
      } else {
        // 快捷按钮是“增量”还是“绝对值”？这里做成叠加，更符合直觉
        const cur = Number(semiRange.value);
        const next = cur + Number(btn.dataset.step);
        semiRange.value = Math.max(-12, Math.min(12, next));
      }
      // 快捷按钮动的是半音数，所以反过来推导目标调
      syncFromSlider();
    });
  });

  // ---------- 变调 ----------
  transposeBtn.addEventListener("click", () => {
    if (!current) { showToast("先上传一首歌", true); return; }
    const n = Number(semiRange.value);
    if (n === 0) { showToast("原调和目标调是同一个，换一个目标调", true); return; }

    transposeBtn.disabled = true;
    transposeBtn.textContent = "变调中…";
    statusEl.textContent = "ffmpeg 正在处理，几秒到几十秒，别关页面。";

    const t0 = Date.now();
    fetch("/api/transpose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: current.id, semitones: n }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "变调失败");
        outPlayer.src = d.url + "?t=" + Date.now();
        downloadBtn.href = d.download;
        // 用服务端给的好名字，别让浏览器叫成 1795131557_xxx.mp3
        downloadBtn.setAttribute("download", d.filename || "");
        resultBadge.textContent = (n > 0 ? "+" : "") + n + " 半音" +
          (d.duration ? " · " + fmtDur(d.duration) : "");
        result.hidden = false;
        statusEl.textContent = "完成，用时 " + (d.seconds ?? ((Date.now() - t0) / 1000).toFixed(1)) + " 秒。原曲长度没变，只是整体升高/降低了 " + Math.abs(n) + " 个半音。";
        result.scrollIntoView({ behavior: "smooth", block: "nearest" });
      })
      .catch((err) => {
        statusEl.textContent = "";
        showToast(err.message, true);
      })
      .finally(() => {
        transposeBtn.disabled = false;
        transposeBtn.textContent = "开始变调";
      });
  });

  // ---------- 添加音乐人（免登录，任何人可补充） ----------
  const addMusicianBtn = $("addMusicianBtn"), addMusicianCard = $("addMusicianCard");
  const addMusicianSubmit = $("addMusicianSubmit"), addMusicianStatus = $("addMusicianStatus");

  // 添加音乐人
  addMusicianBtn.addEventListener("click", () => {
    addMusicianCard.hidden = !addMusicianCard.hidden;
    if (!addMusicianCard.hidden) addMusicianCard.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  addMusicianSubmit.addEventListener("click", () => {
    const payload = {
      name: $("newArtistName").value.trim(),
      instrument: $("newArtistInstrument").value,
      video: $("newArtistVideo").value.trim(),
      title: $("newArtistTitle").value.trim(),
      note: $("newArtistNote").value.trim(),
    };
    if (!payload.name) { showToast("先填音乐人名字", true); return; }
    if (!payload.video) { showToast("先填视频链接或 ID", true); return; }

    addMusicianSubmit.disabled = true;
    addMusicianStatus.textContent = "提交中…";
    fetch("/api/musicians", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "添加失败");
        addMusicianStatus.textContent = "已添加：「" + d.video.title + "」，共 " + d.total + " 条视频。切到「" +
          d.video.instrument + "」就能看到。";
        $("newArtistName").value = "";
        $("newArtistVideo").value = "";
        $("newArtistTitle").value = "";
        $("newArtistNote").value = "";
        // 重新拉一次视频数据，标签会立刻多出这个音乐人
        return fetch("/api/videos").then((r) => r.json()).then((vd) => {
          videosCache = vd.videos || [];
          renderArtistChips();
          renderVideos();
        });
      })
      .catch((err) => { addMusicianStatus.textContent = ""; showToast(err.message, true); })
      .finally(() => { addMusicianSubmit.disabled = false; });
  });

  // ---------- 竖琴曲生成器 ----------
  const genMood = $("genMood"), genKey = $("genKey"), genTempo = $("genTempo");
  const genTempoVal = $("genTempoVal"), genLen = $("genLen");
  const genBtn = $("genBtn"), genStatus = $("genStatus"), genResult = $("genResult");
  const genPlayer = $("genPlayer"), genMeta = $("genMeta"), genDownload = $("genDownload");
  const genShift = $("genShift"), genAgain = $("genAgain");
  let generatedName = null;

  const MOODS = [
    { id: "温柔", tempo: 66 },
    { id: "空灵", tempo: 58 },
    { id: "明快", tempo: 92 },
    { id: "忧伤", tempo: 62 },
    { id: "电音融合", tempo: 118 },
  ];

  MOODS.forEach((m) => {
    const o = document.createElement("option");
    o.value = m.id;
    o.textContent = m.id;
    genMood.appendChild(o);
  });
  KEYS.forEach((k, i) => {
    const o = document.createElement("option");
    o.value = String(i);
    o.textContent = k.sym + "（" + k.cn + "）";
    genKey.appendChild(o);
  });

  function applyMoodTempo() {
    const m = MOODS.find((x) => x.id === genMood.value) || MOODS[0];
    genTempo.value = m.tempo;
    genTempoVal.textContent = m.tempo + " 拍/分";
  }
  genMood.addEventListener("change", applyMoodTempo);
  genTempo.addEventListener("input", () => {
    genTempoVal.textContent = genTempo.value + " 拍/分";
  });
  applyMoodTempo();

  // 生成按钮：调接口，等 1~3 秒拿回 mp3
  function doGenerate() {
    genBtn.disabled = true;
    genBtn.textContent = "生成中…";
    genStatus.textContent = "正在合成……大约 1~3 秒";
    genResult.hidden = true;

    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mood: genMood.value,
        key: Number(genKey.value),
        tempo: Number(genTempo.value),
        seconds: Number(genLen.value),
      }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "生成失败");
        generatedName = d.filename;
        genPlayer.src = d.url + "?t=" + Date.now();
        genDownload.href = d.download;
        genDownload.setAttribute("download", d.filename);
        genMeta.textContent = [
          d.info.key,
          d.info.tempo + " 拍/分",
          d.info.progression,
          "约 " + d.info.requested + " 秒",
          "用时 " + d.seconds_taken + " 秒",
          "seed " + d.info.seed,
        ].join(" · ");
        genResult.hidden = false;
        genShift.dataset.id = generatedName;
        genStatus.textContent = "生成好了，点播放试听，也可以下载或拿去变调。";
        refreshHistory();
      })
      .catch((err) => {
        genStatus.textContent = "";
        showToast(err.message, true);
      })
      .finally(() => {
        genBtn.disabled = false;
        genBtn.textContent = "生成";
      });
  }

  // 已生成的曲子：落盘后保留，可回听、下载、再变调
  const genHistory = $("genHistory"), genHistoryHead = $("genHistoryHead"), genHistoryCount = $("genHistoryCount");

  function renderHistory(tracks) {
    if (!tracks.length) {
      genHistory.hidden = true;
      genHistoryHead.hidden = true;
      return;
    }
    genHistory.hidden = false;
    genHistoryHead.hidden = false;
    genHistoryCount.textContent = tracks.length + " 首";
    genHistory.innerHTML = tracks.map((t) =>
      '<div class="score-item">' +
        '<div class="si-main"><b>' + esc(t.title) + "</b>" +
          "<p>" + esc(t.time) + (t.duration ? " · " + t.duration + " 秒" : "") + "</p></div>" +
        '<div class="vactions">' +
          '<button class="ghost sm" type="button" data-act="gplay" data-id="' + esc(t.id) +
            '" data-url="' + esc(t.url) + '" data-dl="' + esc(t.download) + '">试听</button>' +
          '<a class="ghost sm" href="' + esc(t.download) + '" download="' + esc(t.id) + '">下载</a>' +
          '<button class="ghost sm" type="button" data-act="gshift" data-id="' + esc(t.id) + '">拿去变调</button>' +
        "</div>" +
      "</div>"
    ).join("");
  }

  function refreshHistory() {
    return fetch("/api/generated")
      .then((r) => r.json())
      .then((d) => renderHistory(d.tracks || []))
      .catch(() => {});
  }

  genHistory.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const id = btn.dataset.id;
    if (btn.dataset.act === "gplay") {
      genPlayer.src = btn.dataset.url + "?t=" + Date.now();
      genDownload.href = btn.dataset.dl;
      genDownload.setAttribute("download", id);
      genShift.dataset.id = id;
      genResult.hidden = false;
      genPlayer.play().catch(() => {});
      genResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    if (btn.dataset.act === "gshift") {
      btn.disabled = true;
      fetch("/api/load_generated", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: id }),
      })
        .then((r) => r.json())
        .then((d) => {
          if (!d.ok) throw new Error(d.error || "载入失败");
          loadIntoLab(d);
          document.getElementById("lab").scrollIntoView({ behavior: "smooth", block: "start" });
        })
        .catch((err) => showToast(err.message, true))
        .finally(() => { btn.disabled = false; });
    }
  });

  refreshHistory();

  genBtn.addEventListener("click", doGenerate);
  genAgain.addEventListener("click", doGenerate);

  // 生成的曲子可以直接丢进变调台
  genShift.addEventListener("click", () => {
    // 优先用按钮上记录的 id（历史列表里点「试听」后就是那一首）
    const target = genShift.dataset.id || generatedName;
    if (!target) return;
    genShift.disabled = true;
    fetch("/api/load_generated", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: target }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "载入失败");
        loadIntoLab(d);
        document.getElementById("lab").scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch((err) => showToast(err.message, true))
      .finally(() => { genShift.disabled = false; });
  });

  // ---------- 竖琴专区：YouTube 官方嵌入 + 跟练建议 + 曲谱 ----------
  const videoGrid = $("videoGrid"), harpTag = $("harpTag");
  const scoreList = $("scoreList"), scoreViewer = $("scoreViewer");
  const openTips = new Set();

  function videoCard(v) {
    const open = openTips.has(v.videoId);
    const tips = v.tips || {};
    const points = (tips.points || []).map((x, i) =>
      "<li><b>" + (i + 1) + ". " + esc(x) + "</b></li>").join("");
    const steps = (tips.steps || []).map((x) => "<li>" + esc(x) + "</li>").join("");
    const listens = (tips.listenFor || []).map((x) => "<li>" + esc(x) + "</li>").join("");
    return (
      '<article class="vcard">' +
        '<div class="thumb" data-vid="' + esc(v.videoId) + '">' +
          '<img src="https://i.ytimg.com/vi/' + esc(v.videoId) + '/mqdefault.jpg" alt="' + esc(v.title) + '" />' +
          '<span class="playbtn">▶</span>' +
        "</div>" +
        "<h3>" + esc(v.title) + "</h3>" +
        '<p class="vmeta">' + esc(v.date) + (v.note ? " · " + esc(v.note) : "") + "</p>" +
        '<div class="vactions">' +
          '<button class="ghost" type="button" data-act="play" data-id="' + esc(v.videoId) + '">在页面里播放</button>' +
          '<button class="ghost accent' + (open ? " on" : "") + '" type="button" data-act="vtips" data-id="' +
            esc(v.videoId) + '">' + (open ? "收起建议" : "跟练建议") + "</button>" +
          (v.scoreUrl ? '<a class="score-link" href="' + esc(v.scoreUrl) + '" target="_blank" ' +
            'rel="noopener noreferrer" title="' + esc(v.scoreLabel || "曲谱") + '">曲谱 ↗</a>' : "") +
          '<a class="src" href="https://www.youtube.com/watch?v=' + esc(v.videoId) +
            '" target="_blank" rel="noopener noreferrer">去 YouTube ↗</a>' +
        "</div>" +
        (open
          ? '<div class="vtips">' +
              (tips.goal ? '<p class="lesson-goal">练习目标：' + esc(tips.goal) + "</p>" : "") +
              '<div class="lesson-block"><h4>跟练要点</h4><ul class="points">' + points + "</ul></div>" +
              '<div class="lesson-block"><h4>练习步骤</h4><ul class="listens">' + steps + "</ul></div>" +
              '<div class="lesson-block"><h4>听的时候注意</h4><ul class="listens">' + listens + "</ul></div>" +
            "</div>"
          : "") +
      "</article>"
    );
  }

  // 三层导航：乐器（横）→ 演奏者（横）→ 栏目（纵）
  let currentInstrument = "竖琴";
  let currentArtist = "全部";
  let currentSection = "视频";

  function visibleVideos() {
    return videosCache.filter((v) =>
      (v.instrument || "竖琴") === currentInstrument &&
      (currentArtist === "全部" || v.artist === currentArtist)
    );
  }

  function renderVideos() {
    const list = visibleVideos();
    harpTag.textContent = currentInstrument + " · " +
      (currentArtist === "全部" ? "全部演奏者" : currentArtist) + " · " + list.length + " 个";

    if (!list.length) {
      videoGrid.innerHTML = '<p class="empty">这个演奏者名下还没有视频。把视频加进 ' +
        '<code>data/videos.json</code>，写上 <code>"instrument": "' + esc(currentInstrument) +
        '"</code> 和 <code>"artist"</code>，刷新就会出现。</p>';
      return;
    }

    // 按演奏者分组，同类的放在一起
    const order = [];
    const groups = {};
    list.forEach((v) => {
      const a = v.artist || "其他";
      if (!groups[a]) { groups[a] = []; order.push(a); }
      groups[a].push(v);
    });
    videoGrid.innerHTML = order.map((a) =>
      '<h4 class="artist-head">' + esc(a) + ' <span class="tag">' + groups[a].length + " 个</span></h4>" +
      groups[a].map(videoCard).join("")
    ).join("");
  }

  function setActiveChip(row, btn) {
    row.querySelectorAll(".fchip").forEach((b) => b.classList.toggle("active", b === btn));
  }

  const axisInstrument = $("axisInstrument"), axisArtist = $("axisArtist"), axisSection = $("axisSection");
  const secVideos = $("secVideos"), secGen = $("secGen"), secScores = $("secScores");

  // 演奏者标签：只列当前乐器下的人，数据里加新 artist 就自动多一个
  function renderArtistChips() {
    const artists = [];
    videosCache.forEach((v) => {
      if ((v.instrument || "竖琴") !== currentInstrument) return;
      if (v.artist && artists.indexOf(v.artist) < 0) artists.push(v.artist);
    });
    if (currentArtist !== "全部" && artists.indexOf(currentArtist) < 0) currentArtist = "全部";

    const chips = [{ name: "全部", label: "全部演奏者" }].concat(
      artists.map((a) => ({ name: a, label: a }))
    );
    axisArtist.innerHTML = chips.map((c) =>
      '<button class="fchip' + (c.name === currentArtist ? " active" : "") +
      '" type="button" data-artist="' + esc(c.name) + '">' + esc(c.label) + "</button>"
    ).join("");
  }

  // 点乐器：重置演奏者，重新出标签
  axisInstrument.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-instrument]");
    if (!btn) return;
    currentInstrument = btn.dataset.instrument;
    currentArtist = "全部";
    setActiveChip(axisInstrument, btn);
    renderArtistChips();
    renderVideos();
  });

  axisArtist.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-artist]");
    if (!btn) return;
    currentArtist = btn.dataset.artist;
    setActiveChip(axisArtist, btn);
    renderVideos();
  });

  // 栏目：演奏视频 / 生成（含电音融合）/ 曲谱
  axisSection.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-section]");
    if (!btn) return;
    const sec = btn.dataset.section;
    setActiveChip(axisSection, btn);
    currentSection = sec;

    secVideos.hidden = sec !== "视频";
    secGen.hidden = sec !== "生成";
    secScores.hidden = sec !== "曲谱";
    if (sec === "生成") {
      genStatus.textContent = "五种风格：温柔 / 空灵 / 明快 / 忧伤 / 电音融合（带四拍底鼓）。";
    }
    renderVideos();
  });

  function playVideo(id) {
    const thumb = videoGrid.querySelector('.thumb[data-vid="' + CSS.escape(id) + '"]');
    if (!thumb) return;
    thumb.classList.add("playing");
    thumb.innerHTML =
      '<iframe src="https://www.youtube-nocookie.com/embed/' + encodeURIComponent(id) +
      '?autoplay=1&rel=0" title="Sarah Bhalla 竖琴视频" allow="autoplay; encrypted-media; picture-in-picture" ' +
      'allowfullscreen loading="lazy"></iframe>';
  }

  videoGrid.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    const thumb = e.target.closest(".thumb");
    const id = (btn && btn.dataset.id) || (thumb && thumb.dataset.vid);
    if (!id) return;
    const act = btn ? btn.dataset.act : "play";
    if (act === "play") { playVideo(id); return; }
    if (act === "vtips") {
      if (openTips.has(id)) openTips.delete(id);
      else openTips.add(id);
      renderVideos();
    }
  });

  let videosCache = [];
  fetch("/api/videos")
    .then((r) => r.json())
    .then((d) => {
      videosCache = d.videos || [];
      renderArtistChips();
      renderVideos();
    })
    .catch(() => { videoGrid.innerHTML = '<p class="empty">视频列表加载失败</p>'; });

  // 曲谱：本地文件在页面里看，外链在新标签打开
  function scoreItem(sc) {
    const tag = sc.license ? '<span class="chip">' + esc(sc.license) + "</span>" : "";
    const note = sc.note ? "<p>" + esc(sc.note) + "</p>" : "";
    const action = sc.kind === "file"
      ? '<button class="ghost sm" type="button" data-act="view" data-url="' + esc(sc.url) +
        '" data-pdf="' + (sc.isPdf ? "1" : "0") + '" data-title="' + esc(sc.title) + '">查看</button>'
      : '<a class="ghost sm" href="' + esc(sc.url) + '" target="_blank" rel="noopener noreferrer">打开 ↗</a>';
    return (
      '<div class="score-item">' +
        '<div class="si-main"><b>' + esc(sc.title) + "</b> " + tag + note + "</div>" +
        action +
      "</div>"
    );
  }

  function renderScores(scores) {
    if (!scores.length) {
      scoreList.innerHTML = '<p class="empty">还没有曲谱。把 PDF 丢进 <code>scores/</code> 目录就出现了。</p>';
      return;
    }
    scoreList.innerHTML = scores.map(scoreItem).join("");
  }

  scoreList.addEventListener("click", (e) => {
    const btn = e.target.closest('[data-act="view"]');
    if (!btn) return;
    const url = btn.dataset.url;
    $("svTitle").textContent = btn.dataset.title || "曲谱";
    $("svBody").innerHTML = btn.dataset.pdf === "1"
      ? '<iframe src="' + esc(url) + '" title="曲谱"></iframe>'
      : '<img src="' + esc(url) + '" alt="曲谱" />';
    scoreViewer.hidden = false;
    scoreViewer.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  $("svClose").addEventListener("click", () => {
    scoreViewer.hidden = true;
    $("svBody").innerHTML = "";
  });

  fetch("/api/scores")
    .then((r) => r.json())
    .then((d) => renderScores(d.scores || []))
    .catch(() => { scoreList.innerHTML = '<p class="empty">曲谱列表加载失败</p>'; });

  // ---------- 活动：江浙沪竖琴 / 古筝音乐会 ----------
  const eventCities = $("eventCities"), eventInstruments = $("eventInstruments");
  let eventsCache = [];
  let eventCity = "全部";
  let eventInstrument = "全部";
  let eventsFetchedAt = "";

  function todayStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  function weekdayCn(dateStr) {
    const d = new Date(dateStr + "T00:00:00");
    if (isNaN(d.getTime())) return "";
    return "周" + "日一二三四五六"[d.getDay()];
  }

  function eventCard(e) {
    const past = e.date < todayStr();
    const poster = e.poster
      ? '<div class="thumb"><img src="' + esc(e.poster) + '" alt="' + esc(e.title) + ' 海报" /></div>'
      : "";
    const when = [e.date, weekdayCn(e.date), e.time].filter(Boolean).join(" ");
    const where = [e.city, e.venue].filter(Boolean).join(" · ");
    const tags = (e.tags || []).map((t) => '<span class="chip">' + esc(t) + "</span>").join("");
    const badge = past ? '<span class="chip">已结束</span>' : '<span class="chip">可报名</span>';
    const btn = e.url
      ? '<a class="ghost sm" href="' + esc(e.url) + '" target="_blank" rel="noopener noreferrer">' +
        (past ? "看回顾 ↗" : "报名 / 购票 ↗") + "</a>"
      : "";
    const src = e.source
      ? '<span>来源：' + esc(e.source) + "</span>"
      : "";

    return (
      '<article class="event" data-city="' + esc(e.city) + '">' +
        poster +
        '<div class="event-top">' +
          "<h3>" + esc(e.title) + "</h3>" +
          '<span class="event-date">' + esc(when) + "</span>" +
        "</div>" +
        (e.summary ? "<p>" + esc(e.summary) + "</p>" : "") +
        '<div class="event-foot">' +
          (where ? "<span>" + esc(where) + "</span>" : "") +
          (e.price ? "<span>" + esc(e.price) + "</span>" : "") +
          badge + tags + src +
          (btn ? " " + btn : "") +
        "</div>" +
      "</article>"
    );
  }

  // 乐器标签按数据自动生成
  function renderEventInstrumentChips() {
    const kinds = [];
    eventsCache.forEach((e) => {
      const k = e.instrument || "其他";
      if (kinds.indexOf(k) < 0) kinds.push(k);
    });
    if (eventInstrument !== "全部" && kinds.indexOf(eventInstrument) < 0) eventInstrument = "全部";
    const chips = [{ name: "全部", label: "全部乐器" }].concat(kinds.map((k) => ({ name: k, label: k })));
    eventInstruments.innerHTML = chips.map((c) =>
      '<button class="fchip' + (c.name === eventInstrument ? " active" : "") +
      '" type="button" data-einst="' + esc(c.name) + '">' + esc(c.label) + "</button>"
    ).join("");
  }

  function renderEvents() {
    const list = eventsCache
      .filter((e) => eventCity === "全部" || e.city === eventCity)
      .filter((e) => eventInstrument === "全部" || (e.instrument || "其他") === eventInstrument)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));

    const scope = [eventCity === "全部" ? "" : eventCity,
                   eventInstrument === "全部" ? "" : eventInstrument].filter(Boolean).join(" · ");
    eventCount.textContent = (scope ? scope + " · " : "") + list.length + " / " + eventsCache.length + " 场";

    if (eventsFetchedAt) {
      const hint = document.getElementById("eventHint");
      if (hint && hint.dataset.updated !== eventsFetchedAt) {
        hint.dataset.updated = eventsFetchedAt;
        hint.insertAdjacentHTML("beforeend",
          ' <span class="chip">数据更新于 ' + esc(eventsFetchedAt) + "</span>");
      }
    }

    if (!list.length) {
      eventList.innerHTML = '<p class="empty">这个城市暂时没有可核实的场次。' +
        "把活动加进 <code>data/events.json</code>，或者告诉我链接，我来核实收录。</p>";
      return;
    }
    eventList.innerHTML = list.map(eventCard).join("");
  }

  eventInstruments.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-einst]");
    if (!btn) return;
    eventInstrument = btn.dataset.einst;
    eventInstruments.querySelectorAll(".fchip").forEach((b) => b.classList.toggle("active", b === btn));
    renderEvents();
  });

  eventCities.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-city]");
    if (!btn) return;
    eventCity = btn.dataset.city;
    eventCities.querySelectorAll(".fchip").forEach((b) => b.classList.toggle("active", b === btn));
    renderEvents();
  });

  fetch("/api/events")
    .then((r) => r.json())
    .then((d) => {
      eventsCache = d.events || [];
      eventsFetchedAt = d.fetchedAt || "";
      renderEventInstrumentChips();
      renderEvents();
    })
    .catch(() => { eventList.innerHTML = '<p class="empty">活动数据加载失败</p>'; });

  syncFromKeys();

  // 带 ?demo=1 打开时自动载入示例，方便直接看效果
  if (location.search.indexOf("demo=1") >= 0) loadDemo();
})();
