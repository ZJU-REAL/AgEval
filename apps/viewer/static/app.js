/* BORA local Database viewer SPA (no build step). */
(() => {
  const state = {
    db: null,
    taskId: null,
    detail: null,
    tree: null,
    activeTab: "readme",
    activeFile: null,
  };

  const $ = (id) => document.getElementById(id);

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 1600);
  }

  async function api(path) {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Minimal markdown → HTML (headers, code fences, inline code, paragraphs). */
  function renderMarkdown(src) {
    if (!src) return '<p class="muted">No content</p>';
    const lines = src.replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let i = 0;
    let inCode = false;
    let codeLang = "";
    let codeBuf = [];
    let para = [];

    const flushPara = () => {
      if (!para.length) return;
      const text = para.join(" ");
      out.push(`<p>${inline(text)}</p>`);
      para = [];
    };

    const inline = (t) =>
      escapeHtml(t)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    while (i < lines.length) {
      const line = lines[i];
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        if (inCode) {
          out.push(
            `<pre><code class="lang-${escapeHtml(codeLang)}">${escapeHtml(
              codeBuf.join("\n")
            )}</code></pre>`
          );
          codeBuf = [];
          inCode = false;
          codeLang = "";
        } else {
          flushPara();
          inCode = true;
          codeLang = fence[1] || "";
        }
        i += 1;
        continue;
      }
      if (inCode) {
        codeBuf.push(line);
        i += 1;
        continue;
      }
      if (/^\s*$/.test(line)) {
        flushPara();
        i += 1;
        continue;
      }
      const h = line.match(/^(#{1,3})\s+(.*)$/);
      if (h) {
        flushPara();
        const level = h[1].length;
        out.push(`<h${level}>${inline(h[2])}</h${level}>`);
        i += 1;
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        flushPara();
        const items = [];
        while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
          items.push(`<li>${inline(lines[i].replace(/^[-*]\s+/, ""))}</li>`);
          i += 1;
        }
        out.push(`<ul>${items.join("")}</ul>`);
        continue;
      }
      para.push(line.trim());
      i += 1;
    }
    if (inCode) {
      out.push(`<pre><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`);
    }
    flushPara();
    return `<div class="prose">${out.join("\n")}</div>`;
  }

  function renderCommands(container, commands, keys) {
    container.innerHTML = "";
    const entries = keys
      ? keys.map((k) => [k, commands[k]]).filter(([, v]) => v)
      : Object.entries(commands || {});
    for (const [label, cmd] of entries) {
      const wrap = document.createElement("div");
      wrap.className = "cmd";
      wrap.innerHTML = `<code title="${escapeHtml(label)}">${escapeHtml(cmd)}</code>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Copy";
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(cmd);
          toast("Copied");
        } catch {
          toast("Copy failed");
        }
      });
      wrap.appendChild(btn);
      container.appendChild(wrap);
    }
  }

  function setTab(name) {
    state.activeTab = name;
    document.querySelectorAll(".tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === name);
    });
    ["readme", "instruction", "files", "yaml"].forEach((t) => {
      $(`tab-${t}`).classList.toggle("hidden", t !== name);
    });
  }

  function renderTreeNode(node, ul) {
    if (!node) return;
    if (node.type === "dir") {
      const li = document.createElement("li");
      const label = document.createElement("div");
      label.className = "dir-label";
      label.textContent = node.path === "." || !node.path ? node.name : node.name + "/";
      li.appendChild(label);
      const childUl = document.createElement("ul");
      (node.children || []).forEach((c) => renderTreeNode(c, childUl));
      li.appendChild(childUl);
      ul.appendChild(li);
      return;
    }
    if (node.type === "truncated") {
      const li = document.createElement("li");
      li.innerHTML = `<span class="muted">${escapeHtml(node.message || "truncated")}</span>`;
      ul.appendChild(li);
      return;
    }
    if (node.type === "file") {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = node.name;
      btn.dataset.path = node.path;
      if (state.activeFile === node.path) btn.classList.add("active");
      btn.addEventListener("click", () => openFile(node.path));
      li.appendChild(btn);
      ul.appendChild(li);
    }
  }

  async function openFile(relPath) {
    state.activeFile = relPath;
    const preview = $("file-preview");
    preview.innerHTML = `<div class="muted">Loading ${escapeHtml(relPath)}…</div>`;
    // refresh active class
    document.querySelectorAll(".file-tree button").forEach((b) => {
      b.classList.toggle("active", b.dataset.path === relPath);
    });
    try {
      const data = await api(
        `/api/tasks/${encodeURIComponent(state.taskId)}/file?path=${encodeURIComponent(relPath)}`
      );
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.innerHTML = `<span>${escapeHtml(data.path)}</span><span>${data.size} bytes</span><span>${escapeHtml(
        data.kind
      )}${data.language ? " · " + escapeHtml(data.language) : ""}</span>`;
      preview.innerHTML = "";
      preview.appendChild(meta);
      if (data.kind === "text" && data.content != null) {
        if (data.language === "markdown") {
          const wrap = document.createElement("div");
          wrap.innerHTML = renderMarkdown(data.content);
          preview.appendChild(wrap);
        } else {
          const pre = document.createElement("pre");
          pre.textContent = data.content;
          preview.appendChild(pre);
        }
      } else if (data.kind === "image" && data.content_base64) {
        const img = document.createElement("img");
        img.alt = data.name;
        img.src = `data:${data.mime || "image/png"};base64,${data.content_base64}`;
        preview.appendChild(img);
      } else {
        const p = document.createElement("p");
        p.className = "muted";
        p.textContent = data.message || "No preview";
        preview.appendChild(p);
      }
    } catch (err) {
      preview.innerHTML = `<p class="muted">${escapeHtml(err.message)}</p>`;
    }
  }

  async function selectTask(taskId) {
    state.taskId = taskId;
    state.activeFile = null;
    document.querySelectorAll("#task-list button").forEach((b) => {
      b.classList.toggle("active", b.dataset.id === taskId);
    });
    $("empty").classList.add("hidden");
    $("detail").classList.remove("hidden");
    $("task-title").textContent = taskId;

    const [detail, tree] = await Promise.all([
      api(`/api/tasks/${encodeURIComponent(taskId)}`),
      api(`/api/tasks/${encodeURIComponent(taskId)}/tree`),
    ]);
    state.detail = detail;
    state.tree = tree;

    renderCommands($("task-cmds"), detail.commands, ["run_task", "lock_task"]);

    const readme = $("tab-readme");
    if (detail.readme) {
      readme.innerHTML =
        `<div class="meta muted" style="margin-bottom:8px">${escapeHtml(detail.readme.path)}</div>` +
        renderMarkdown(detail.readme.content);
    } else {
      readme.innerHTML = '<p class="muted">No README found in this task directory.</p>';
    }

    const instruction = $("tab-instruction");
    if (detail.instruction) {
      instruction.innerHTML =
        `<div class="meta muted" style="margin-bottom:8px">${escapeHtml(
          detail.instruction.path
        )}</div>` + renderMarkdown(detail.instruction.content);
    } else {
      instruction.innerHTML =
        '<p class="muted">No instruction.md (or data/instruction.md) found.</p>';
    }

    const yaml = $("tab-yaml");
    if (detail.task_yaml) {
      yaml.innerHTML = `<pre>${escapeHtml(detail.task_yaml)}</pre>`;
    } else {
      yaml.innerHTML = '<p class="muted">task.yaml unavailable</p>';
    }

    const treeRoot = $("file-tree");
    treeRoot.innerHTML = "";
    const ul = document.createElement("ul");
    renderTreeNode(tree.tree, ul);
    treeRoot.appendChild(ul);
    $("file-preview").innerHTML = '<div class="muted">Select a file</div>';

    setTab(state.activeTab === "files" ? "files" : "readme");
  }

  async function init() {
    document.querySelectorAll(".tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.dataset.tab));
    });

    try {
      const db = await api("/api/database");
      state.db = db;
      $("db-meta").innerHTML = `
        <div><strong>${escapeHtml(db.database_id)}</strong> @ ${escapeHtml(db.version)}</div>
        <div>${db.task_count} tasks · ${escapeHtml(db.tasks_root || "tasks")}</div>
        ${db.description ? `<div style="margin-top:6px">${escapeHtml(db.description)}</div>` : ""}
        <div style="margin-top:6px;word-break:break-all">${escapeHtml(db.root)}</div>
      `;
      const list = $("task-list");
      list.innerHTML = "";
      for (const id of db.task_ids || []) {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = id;
        btn.dataset.id = id;
        btn.addEventListener("click", () => selectTask(id).catch((e) => toast(e.message)));
        li.appendChild(btn);
        list.appendChild(li);
      }
      renderCommands($("suite-cmd-list"), db.commands, ["tasks", "run_suite", "lock_suite_hint"]);
    } catch (err) {
      $("db-meta").textContent = err.message;
      toast(err.message);
    }
  }

  init();
})();
