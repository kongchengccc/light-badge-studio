/* =========================================================================
   灯牌渲染引擎
   把「分析出来的 project.json」渲染成和原视频一致的动态画面。
   文字 / 头像 / 字体 / 配色 全部可编辑。
   ========================================================================= */
(function (global) {
  "use strict";

  const DEFAULTS = {
    text: { content: "", sub: "", y: 520, size: 66, maxWidth: 600, spacing: 1,
            fillTop: "#ffffff", fillBot: "#fffbe8", stroke: "#241a10", glow: "#c8ff55",
            strokeW: 1.2, glowBlur: 5, glowAlpha: 0.8, fatten: 7, shadow: 0.35,
            glowPulse: 0.12, subSize: 26, subY: 592, font: "zcool",
            iconsFollow: true, iconGap: 10 },
    motion: { enabled: true, period: 2.33, grid: null },
    particles: { enabled: true, speed: 25, angle: 0, density: 140, size: 1, color: [94, 175, 231] },
    shine: { enabled: true, amount: 0.4, speed: 110, bands: 2, angle: 0.22 },
    render: { fps: 30, duration: 2.44, bg: "transparent" },
  };

  const FONT_STACKS = {
    zcool: '"ZCOOL QingKe HuangYou"',
    system: '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Source Han Sans SC","Noto Sans SC",sans-serif',
    serif: '"Songti SC","STSong","SimSun",serif',
    round: '"Yuanti SC","YouYuan","幼圆",sans-serif',
    custom: '"MyCustomFont"',
  };

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function smoothstep(a, b, x) {
    const t = Math.min(1, Math.max(0, (x - a) / Math.max(1e-6, b - a)));
    return t * t * (3 - 2 * t);
  }

  class Engine {
    constructor(canvas) {
      this.cv = canvas;
      this.ctx = canvas.getContext("2d", { willReadFrequently: true });
      this.cfg = clone(DEFAULTS);
      this.imgs = {};
      this.parts = null;
      this.warp = null;
      this.glowCv = document.createElement("canvas");
      this.glowCtx = this.glowCv.getContext("2d");
      this.shCv = document.createElement("canvas");
      this.shCtx = this.shCv.getContext("2d");
      this.warpCv = document.createElement("canvas");
      this.warpCtx = this.warpCv.getContext("2d");
      this.fontLoaded = false;
      this.onFontReady = null;
    }

    /* ---------------- 字体 ---------------- */
    async loadFont(url) {
      try {
        const ff = new FontFace("ZCOOL QingKe HuangYou", `url(${url})`);
        await ff.load();
        document.fonts.add(ff);
        this.fontLoaded = true;
        if (this.onFontReady) this.onFontReady();
      } catch (e) { console.warn("字体加载失败", e); }
    }

    fontCss() { return FONT_STACKS[this.cfg.text.font] || FONT_STACKS.system; }
    fontWeight() { return this.cfg.text.font === "zcool" ? 400 : 900; }

    /* ---------------- 载入工程 ---------------- */
    async load(project, baseUrl) {
      const p = project || {};
      const t = p.text || {};
      this.cfg = clone(DEFAULTS);
      Object.assign(this.cfg.text, t);
      Object.assign(this.cfg.motion, p.motion || {});
      Object.assign(this.cfg.particles, p.particles || {});
      Object.assign(this.cfg.shine, p.shine || {});
      Object.assign(this.cfg.render, p.render || {});
      this.canvasW = (p.canvas && p.canvas.w) || 960;
      this.canvasH = (p.canvas && p.canvas.h) || 720;
      this.cv.width = this.canvasW; this.cv.height = this.canvasH;
      this.warpCv.width = this.canvasW; this.warpCv.height = this.canvasH;

      const A = (p.assets || {});
      const load = (url) => new Promise((res) => {
        if (!url) return res(null);
        const im = new Image();
        im.onload = () => res(im); im.onerror = () => res(null);
        im.src = baseUrl + url;
      });
      const [badge, avatar, ...icons] = await Promise.all([
        load(A.badge), load(A.avatar),
        ...(A.icons || []).map(i => load(i.file)),
      ]);
      this.imgs.badge = badge; this.imgs.avatar = avatar;
      this.imgs.icons = (A.icons || []).map((meta, i) => ({ meta, img: icons[i] })).filter(x => x.img);
      this.buildParticles();
      this.buildWarp();
      return this;
    }

    /* ---------------- 粒子 ---------------- */
    buildParticles() {
      const p = this.cfg.particles;
      const rnd = mulberry32(20261030);
      this.parts = [];
      const n = Math.max(0, Math.round(p.density || 0));
      for (let i = 0; i < n; i++) {
        const depth = rnd();
        this.parts.push({
          x0: rnd() * this.canvasW,
          y: Math.pow(rnd(), 0.72) * this.canvasH,
          r: (0.6 + Math.pow(depth, 1.8) * 5.0) * (p.size || 1),
          sp: 0.45 + depth * 1.15,
          al: 0.20 + depth * 0.72,
          hue: 198 + rnd() * 22,
          ph: rnd() * Math.PI * 2,
        });
      }
    }

    drawParticles(t) {
      const p = this.cfg.particles;
      if (!p.enabled || !this.parts) return;
      const ctx = this.ctx;
      const ang = (p.angle || 0) * Math.PI / 180;
      const vx = Math.cos(ang) * p.speed, vy = Math.sin(ang) * p.speed;
      const span = this.canvasW + 160;
      for (const q of this.parts) {
        let x = (q.x0 + vx * t * q.sp) % span; if (x < 0) x += span; x -= 80;
        let y = (q.y + vy * t * q.sp) % this.canvasH; if (y < 0) y += this.canvasH;
        y += Math.sin(t * 0.6 + q.ph) * 2.2;
        if (y < -20 || y > this.canvasH + 20) continue;
        const g = ctx.createRadialGradient(x, y, 0, x, y, q.r * 1.9);
        g.addColorStop(0, `hsla(${q.hue},100%,80%,${q.al})`);
        g.addColorStop(0.38, `hsla(${q.hue},95%,60%,${q.al * 0.5})`);
        g.addColorStop(1, `hsla(${q.hue},95%,55%,0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, q.r * 1.9, 0, 6.2832); ctx.fill();
        if (q.r > 2.2) {
          ctx.fillStyle = `hsla(${q.hue},100%,94%,${q.al * 0.95})`;
          ctx.beginPath(); ctx.arc(x, y, q.r * 0.5, 0, 6.2832); ctx.fill();
        }
      }
    }

    /* ---------------- 运动场（分析测得的 4 通道位移） ---------------- */
    buildWarp() {
      const m = this.cfg.motion;
      const g = m.grid;
      this.warp = null;
      if (!m.enabled || !g || !g.data) return;
      const W = this.canvasW, H = this.canvasH;
      const gw = g.w, gh = g.h;
      const AX = new Float32Array(W * H), AY = new Float32Array(W * H);
      // 把粗网格的双线性插值展开成逐像素场
      for (let y = 0; y < H; y++) {
        const fy = (y / H) * gh - 0.5;
        const y0 = Math.max(0, Math.min(gh - 1, Math.floor(fy)));
        const y1 = Math.max(0, Math.min(gh - 1, y0 + 1));
        const ty = Math.min(1, Math.max(0, fy - y0));
        for (let x = 0; x < W; x++) {
          const fx = (x / W) * gw - 0.5;
          const x0 = Math.max(0, Math.min(gw - 1, Math.floor(fx)));
          const x1 = Math.max(0, Math.min(gw - 1, x0 + 1));
          const tx = Math.min(1, Math.max(0, fx - x0));
          const i = y * W + x;
          for (let c = 0; c < 4; c++) {
            const v00 = g.data[y0][x0][c], v10 = g.data[y0][x1][c];
            const v01 = g.data[y1][x0][c], v11 = g.data[y1][x1][c];
            const v = (v00 * (1 - tx) + v10 * tx) * (1 - ty) + (v01 * (1 - tx) + v11 * tx) * ty;
            if (c === 0) AX[i] = v; else if (c === 2) AY[i] = v;
          }
        }
      }
      this.warp = { AX, AY };
    }

    warpFrame(t) {
      if (!this.warp || !this.imgs.badge) return;
      const W = this.canvasW, H = this.canvasH;
      const pre = this.badgeData;      // 已是预乘好的 Uint8ClampedArray
      if (!pre) return;
      const { AX, AY } = this.warp;
      const w = 2 * Math.PI / Math.max(0.15, this.cfg.motion.period || 2.33);
      const cosW = Math.cos(w * t), sinW = Math.sin(w * t);
      const out = this.warpCtx.createImageData(W, H);
      const dst = out.data;
      for (let i = 0, px = 0; i < W * H; i++, px += 4) {
        const dx = AX[i] * cosW + AX[i + 1] * sinW;
        const dy = AY[i] * cosW + AY[i + 1] * sinW;
        const fx = (i % W) - dx, fy = ((i / W) | 0) - dy;
        let ix = fx | 0, iy = fy | 0;
        if (ix < 0) ix = 0; if (iy < 0) iy = 0;
        if (ix > W - 2) ix = W - 2; if (iy > H - 2) iy = H - 2;
        const tx = fx - ix, ty = fy - iy;
        const w00 = (1 - tx) * (1 - ty), w10 = tx * (1 - ty), w01 = (1 - tx) * ty, w11 = tx * ty;
        const o00 = (iy * W + ix) * 4, o10 = o00 + 4, o01 = o00 + W * 4, o11 = o01 + 4;
        let r = pre[o00] * w00 + pre[o10] * w10 + pre[o01] * w01 + pre[o11] * w11;
        let g = pre[o00 + 1] * w00 + pre[o10 + 1] * w10 + pre[o01 + 1] * w01 + pre[o11 + 1] * w11;
        let b = pre[o00 + 2] * w00 + pre[o10 + 2] * w10 + pre[o01 + 2] * w01 + pre[o11 + 2] * w11;
        let a = pre[o00 + 3] * w00 + pre[o10 + 3] * w10 + pre[o01 + 3] * w01 + pre[o11 + 3] * w11;
        if (a > 0.5) { const k = 255 / a; r *= k; g *= k; b *= k; }
        dst[px] = r; dst[px + 1] = g; dst[px + 2] = b; dst[px + 3] = a;
      }
      this.warpCtx.putImageData(out, 0, 0);
    }

    ensureBadgeData() {
      if (this.badgeData || !this.imgs.badge) return;
      const c = document.createElement("canvas");
      c.width = this.canvasW; c.height = this.canvasH;
      const g = c.getContext("2d", { willReadFrequently: true });
      g.drawImage(this.imgs.badge, 0, 0);
      const d = g.getImageData(0, 0, this.canvasW, this.canvasH).data;
      // 预乘 alpha，避免双线性插值时透明像素串色
      const pre = new Uint8ClampedArray(d.length);
      for (let i = 0; i < d.length; i += 4) {
        const a = d[i + 3];
        pre[i] = d[i] * a / 255; pre[i + 1] = d[i + 1] * a / 255;
        pre[i + 2] = d[i + 2] * a / 255; pre[i + 3] = a;
      }
      this.badgeData = pre;
    }

    /* ---------------- 主体 ---------------- */
    drawBadge(t) {
      const badge = this.imgs.badge;
      if (!badge) return;
      this.ensureBadgeData();
      if (this.cfg.motion.enabled && this.warp) {
        this.warpFrame(t);
        this.ctx.drawImage(this.warpCv, 0, 0);
      } else {
        this.ctx.drawImage(badge, 0, 0);
      }
      // 头像：默认美术层里已经含有原头像，只有用户替换后才叠加
      if (this.cfg.avatarOverride && this.imgs.avatar) {
        const av = this.cfg.avatarRect;
        if (av) this.ctx.drawImage(this.imgs.avatar, av.x, av.y, av.w, av.h);
        else this.ctx.drawImage(this.imgs.avatar, 0, 0);
      }
    }

    /* ---------------- 流光 ---------------- */
    drawShine(t) {
      const s = this.cfg.shine;
      if (!s.enabled || !s.amount || !this.imgs.badge) return;
      const W = this.canvasW, H = this.canvasH;
      this.shCv.width = W; this.shCv.height = H;
      const c = this.shCtx;
      c.clearRect(0, 0, W, H);
      const ang = (s.angle || 0) * Math.PI / 180, span = W + 900;
      for (let b = 0; b < (s.bands || 2); b++) {
        const off = ((t * s.speed + b * span / (s.bands || 2)) % span) - 450;
        c.save(); c.translate(off, 0); c.rotate(ang);
        const g = c.createLinearGradient(-260, 0, 260, 0);
        g.addColorStop(0, "rgba(255,255,255,0)");
        g.addColorStop(0.5, "rgba(255,255,255,1)");
        g.addColorStop(1, "rgba(255,255,255,0)");
        c.fillStyle = g; c.fillRect(-260, -2600, 520, 5200);
        c.restore();
      }
      c.globalCompositeOperation = "destination-in";
      c.drawImage(this.imgs.badge, 0, 0);
      c.globalCompositeOperation = "source-over";
      this.ctx.save();
      this.ctx.globalCompositeOperation = "lighter";
      this.ctx.globalAlpha = s.amount;
      this.ctx.drawImage(this.shCv, 0, 0);
      this.ctx.restore();
    }

    /* ---------------- 文字 ---------------- */
    measureLines() {
      const T = this.cfg.text;
      return (T.content || "").split("\n").filter(x => x.length);
    }
    fitFont() {
      const T = this.cfg.text;
      const lines = this.measureLines();
      if (!lines.length) return T.size;
      const c = this.ctx;
      const measure = (sz) => {
        c.font = `${this.fontWeight()} ${sz}px ${this.fontCss()}`;
        let w = 0;
        for (const ln of lines) {
          let ww = c.measureText(ln).width;
          if ("letterSpacing" in c) ww += T.spacing * Math.max(0, ln.length - 1);
          if (ww > w) w = ww;
        }
        return w;
      };
      let size = T.size;
      if (T.fit) {
        const nat = measure(size);
        if (nat > 1) size = Math.max(16, Math.min(220, size * T.maxWidth / nat));
      }
      for (let i = 0; i < 80; i++) {
        if (measure(size) <= T.maxWidth || size <= 16) break;
        size -= 1;
      }
      return size;
    }
    textBounds() {
      const T = this.cfg.text;
      const lines = this.measureLines();
      if (!lines.length) return { left: this.canvasW / 2, right: this.canvasW / 2 };
      const size = this.fitFont();
      const c = this.ctx;
      c.font = `${this.fontWeight()} ${size}px ${this.fontCss()}`;
      let w = 0;
      for (const ln of lines) {
        let ww = c.measureText(ln).width;
        if ("letterSpacing" in c) ww += T.spacing * Math.max(0, ln.length - 1);
        if (ww > w) w = ww;
      }
      const pad = T.fatten / 2 + T.strokeW + T.glowBlur * 0.35;
      return { left: this.canvasW / 2 - w / 2 - pad, right: this.canvasW / 2 + w / 2 + pad };
    }
    drawText(t) {
      const T = this.cfg.text;
      const lines = this.measureLines();
      if (!lines.length) return;
      const size = this.fitFont();
      const lh = size * 1.12;
      const y0 = T.y - (lines.length - 1) * lh / 2;
      const fs = `${this.fontWeight()} ${size}px ${this.fontCss()}`;
      const W = this.canvasW, H = this.canvasH;

      // 光晕
      this.glowCv.width = W; this.glowCv.height = H;
      const gc = this.glowCtx;
      gc.clearRect(0, 0, W, H);
      gc.font = fs; gc.textAlign = "center"; gc.textBaseline = "middle";
      if ("letterSpacing" in gc) gc.letterSpacing = T.spacing + "px";
      gc.shadowColor = T.glow; gc.shadowBlur = T.glowBlur; gc.fillStyle = T.glow;
      for (const ln of lines) { gc.fillText(ln, W / 2, y0); gc.fillText(ln, W / 2, y0); }
      const pulse = 1 - (T.glowPulse || 0) + (T.glowPulse || 0) * Math.sin(t * 3.1);
      this.ctx.save();
      this.ctx.globalCompositeOperation = "lighter";
      this.ctx.globalAlpha = (T.glowAlpha || 0.6) * pulse;
      this.ctx.drawImage(this.glowCv, 0, 0);
      this.ctx.restore();

      // 描边 + 渐变填充
      const ctx = this.ctx;
      ctx.save();
      ctx.font = fs; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      if ("letterSpacing" in ctx) ctx.letterSpacing = T.spacing + "px";
      if (T.shadow > 0) { ctx.shadowColor = `rgba(0,0,0,${T.shadow})`; ctx.shadowBlur = 10; ctx.shadowOffsetY = 5; }
      ctx.lineJoin = "round"; ctx.miterLimit = 2;
      const g = ctx.createLinearGradient(0, y0 - size * 0.62, 0, y0 + size * 0.62);
      g.addColorStop(0, T.fillTop); g.addColorStop(0.5, "#fffdf4"); g.addColorStop(1, T.fillBot);
      if (T.fatten > 0) {
        ctx.lineWidth = T.fatten; ctx.strokeStyle = g;
        for (const ln of lines) ctx.strokeText(ln, W / 2, y0);
      }
      ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      if (T.strokeW > 0) {
        ctx.lineWidth = T.fatten + T.strokeW * 2; ctx.strokeStyle = T.stroke;
        for (const ln of lines) ctx.strokeText(ln, W / 2, y0);
      }
      ctx.fillStyle = g;
      for (const ln of lines) ctx.fillText(ln, W / 2, y0);
      ctx.restore();

      // 副标题
      if (T.sub && T.sub.trim()) {
        ctx.save();
        ctx.font = `${this.fontWeight()} ${T.subSize}px ${this.fontCss()}`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        if ("letterSpacing" in ctx) ctx.letterSpacing = "1px";
        ctx.shadowColor = "rgba(0,0,0,.5)"; ctx.shadowBlur = 8; ctx.shadowOffsetY = 3;
        ctx.lineWidth = 3; ctx.lineJoin = "round"; ctx.strokeStyle = "rgba(30,20,10,.85)";
        ctx.strokeText(T.sub, W / 2, T.subY);
        ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
        ctx.fillStyle = "#ffe9a8"; ctx.fillText(T.sub, W / 2, T.subY);
        ctx.restore();
      }
    }

    /* ---------------- 图标 ---------------- */
    drawIcons(t) {
      const list = this.imgs.icons || [];
      if (!list.length) return;
      const T = this.cfg.text;
      const b = this.textBounds();
      let left = null, right = null;
      for (const it of list) {
        if (it.meta.x + it.meta.w / 2 < this.canvasW / 2) {
          if (!left || it.meta.x < left.meta.x) left = it;
        } else {
          if (!right || it.meta.x > right.meta.x) right = it;
        }
      }
      for (const [it, side] of [[left, "L"], [right, "R"]]) {
        if (!it) continue;
        let x = it.meta.x, y = it.meta.y;
        if (T.iconsFollow && side === "L") x = Math.max(4, b.left - (T.iconGap || 10) - it.meta.w);
        if (T.iconsFollow && side === "R") x = Math.min(this.canvasW - it.meta.w - 4, b.right + (T.iconGap || 10));
        this.ctx.save();
        this.ctx.globalAlpha = 0.9 + 0.1 * Math.sin(t * 3.1 + (side === "L" ? 0 : 1));
        this.ctx.drawImage(it.img, x, y, it.meta.w, it.meta.h);
        this.ctx.restore();
      }
    }

    /* ---------------- 主渲染 ---------------- */
    render(t) {
      const ctx = this.ctx;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, this.canvasW, this.canvasH);
      if (this.cfg.render.bg !== "transparent") {
        ctx.fillStyle = this.cfg.render.bg; ctx.fillRect(0, 0, this.canvasW, this.canvasH);
      }
      this.drawParticles(t);
      this.drawBadge(t);
      this.drawShine(t);
      this.drawIcons(t);
      this.drawText(t);
    }

    setText(k, v) { this.cfg.text[k] = v; }
    setMotion(k, v) { this.cfg.motion[k] = v; this.buildWarp(); }
    setParticles(k, v) { this.cfg.particles[k] = v; this.buildParticles(); }
    setShine(k, v) { this.cfg.shine[k] = v; }
    setRender(k, v) { this.cfg.render[k] = v; }
    replaceAvatar(img) { this.imgs.avatar = img; }
  }

  global.BadgeEngine = { Engine, DEFAULTS, FONT_STACKS };
})(window);
