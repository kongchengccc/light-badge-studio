# 部署指南

代码已经在 GitHub 上了（`main` 分支，CI 绿）。剩下的是**把服务跑起来**。

GitHub 只托管代码，不跑常驻服务，所以要分两半：

```
┌─ 前端（静态）─┐   ┌─ 后端（FastAPI）─┐
│  upload/分析/编辑 │ ←→ │  逆向分析 + 服务端渲染 │
└────────────────┘   └───────────────────┘
   Pages / Vercel        Render / Fly / 自建
```

---

## 一、后端（必须，这是核心）

### 方式 A：Render（推荐，一键）

仓库里带了 `render.yaml` + `Dockerfile`：

1. 打开 <https://render.com> → **New → Blueprint**
2. 选 `kongchengccc/light-badge-studio` → Apply
3. Render 会读 `render.yaml`，自动用 Dockerfile 构建
4. 拿到地址，形如 `https://light-badge-studio.onrender.com`

> 免费版冷启动慢（约 1 分钟），第一次分析会等一会儿。

### 方式 B：Fly.io

```bash
fly launch --copy-config --no-deploy
fly deploy
```

### 方式 C：自己的服务器

```bash
git clone git@github.com:kongchengccc/light-badge-studio.git
cd light-badge-studio
docker compose up -d
```

> 服务端渲染需要 **Chrome** 和 **ffmpeg**，Dockerfile 里都装好了。

---

## 二、前端

### 方式 A：GitHub Pages（需你点一次）

Actions 里已经有一个 `Publish to gh-pages branch` 工作流，
每次 push 会自动把前端产物推到 `gh-pages` 分支。

**你只需要去仓库设置里拉一个下拉框：**

1. 打开 <https://github.com/kongchengccc/light-badge-studio/settings/pages>
   （页面样式可能因为网络问题不显示，但**功能是好的**，照着文字找就行）
2. **Build and deployment → Source** 选 **Deploy from a branch**
3. **Branch** 选 `gh-pages`，目录选 `/ (root)`，Save
4. 几十秒后站点地址就出现在 **Pages** 页顶部

> 另一条路：`Deploy Pages` 工作流用的是官方 Pages API，
> 但 `GITHUB_TOKEN` 无权创建 Pages 站点（GitHub 限制），
> 所以**必须先手动启用一次**，之后那条工作流也能正常工作。

### 方式 B：Vercel / Netlify（也一键）

仓库里已经带了 `vercel.json` / `netlify.toml`：

- Vercel：<https://vercel.com/new> → 导入仓库 → Root Directory 填 `frontend`
- Netlify：<https://app.netlify.com> → Add new site → Import → Base 填 `frontend`

### 接上后端

前端要知道自己要调哪个后端。两种方式：

**A. 改代码（推荐，Pages 每次构建都会带上）**

编辑 `frontend/js/config.js`：

```js
window.API_BASE = "https://light-badge-studio.onrender.com";
```

提交后 push，Pages 自动重新部署。

**B. 用仓库变量（不用改代码）**

仓库 **Settings → Secrets and variables → Actions → Variables** 里加一个
`API_BASE` = 你的后端地址，`Publish to gh-pages branch` 工作流会自动写进产物。

---

## 三、验证

```bash
curl https://你的后端/api/health
# {"ok":true,"ffmpeg":true,"chrome":true,"projects":0}
```

打开前端 → 点「加载示例工程」→ 能进编辑器就说明前后端通了。

---

## 四、常见问题

| 现象 | 原因 / 解决 |
|---|---|
| Pages 一直失败 | 正常，必须先在 Settings 里手动启用一次（见上文） |
| 后端分析超时 | Render 免费版冷启动，第一次可能要等 1 分钟 |
| 服务端渲染失败 | 后端环境缺 Chrome 或 ffmpeg → 用 Docker 部署，或确认 `render.yaml` 生效 |
| 前端提示「Failed to fetch」 | `API_BASE` 没填或填错，或后端没起来 |
| 网页打开是「无样式」的 | 你的代理把 `githubassets.com` 挡了（跟本项目无关），换个节点或加直连规则 |
