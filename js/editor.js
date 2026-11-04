/* 编辑器 UI */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const engine = new window.BadgeEngine.Engine($("#c"));

  let project = null, projectId = null, playing = true, t0 = performance.now(), curT = 0;
  let fonts = [];

  function toast(m, ms) {
    const t = $("#toast"); t.textContent = m; t.style.display = "block";
    clearTimeout(t._t); t._t = setTimeout(() => (t.style.display = "none"), ms || 2600);
  }

  /* ---------------- 上传 ---------------- */
  const drop = $("#drop"), fileInput = $("#file");
  drop.onclick = () => fileInput.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => {
    e.preventDefault(); drop.classList.remove("over");
    if (e.dataTransfer.files[0]) doUpload(e.dataTransfer.files[0]);
  };
  fileInput.onchange = () => { if (fileInput.files[0]) doUpload(fileInput.files[0]); };

  async function doUpload(file) {
    const prog = $("#progress"), bar = prog.querySelector("i"), step = prog.querySelector(".step");
    const err = $("#landingErr");
    err.classList.add("hidden"); prog.classList.remove("hidden");
    try {
      const res = await api.analyze(file, (pct, msg) => {
        bar.style.width = (pct * 40) + "%"; step.textContent = msg;
      });
      step.textContent = "分析中（运动场测量较慢，约 20~60 秒）…";
      bar.style.width = "55%";
      // 分析在服务端同步完成，这里轮询拿进度提示
      const id = res.id;
      const t = setInterval(async () => {
        try {
          const st = await api.job(res.job || "");
          if (st && st.step) step.textContent = st.step + "（" + st.percent + "%）";
        } catch (e) { /* 忽略 */ }
      }, 1200);
      clearInterval(t);
      bar.style.width = "100%";
      await openProject(res.id, res.project);
    } catch (e) {
      err.textContent = "分析失败：" + e.message;
      err.classList.remove("hidden");
      prog.classList.add("hidden");
      bar.style.width = "0%";
    }
  }

  /* ---------------- 打开工程 ---------------- */
  async function openProject(id, proj) {
    projectId = id;
    project = proj || await api.project(id);
    await engine.load(project, api.assetUrl(id, ""));
    applyConfigToUI();
    $("#landing").classList.add("hidden");
    $("#studio").classList.remove("hidden");
    const s = project.source || {};
    $("#metaInfo").textContent = `${s.width}×${s.height} · ${(s.duration || 0).toFixed(2)}s · ${s.fps}fps`;
    if (!engine.fontLoaded) {
      const f = fonts.find(x => x.key === "zcool");
      if (f) engine.loadFont(f.url).then(() => { engine.cfg.text.font = "zcool"; applyConfigToUI(); renderNow(); });
    }
    renderNow();
  }

  /* ---------------- UI 绑定 ---------------- */
  const TEXT_MAP = {
    f_text: "content", f_sub: "sub", f_size: "size", f_spacing: "spacing",
    f_maxw: "maxWidth", f_texty: "y", f_font: "font", f_subsize: "subSize", f_suby: "subY",
    f_ftop: "fillTop", f_fbot: "fillBot", f_stroke: "stroke", f_glow: "glow",
    f_sw: "strokeW", f_fatten: "fatten", f_gb: "glowBlur", f_galpha: "glowAlpha", f_sh: "shadow",
    f_fit: "fit",
  };
  const MOTION_MAP = { f_motion: "enabled", f_mper: "period" };
  const PART_MAP = { f_part: "enabled", f_pspeed: "speed", f_pangle: "angle", f_pcount: "density", f_psize: "size" };
  const SHINE_MAP = { f_shine: "enabled", f_shamt: "amount", f_shspd: "speed" };
  const OUT_MAP = { f_dur: "duration", f_fps: "fps" };

  function applyConfigToUI() {
    const T = engine.cfg.text, M = engine.cfg.motion, P = engine.cfg.particles,
      S = engine.cfg.shine, R = engine.cfg.render;
    const set = (id, v) => { const el = $("#" + id); if (!el) return;
      if (el.type === "checkbox") el.checked = !!v; else el.value = v; };
    for (const id in TEXT_MAP) set(id, T[TEXT_MAP[id]]);
    for (const id in MOTION_MAP) set(id, M[MOTION_MAP[id]]);
    for (const id in PART_MAP) set(id, P[PART_MAP[id]]);
    for (const id in SHINE_MAP) set(id, S[SHINE_MAP[id]]);
    for (const id in OUT_MAP) set(id, R[OUT_MAP[id]]);
    set("f_cw", engine.canvasW); set("f_ch", engine.canvasH);
    $("#v_sw").textContent = T.strokeW; $("#v_ft").textContent = T.fatten;
    $("#v_gb").textContent = T.glowBlur; $("#v_ga").textContent = T.glowAlpha;
    $("#v_sh").textContent = T.shadow;
    // 头像框
    const av = project && project.detected && project.detected.avatar;
    if (av) {
      const r = { x: Math.round(av.cx - av.rx), y: Math.round(av.cy - av.ry), w: Math.round(av.rx * 2), h: Math.round(av.ry * 2) };
      engine.cfg.avatarRect = r;
      $("#f_avx").value = r.x; $("#f_avy").value = r.y;
      $("#f_avw").value = r.w; $("#f_avh").value = r.h;
      $("#avatarInfo").textContent = `椭圆 ${r.w}×${r.h} @ (${r.x},${r.y}) — 可拖动数值或换图`;
    }
    if ($("#f_mamp")) $("#f_mamp").value = 1;
  }

  function bind(id, kind, obj) {
    const el = $("#" + id); if (!el) return;
    el.addEventListener("input", () => {
      let v = el.value;
      if (el.type === "checkbox") v = el.checked;
      else if (el.type === "number" || el.type === "range") v = parseFloat(v) || 0;
      if (kind === "text") engine.setText(obj, v);
      else if (kind === "motion") { engine.setMotion(obj, v); if (obj === "enabled") engine.buildWarp(); }
      else if (kind === "particles") engine.setParticles(obj, v);
      else if (kind === "shine") engine.setShine(obj, v);
      else if (kind === "render") { engine.setRender(obj, v); }
      const T = engine.cfg.text;
      $("#v_sw").textContent = T.strokeW; $("#v_ft").textContent = T.fatten;
      $("#v_gb").textContent = T.glowBlur; $("#v_ga").textContent = T.glowAlpha;
      $("#v_sh").textContent = T.shadow;
      renderNow();
    });
  }
  for (const id in TEXT_MAP) bind(id, "text", TEXT_MAP[id]);
  for (const id in MOTION_MAP) bind(id, "motion", MOTION_MAP[id]);
  for (const id in PART_MAP) bind(id, "particles", PART_MAP[id]);
  for (const id in SHINE_MAP) bind(id, "shine", SHINE_MAP[id]);
  for (const id in OUT_MAP) bind(id, "render", OUT_MAP[id]);

  $("#f_cw").addEventListener("input", () => {
    const w = parseInt($("#f_cw").value) || 960, h = parseInt($("#f_ch").value) || 720;
    engine.canvasW = w; engine.canvasH = h;
    engine.cv.width = w; engine.cv.height = h;
    engine.buildParticles(); engine.buildWarp(); engine.badgeData = null;
    renderNow();
  });
  $("#f_ch").addEventListener("input", () => $("#f_cw").dispatchEvent(new Event("input")));

  /* 字体 */
  async function loadFonts() {
    try { fonts = await api.fonts(); } catch (e) { fonts = []; }
    const sel = $("#f_font");
    sel.innerHTML = fonts.map(f => `<option value="${f.key}">${f.name}</option>`).join("");
    if (!fonts.length) sel.innerHTML = '<option value="system">系统字体</option>';
    sel.addEventListener("change", () => {
      const f = fonts.find(x => x.key === sel.value);
      if (f && f.url) engine.loadFont(f.url).then(renderNow);
      else renderNow();
    });
  }
  $("#f_fontfile").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const ff = new FontFace("MyCustomFont", await f.arrayBuffer());
      await ff.load(); document.fonts.add(ff);
      engine.cfg.text.font = "custom"; $("#f_font").value = "custom"; renderNow();
      toast("字体已加载：" + f.name);
    } catch (err) { toast("字体加载失败"); }
  });

  /* 头像 */
  $("#f_avatar").addEventListener("change", (e) => {
    const f = e.target.files[0]; if (!f) return;
    const url = URL.createObjectURL(f);
    const img = new Image();
    img.onload = () => {
      const r = engine.cfg.avatarRect || { x: 0, y: 0, w: 125, h: 151 };
      const c = document.createElement("canvas"); c.width = r.w; c.height = r.h;
      const g = c.getContext("2d");
      g.save(); g.beginPath(); g.ellipse(r.w / 2, r.h / 2, r.w / 2, r.h / 2, 0, 0, 6.2832); g.clip();
      const s = Math.max(r.w / img.width, r.h / img.height);
      g.drawImage(img, (r.w - img.width * s) / 2, (r.h - img.height * s) / 2, img.width * s, img.height * s);
      g.restore();
      engine.replaceAvatar(c);
      engine.cfg.avatarOverride = true;
      renderNow(); toast("头像已替换");
    };
    img.src = url;
  });
  ["f_avx", "f_avy", "f_avw", "f_avh"].forEach(id => {
    $("#" + id).addEventListener("input", () => {
      const r = engine.cfg.avatarRect || { x: 0, y: 0, w: 125, h: 151 };
      r.x = parseInt($("#f_avx").value) || 0; r.y = parseInt($("#f_avy").value) || 0;
      r.w = parseInt($("#f_avw").value) || r.w; r.h = parseInt($("#f_avh").value) || r.h;
      engine.cfg.avatarRect = r; renderNow();
    });
  });

  /* 播放 */
  function renderNow() { engine.render(curT); }
  function loop(now) {
    if (playing) {
      curT = (now - t0) / 1000 % (engine.cfg.render.duration || 2.44);
      engine.render(curT);
      $("#scrub").value = Math.round(curT / (engine.cfg.render.duration || 2.44) * 1000);
      $("#timeLabel").textContent = curT.toFixed(2) + "s";
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
  $("#btnPlay").onclick = () => {
    playing = !playing;
    $("#btnPlay").textContent = playing ? "⏸" : "▶";
    if (playing) t0 = performance.now() - curT * 1000;
  };
  $("#scrub").addEventListener("input", () => {
    curT = (parseInt($("#scrub").value) / 1000) * (engine.cfg.render.duration || 2.44);
    engine.render(curT);
  });
  $("#chkAlpha").addEventListener("change", (e) => {
    $(".checker").classList.toggle("on", e.target.checked);
  });

  /* ---------------- 导出 ---------------- */
  function crc32(u8) {
    const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    let r = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) r = t[(r ^ u8[i]) & 0xFF] ^ (r >>> 8);
    return (r ^ 0xFFFFFFFF) >>> 0;
  }
  function makeZip(files) {
    const enc = new TextEncoder(), chunks = [], central = []; let off = 0;
    const dt = new Date();
    const dosT = ((dt.getHours() << 11) | (dt.getMinutes() << 5) | (dt.getSeconds() >> 1)) & 0xFFFF;
    const dosD = ((dt.getFullYear() - 1980) << 9) | ((dt.getMonth() + 1) << 5) | dt.getDate();
    for (const f of files) {
      const nb = enc.encode(f.name), crc = crc32(f.data), len = f.data.length;
      const lh = new Uint8Array(30 + nb.length), dv = new DataView(lh.buffer);
      dv.setUint32(0, 0x04034b50, true); dv.setUint16(4, 20, true); dv.setUint16(6, 0x0800, true);
      dv.setUint16(10, dosT, true); dv.setUint16(12, dosD, true); dv.setUint32(14, crc, true);
      dv.setUint32(18, len, true); dv.setUint32(22, len, true); dv.setUint16(26, nb.length, true);
      lh.set(nb, 30); chunks.push(lh, f.data);
      const ch = new Uint8Array(46 + nb.length), cv = new DataView(ch.buffer);
      cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
      cv.setUint16(8, 0x0800, true); cv.setUint16(12, dosT, true); cv.setUint16(14, dosD, true);
      cv.setUint32(16, crc, true); cv.setUint32(20, len, true); cv.setUint32(24, len, true);
      cv.setUint16(28, nb.length, true); cv.setUint32(42, off, true); ch.set(nb, 46);
      central.push(ch); off += lh.length + len;
    }
    let cdSize = 0; central.forEach(c => cdSize += c.length);
    const end = new Uint8Array(22), ev = new DataView(end.buffer);
    ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, central.length, true);
    ev.setUint16(10, central.length, true); ev.setUint32(12, cdSize, true); ev.setUint32(16, off, true);
    return new Blob([...chunks, ...central, end], { type: "application/zip" });
  }
  $("#b_zip").onclick = async () => {
    const n = Math.round((engine.cfg.render.duration || 2.44) * (engine.cfg.render.fps || 30));
    const files = [], st = $("#status");
    st.textContent = `正在生成 ${n} 帧…`;
    for (let i = 0; i < n; i++) {
      engine.render(i / (engine.cfg.render.fps || 30));
      const blob = await new Promise(r => engine.cv.toBlob(r, "image/png"));
      files.push({ name: "frames/" + String(i + 1).padStart(4, "0") + ".png", data: new Uint8Array(await blob.arrayBuffer()) });
      if (i % 6 === 0) { st.textContent = `正在生成 ${i + 1}/${n}`; await new Promise(r => setTimeout(r)); }
    }
    const zip = makeZip(files), a = document.createElement("a");
    a.href = URL.createObjectURL(zip); a.download = "灯牌帧序列.zip"; a.click();
    st.textContent = `✅ 已导出 ${n} 帧（${(zip.size / 1048576).toFixed(1)} MB）`;
  };
  $("#b_webm").onclick = () => {
    const st = $("#status");
    if (!window.MediaRecorder || !engine.cv.captureStream) { st.textContent = "❌ 浏览器不支持 WebM 录制"; return; }
    const stream = engine.cv.captureStream(engine.cfg.render.fps || 30);
    const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find(t => MediaRecorder.isTypeSupported(t));
    if (!mime) { st.textContent = "❌ 不支持 WebM"; return; }
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 12e6 });
    const parts = []; rec.ondataavailable = e => { if (e.data.size) parts.push(e.data); };
    rec.onstop = () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob(parts, { type: mime })); a.download = "灯牌.webm"; a.click();
      st.textContent = "✅ WebM 已导出（浏览器录制可能丢透明通道，正式交付用服务端渲染）";
    };
    playing = true; t0 = performance.now(); rec.start();
    setTimeout(() => rec.stop(), (engine.cfg.render.duration || 2.44) * 1000);
    st.textContent = "录制中…";
  };

  /* 服务端渲染 */
  $("#btnExport").onclick = () => $("#exportModal").classList.remove("hidden");
  $("#ex_cancel").onclick = () => $("#exportModal").classList.add("hidden");
  $("#ex_go").onclick = async () => {
    const st = $("#exStatus");
    const formats = [];
    if ($("#ex_mp4").checked) formats.push("mp4");
    if ($("#ex_mov").checked) formats.push("mov");
    if ($("#ex_gif").checked) formats.push("gif");
    if ($("#ex_webm").checked) formats.push("webm");
    if (!formats.length) { st.textContent = "至少选一个格式"; return; }
    st.textContent = "提交中…";
    try {
      const body = {
        formats,
        name: $("#ex_name").value || "灯牌",
        project: { ...project, ...exportProject() },
      };
      const job = await api.render(projectId, body);
      st.textContent = "渲染中…（无头 Chrome 逐帧渲染，通常 1~3 分钟）";
      const timer = setInterval(async () => {
        try {
          const s = await api.job(job.id);
          st.textContent = `${s.step || "渲染中"} ${s.percent || 0}%` +
            (s.done ? ` — 完成：${(s.outputs || []).join(", ")}` : "");
          if (s.done || s.error) { clearInterval(timer); }
        } catch (e) { clearInterval(timer); }
      }, 1500);
    } catch (e) {
      st.textContent = "提交失败：" + e.message;
    }
  };

  function exportProject() {
    const e = engine.cfg;
    return {
      text: e.text, motion: e.motion, particles: e.particles, shine: e.shine,
      render: e.render, canvas: { w: e.canvasW, h: e.canvasH },
      avatarRect: e.avatarRect,
    };
  }
  $("#btnSave").onclick = async () => {
    try {
      await api.saveProject(projectId, { ...project, ...exportProject() });
      toast("✅ 工程已保存到服务端");
    } catch (e) { toast("保存失败：" + e.message); }
  };
  $("#btnNewVideo").onclick = () => {
    $("#studio").classList.add("hidden"); $("#landing").classList.remove("hidden");
  };
  $(".sample").onclick = async () => {
    const btn = $(".sample");
    btn.disabled = true;
    try {
      const s = await api.sample();
      if (s.project) { await openProject(s.id, s.project); return; }
      toast("正在分析内置示例，约 40 秒…");
      btn.textContent = "分析中…";
      const timer = setInterval(async () => {
        try {
          const st = await api.job(s.job);
          btn.textContent = `${st.step || "分析中"} ${st.percent || 0}%`;
          if (st.error) { clearInterval(timer); toast("失败：" + st.error); btn.disabled = false; btn.textContent = "加载示例工程"; }
          if (st.done && st.projectId) {
            clearInterval(timer);
            await openProject(st.projectId);
            btn.disabled = false; btn.textContent = "加载示例工程";
          }
        } catch (e) { clearInterval(timer); btn.disabled = false; }
      }, 1200);
    } catch (e) { toast("示例加载失败：" + e.message); btn.disabled = false; }
  };

  /* ---------------- 启动 ---------------- */
  (async () => {
    await loadFonts();
    $("#f_font").addEventListener("change", () => { }, { once: true });
  })();
})();
