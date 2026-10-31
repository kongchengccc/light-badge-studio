/* 后端 API 封装 */
(function (global) {
  "use strict";
  const BASE = (global.API_BASE || "").replace(/\/$/, "");

  async function req(path, opts) {
    const res = await fetch(BASE + path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("json") ? res.json() : res.text();
  }

  const api = {
    base: BASE,
    async analyze(file, onProgress) {
      const fd = new FormData();
      fd.append("video", file);
      // fetch 没有上传进度，用 XHR
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", BASE + "/api/analyze");
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total, "上传中");
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText)); }
            catch (e) { reject(new Error("返回解析失败")); }
          } else {
            let msg = xhr.statusText;
            try { msg = JSON.parse(xhr.responseText).detail || msg; } catch (e) {}
            reject(new Error(msg));
          }
        };
        xhr.onerror = () => reject(new Error("网络错误"));
        xhr.send(fd);
      });
    },
    project: (id) => req("/api/projects/" + id),
    saveProject: (id, project) => req("/api/projects/" + id, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(project),
    }),
    fonts: () => req("/api/fonts"),
    render: (id, opts) => req("/api/projects/" + id + "/render", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(opts),
    }),
    job: (jid) => req("/api/jobs/" + jid),
    assetUrl: (id, rel) => BASE + "/api/projects/" + id + "/file/" + rel,
    sample: () => req("/api/sample"),
  };
  global.api = api;
})(window);
