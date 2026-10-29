(function () {
  "use strict";

  /* ---------- helpers ---------- */
  var root = document.getElementById("app");
  var S = { user: null, cfg: null, tools: [], chat: null };

  function h(tag, attrs) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), v);
      else if (k === "value") e.value = v;
      else if (v === true) e.setAttribute(k, "");
      else e.setAttribute(k, v);
    }
    for (var i = 2; i < arguments.length; i++) add(e, arguments[i]);
    return e;
  }
  function add(parent, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) c.forEach(function (x) { add(parent, x); });
    else parent.appendChild(c.nodeType ? c : document.createTextNode(String(c)));
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }

  function api(method, path, body, raw) {
    var opts = { method: method, credentials: "same-origin", headers: { "X-Requested-With": "arnet-web" } };
    if (raw) { opts.body = raw.body; for (var k in raw.headers) opts.headers[k] = raw.headers[k]; }
    else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (r.status === 401 && S.user && path !== "/api/auth/login") { S.user = null; }
        return { ok: r.ok, status: r.status, data: d };
      });
    }, function () { return { ok: false, status: 0, data: { error: "Network problem. Check your connection and try again." } }; });
  }

  function toast(msg) {
    var t = h("div", { class: "toast", role: "status", text: msg });
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3500);
  }

  function go(path) { if (location.hash === "#" + path) route(); else location.hash = path; }
  function fmtDate(s) { if (!s) return ""; var d = new Date(s); return isNaN(d) ? s : d.toLocaleString(); }

  var ICONS = { chat: "AI", code: "</>", bug: "DBG", web: "WWW", search: "SRC", pen: "Aa", globe: "A→", list: "Σ", book: "EDU", brief: "BIZ", bulb: "IDE", chart: "DAT", check: "✓", image: "IMG", doc: "DOC" };
  function ico(name) { return h("span", { class: "ico", "aria-hidden": "true", text: ICONS[name] || "AI" }); }

  /* ---------- layout ---------- */
  function logo(cls) { return h("img", { src: "/static/logo.svg", alt: "", class: cls || "", width: "34", height: "34" }); }

  function toggleTheme() {
    var cur = document.documentElement.getAttribute("data-theme");
    if (!cur) cur = "dark";
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("arnet-theme", next); } catch (e) {}
  }

  function header(path) {
    var c = S.cfg || {};
    var links = [["/", "Home"], ["/tools", "Tools"], ["/about", "About"], ["/contact", "Contact"]];
    if (S.user) links = [["/app", "Chat"], ["/tools", "Tools"], ["/images", "Images"], ["/documents", "Documents"], ["/account", "Account"]].concat(S.user.role === "admin" ? [["/admin", "Admin"]] : []);
    var nav = h("nav", { class: "nav", id: "nav", "aria-label": "Main" },
      links.map(function (l) {
        var cur = path === l[0] || (l[0] !== "/" && path.indexOf(l[0] + "/") === 0);
        return h("a", { href: "#" + l[0], "aria-current": cur ? "page" : null, text: l[1] });
      }),
      h("button", { class: "link", type: "button", onclick: toggleTheme, "aria-label": "Switch between light and dark theme", text: "Theme" }),
      S.user ? h("button", { class: "link", type: "button", text: "Sign out", onclick: function () { api("POST", "/api/auth/logout", {}).then(function () { S.user = null; S.chat = null; go("/"); }); } })
        : [h("a", { href: "#/login", text: "Sign in" }), h("a", { class: "btn primary sm", href: "#/register", text: "Get started" })]);
    var menu = h("button", { class: "btn icon menu-btn", type: "button", "aria-label": "Menu", "aria-expanded": "false", text: "☰",
      onclick: function () { var o = nav.classList.toggle("open"); menu.setAttribute("aria-expanded", String(o)); } });
    return h("header", { class: "site-header" }, h("div", { class: "wrap" },
      h("a", { class: "brand", href: S.user ? "#/app" : "#/", "aria-label": (c.brand_name || "ARNET AI") + " home" }, logo(), h("span", { text: c.brand_name || "ARNET AI" })),
      menu, nav));
  }

  function footer() {
    var c = S.cfg || {};
    var brand = c.brand_name || "ARNET AI";
    return h("footer", { class: "site-footer" }, h("div", { class: "wrap" },
      h("div", { class: "cols" },
        h("div", null, h("strong", { text: brand }), h("div", { text: c.tagline || "" }), h("div", { text: "Owner: " + (c.owner_name || "") }), h("div", { text: "Built by " + (c.creator || "") })),
        h("div", null, h("div", null, "Email: ", h("a", { href: "mailto:" + (c.contact_email || ""), text: c.contact_email || "" })),
          h("div", null, "WhatsApp: ", h("a", { href: c.whatsapp_link || "#", target: "_blank", rel: "noopener noreferrer", text: c.whatsapp || "" })),
          h("div", { text: "© 2026 " + brand + ". All rights reserved." })),
        h("div", null, h("a", { href: "#/about", text: "About" }), h("br"), h("a", { href: "#/contact", text: "Contact" }), h("br"), h("a", { href: "#/tools", text: "Tools" }))),
      h("div", { class: "attrib", text: brand + " © 2026. All rights reserved. Built by " + (c.creator || "") + "." })));
  }

  function shell(path, content) {
    clear(root);
    root.appendChild(header(path));
    var main = h("main", { id: "main", tabindex: "-1" }, content);
    root.appendChild(main);
    if (!/^\/app/.test(path)) root.appendChild(footer());
    window.scrollTo(0, 0);
  }

  /* ---------- views: public ---------- */
  function toolCard(t) {
    var inner = [h("h3", null, ico(t.icon), h("span", { text: t.name }), t.available ? null : h("span", { class: "badge warn", text: "Needs setup" })),
      h("p", { text: t.description }),
      t.available ? null : h("p", { class: "hint", text: t.unavailable_reason })];
    if (!t.available) return h("div", { class: "card glass" }, inner);
    var dest = t.id === "images" ? "#/images" : t.id === "documents" ? "#/documents" : S.user ? "#/app?tool=" + t.id : "#/register";
    return h("a", { class: "card glass", href: dest }, inner);
  }

  function viewLanding() {
    var c = S.cfg;
    return h("div", { class: "view" },
      h("section", { class: "wrap hero" },
        logo("logo-big"),
        h("h1", null, h("span", { class: "grad-text", text: c.tagline.replace(/\.$/, "") + "." })),
        h("p", { class: "lead", text: c.brand_name + " puts chat, coding help, research, document analysis and image creation in one place." }),
        h("div", { class: "cta" },
          S.user ? h("a", { class: "btn primary", href: "#/app", text: "Open your chats" })
            : [h("a", { class: "btn primary", href: "#/register", text: "Create a free account" }), h("a", { class: "btn", href: "#/login", text: "Sign in" })]),
        h("p", { class: "hint", style: "margin-top:16px", text: "Free accounts include " + c.plans.free_daily_messages + " messages a day." }),
        c.ai_available ? null : h("p", { class: "err", text: "The AI service is not connected on this server yet. Chat will start working once the owner adds an AI key." })),
      h("section", { class: "wrap block" }, h("h2", { text: "Everything in one workspace" }),
        h("div", { class: "grid", id: "landing-tools" }, h("p", { class: "muted", text: "Loading tools..." }))));
  }
  function afterLanding() {
    loadTools().then(function () {
      var g = document.getElementById("landing-tools");
      if (g) clear(g).appendChild(h("div", { style: "display:contents" }, S.tools.map(toolCard)));
    });
  }

  function viewAbout() {
    var c = S.cfg;
    return h("div", { class: "wrap page view narrow", style: "max-width:720px" }, h("h1", { text: "About " + c.brand_name }),
      h("p", { class: "lead", text: c.brand_name + " is an AI-powered platform created by " + c.creator + ", bringing intelligent tools, creativity, coding assistance, and productivity together in one place." }),
      h("p", { class: "muted", text: "Owner: " + c.owner_name }));
  }

  function viewContact() {
    var c = S.cfg;
    return h("div", { class: "wrap page view narrow" }, h("h1", { text: "Contact" }),
      h("p", { class: "muted", text: "Reach the owner, " + c.owner_name + ", directly." }),
      h("div", { class: "glass pad" },
        h("p", null, h("strong", { text: "Email" }), h("br"), h("span", { class: "mono", text: c.contact_email })),
        h("p", null, h("strong", { text: "WhatsApp" }), h("br"), h("span", { class: "mono", text: c.whatsapp })),
        h("div", { class: "row-inline" },
          h("a", { class: "btn primary", href: "mailto:" + c.contact_email, text: "Send an email" }),
          c.whatsapp_link ? h("a", { class: "btn", href: c.whatsapp_link, target: "_blank", rel: "noopener noreferrer", text: "Message on WhatsApp" }) : null)));
  }

  function loadTools() {
    return api("GET", "/api/tools").then(function (r) { if (r.ok) S.tools = r.data.tools; });
  }

  function viewTools() {
    var q = h("input", { type: "search", id: "tool-q", placeholder: "Search tools", "aria-label": "Search tools" });
    var out = h("div");
    function draw() {
      var term = q.value.trim().toLowerCase();
      var list = S.tools.filter(function (t) { return !term || (t.name + " " + t.description + " " + t.category).toLowerCase().indexOf(term) >= 0; });
      clear(out);
      if (!list.length) { out.appendChild(h("p", { class: "muted", text: "No tools match your search." })); return; }
      var cats = [];
      list.forEach(function (t) { if (cats.indexOf(t.category) < 0) cats.push(t.category); });
      cats.forEach(function (cat) {
        out.appendChild(h("h2", { style: "margin-top:28px", text: cat }));
        out.appendChild(h("div", { class: "grid" }, list.filter(function (t) { return t.category === cat; }).map(toolCard)));
      });
    }
    q.addEventListener("input", draw);
    loadTools().then(draw);
    return h("div", { class: "wrap page view" }, h("h1", { text: "Tools" }),
      h("p", { class: "muted", text: "Tools marked “Needs setup” are not connected yet. They will say what is missing." }),
      h("div", { style: "max-width:420px" }, q), out);
  }

  /* ---------- views: auth ---------- */
  function authForm(opts) {
    var errBox = h("div", { class: "err", role: "alert" });
    var fields = opts.fields.map(function (f) {
      return h("div", { class: "field" }, h("label", { for: "f-" + f.name, text: f.label }),
        h("input", { id: "f-" + f.name, name: f.name, type: f.type || "text", autocomplete: f.auto || "off", required: f.required !== false, minlength: f.min, value: f.value }),
        f.hint ? h("div", { class: "hint", text: f.hint }) : null);
    });
    var btn = h("button", { class: "btn primary", type: "submit", text: opts.submit });
    var form = h("form", { novalidate: true, onsubmit: function (e) {
      e.preventDefault();
      var data = {};
      fields.forEach(function (fd) { var i = fd.querySelector("input"); data[i.name] = i.value; });
      clear(errBox); btn.disabled = true;
      opts.onSubmit(data).then(function (msg) { if (msg) { clear(errBox).textContent = msg; } btn.disabled = false; });
    } }, fields, errBox, btn);
    return form;
  }

  function afterAuth(r) {
    if (!r.ok) return r.data.error || "Something went wrong.";
    S.user = r.data.user;
    var next = (location.hash.split("next=")[1] || "");
    go(next && next.charAt(0) === "/" ? decodeURIComponent(next) : "/app");
  }

  function viewLogin() {
    return h("div", { class: "wrap page view narrow" }, h("div", { class: "glass pad" }, h("h1", { style: "font-size:2rem", text: "Sign in" }),
      authForm({ submit: "Sign in", fields: [{ name: "email", label: "Email", type: "email", auto: "username" }, { name: "password", label: "Password", type: "password", auto: "current-password" }],
        onSubmit: function (d) { return api("POST", "/api/auth/login", d).then(afterAuth); } }),
      h("p", { class: "hint", style: "margin-top:16px" }, h("a", { href: "#/forgot", text: "Forgot your password?" }), " · ", h("a", { href: "#/register", text: "Create an account" }))));
  }
  function viewRegister() {
    return h("div", { class: "wrap page view narrow" }, h("div", { class: "glass pad" }, h("h1", { style: "font-size:2rem", text: "Create your account" }),
      S.cfg.registration_open ? authForm({ submit: "Create account", fields: [{ name: "name", label: "Name (optional)", required: false, auto: "name" },
        { name: "email", label: "Email", type: "email", auto: "username" }, { name: "password", label: "Password", type: "password", auto: "new-password", min: 8, hint: "At least 8 characters." }],
        onSubmit: function (d) { return api("POST", "/api/auth/register", d).then(afterAuth); } }) : h("p", { class: "err", text: "Registration is currently closed." }),
      h("p", { class: "hint", style: "margin-top:16px" }, "Already registered? ", h("a", { href: "#/login", text: "Sign in" }))));
  }
  function viewForgot() {
    var msg = h("div", { class: "ok-msg", role: "status" });
    return h("div", { class: "wrap page view narrow" }, h("div", { class: "glass pad" }, h("h1", { style: "font-size:2rem", text: "Reset password" }),
      S.cfg.password_reset_available ? null : h("p", { class: "err", text: "Password reset email is not set up on this server. Contact the owner to reset your password." }),
      authForm({ submit: "Send reset link", fields: [{ name: "email", label: "Email", type: "email", auto: "username" }],
        onSubmit: function (d) { return api("POST", "/api/auth/forgot", d).then(function (r) { if (!r.ok) return r.data.error; msg.textContent = r.data.message; return ""; }); } }), msg));
  }
  function viewReset() {
    var token = decodeURIComponent((location.hash.split("token=")[1] || "").split("&")[0]);
    var msg = h("div", { class: "ok-msg", role: "status" });
    return h("div", { class: "wrap page view narrow" }, h("div", { class: "glass pad" }, h("h1", { style: "font-size:2rem", text: "Choose a new password" }),
      authForm({ submit: "Save password", fields: [{ name: "password", label: "New password", type: "password", auto: "new-password", min: 8 }],
        onSubmit: function (d) { return api("POST", "/api/auth/reset", { token: token, password: d.password }).then(function (r) {
          if (!r.ok) return r.data.error; msg.textContent = "Password updated. You can sign in now."; setTimeout(function () { go("/login"); }, 1200); return ""; }); } }), msg));
  }

  /* ---------- chat ---------- */
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var canSpeak = "speechSynthesis" in window;

  function speak(text) {
    if (!canSpeak) return;
    speechSynthesis.cancel();
    var plain = text.replace(/```[\s\S]*?```/g, " code block omitted. ").replace(/[*_`#>]/g, "");
    var u = new SpeechSynthesisUtterance(plain.slice(0, 4000));
    speechSynthesis.speak(u);
  }

  function openEditor(code) {
    var ta = h("textarea", { "aria-label": "HTML source", spellcheck: "false", value: code });
    var frame = h("iframe", { title: "Website preview", sandbox: "allow-scripts allow-forms allow-popups" });
    var status = h("span", { class: "hint" });
    function run() {
      status.textContent = "Loading preview...";
      api("POST", "/api/previews", { html: ta.value }).then(function (r) {
        if (!r.ok) { status.textContent = r.data.error; return; }
        frame.src = r.data.url; status.textContent = "";
      });
    }
    var close = h("button", { class: "btn sm", type: "button", text: "Close" });
    var modal = h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": "Website editor" }, h("div", { class: "panel" },
      h("header", null, h("h3", { text: "Website editor" }), status,
        h("button", { class: "btn sm primary", type: "button", text: "Run", onclick: run }),
        h("button", { class: "btn sm", type: "button", text: "Copy code", onclick: function () { if (navigator.clipboard) navigator.clipboard.writeText(ta.value).then(function () { toast("Copied"); }); } }),
        close),
      h("div", { class: "split" }, ta, frame)));
    function shut() { modal.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") shut(); }
    close.addEventListener("click", shut);
    document.addEventListener("keydown", onKey);
    document.body.appendChild(modal);
    close.focus();
    run();
  }

  function onCode(lang, code, bar) {
    if (/^(html|htm)$/i.test(lang) || /^\s*<!doctype html|^\s*<html/i.test(code)) {
      bar.insertBefore(h("button", { class: "btn", type: "button", text: "Preview / Edit", onclick: function () { openEditor(code); } }), bar.lastChild);
    }
  }

  function renderBody(body, text) { clear(body).appendChild(window.renderMarkdown(text, { onCode: onCode })); }

  function sourcesNode(sources) {
    if (!sources || !sources.length) return null;
    return h("div", { class: "sources" }, h("h4", { text: "Sources found by web search" }),
      h("ol", null, sources.map(function (s) { return h("li", null, h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer", text: s.title })); })));
  }

  function viewChat(query, convId) {
    var st = { convId: convId || null, tool: query.tool || "chat", docId: query.doc ? parseInt(query.doc, 10) : null, messages: [], busy: false, abort: null, title: "New chat", locked: false };
    var list = h("div", { class: "conv-list", role: "list" });
    var search = h("input", { type: "search", placeholder: "Search chats", "aria-label": "Search chats" });
    var msgsEl = h("div", { class: "msgs", role: "log", "aria-live": "polite", "aria-label": "Conversation" });
    var titleEl = h("h2", { text: st.title });
    var toolSel = h("select", { "aria-label": "Tool" });
    var toolBadge = h("span", { class: "badge" });
    var docSel = h("select", { id: "doc-sel", "aria-label": "Attach a document" }, h("option", { value: "", text: "No document" }));
    var searchChk = h("input", { type: "checkbox", id: "web-chk" });
    var searchLbl = h("label", { for: "web-chk" }, searchChk, "Search the web");
    var speakChk = h("input", { type: "checkbox", id: "speak-chk" });
    var input = h("textarea", { id: "msg-in", rows: "1", placeholder: "Message", "aria-label": "Message", maxlength: "8000" });
    var sendBtn = h("button", { class: "btn primary", type: "button", text: "Send" });
    var mic = SR ? h("button", { class: "btn icon", type: "button", "aria-label": "Speak your message", text: "🎤" }) : null;
    var aiDown = !S.cfg.ai_available;

    function fillTools() {
      clear(toolSel);
      S.tools.filter(function (t) { return t.id !== "images" && t.id !== "documents"; }).forEach(function (t) {
        toolSel.appendChild(h("option", { value: t.id, text: t.name + (t.available ? "" : " (needs setup)"), disabled: !t.available || null }));
      });
      toolSel.value = st.tool;
      syncTool();
    }
    function curTool() { return S.tools.filter(function (t) { return t.id === st.tool; })[0]; }
    function syncTool() {
      var t = curTool();
      input.placeholder = t && t.placeholder || "Message";
      var research = st.tool === "research";
      searchLbl.hidden = research || !S.tools.some(function (x) { return x.id === "research" && x.available; });
      toolSel.hidden = st.locked; toolBadge.hidden = !st.locked;
      toolBadge.textContent = t ? t.name : st.tool;
    }
    toolSel.addEventListener("change", function () { st.tool = toolSel.value; syncTool(); });

    function loadList() {
      var q = search.value.trim();
      return api("GET", "/api/conversations" + (q ? "?q=" + encodeURIComponent(q) : "")).then(function (r) {
        clear(list);
        if (!r.ok) return;
        if (!r.data.conversations.length) list.appendChild(h("p", { class: "hint", style: "padding:6px 10px", text: q ? "No chats match." : "No chats yet." }));
        r.data.conversations.forEach(function (c) { list.appendChild(convRow(c)); });
      });
    }
    function convRow(c) {
      var row = h("div", { class: "conv" + (c.id === st.convId ? " active" : ""), role: "listitem" });
      var link = h("a", { href: "#/app/c/" + c.id, title: c.title, text: c.title, "aria-current": c.id === st.convId ? "true" : null });
      var ren = h("button", { class: "btn sm icon", type: "button", "aria-label": "Rename chat", text: "✎", style: "width:30px;height:30px;padding:0" });
      var del = h("button", { class: "btn sm icon", type: "button", "aria-label": "Delete chat", text: "✕", style: "width:30px;height:30px;padding:0" });
      ren.addEventListener("click", function () {
        var inp = h("input", { value: c.title, "aria-label": "Chat title", maxlength: "120", style: "padding:6px 8px" });
        row.replaceChild(inp, link); inp.focus(); inp.select();
        var done = false;
        function save() {
          if (done) return; done = true;
          var v = inp.value.trim();
          if (!v || v === c.title) { loadList(); return; }
          api("PATCH", "/api/conversations/" + c.id, { title: v }).then(function (r) { if (c.id === st.convId) { st.title = v; titleEl.textContent = v; } if (!r.ok) toast(r.data.error); loadList(); });
        }
        inp.addEventListener("keydown", function (e) { if (e.key === "Enter") save(); if (e.key === "Escape") { done = true; loadList(); } });
        inp.addEventListener("blur", save);
      });
      var armed = false;
      del.addEventListener("click", function () {
        if (!armed) { armed = true; del.textContent = "Sure?"; del.style.width = "auto"; del.style.padding = "0 8px"; setTimeout(function () { armed = false; del.textContent = "✕"; del.style.width = "30px"; del.style.padding = "0"; }, 3000); return; }
        api("DELETE", "/api/conversations/" + c.id).then(function (r) {
          if (!r.ok) { toast(r.data.error); return; }
          if (c.id === st.convId) go("/app"); else loadList();
        });
      });
      row.appendChild(link); row.appendChild(ren); row.appendChild(del);
      return row;
    }

    function msgNode(m, last) {
      if (m.role === "user") return h("div", { class: "msg user", text: m.content });
      var body = h("div", { class: "body md" });
      renderBody(body, m.content);
      var actions = h("div", { class: "msg-actions" },
        h("button", { class: "btn sm", type: "button", text: "Copy", onclick: function (e) { var b = e.currentTarget; if (navigator.clipboard) navigator.clipboard.writeText(m.content).then(function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500); }); } }),
        last ? h("button", { class: "btn sm", type: "button", text: "Regenerate", onclick: regenerate }) : null,
        canSpeak ? h("button", { class: "btn sm", type: "button", text: "Listen", onclick: function () { speak(m.content); } }) : null);
      return h("div", { class: "msg bot" }, body, sourcesNode(m.sources), actions);
    }
    function drawMsgs() {
      clear(msgsEl);
      if (!st.messages.length) {
        msgsEl.appendChild(h("div", { class: "empty" }, logo("logo-big"), h("h2", { text: "How can I help?" }),
          h("p", { class: "muted", text: aiDown ? "The AI service is not connected on this server yet. The owner needs to add an AI key before chat can answer." : (curTool() ? curTool().description : "Ask anything.") })));
        return;
      }
      st.messages.forEach(function (m, i) { msgsEl.appendChild(msgNode(m, i === st.messages.length - 1 && m.role === "assistant" && !st.busy)); });
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }

    function setBusy(b) {
      st.busy = b; sendBtn.textContent = b ? "Stop" : "Send"; sendBtn.classList.toggle("primary", !b); sendBtn.classList.toggle("danger", b);
    }

    function stream(payload, userText) {
      var typing = h("div", { class: "msg bot" }, h("div", { class: "body md typing" }));
      var body = typing.firstChild, text = "", sources = [], raf = 0, errored = false;
      if (userText) st.messages.push({ role: "user", content: userText });
      drawMsgs(); msgsEl.appendChild(typing); msgsEl.scrollTop = msgsEl.scrollHeight;
      st.abort = new AbortController(); setBusy(true);
      function paint() { raf = 0; renderBody(body, text); msgsEl.scrollTop = msgsEl.scrollHeight; }
      function finish() {
        setBusy(false); st.abort = null;
        if (text && !errored) st.messages.push({ role: "assistant", content: text, sources: sources });
        drawMsgs(); loadList();
        if (text && speakChk.checked) speak(text);
      }
      fetch("/api/chat", { method: "POST", credentials: "same-origin", signal: st.abort.signal,
        headers: { "Content-Type": "application/json", "X-Requested-With": "arnet-web" }, body: JSON.stringify(payload) }).then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (d) {
            if (userText) st.messages.pop();
            if (userText) input.value = userText;
            setBusy(false); st.abort = null; drawMsgs(); toast(d.error || "Could not send your message.");
          });
        }
        var reader = res.body.getReader(), dec = new TextDecoder(), buf = "";
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) { finish(); return; }
            buf += dec.decode(r.value, { stream: true });
            var parts = buf.split("\n\n"); buf = parts.pop();
            parts.forEach(function (blk) {
              var ev = "", data = "";
              blk.split("\n").forEach(function (l) { if (l.indexOf("event: ") === 0) ev = l.slice(7); else if (l.indexOf("data: ") === 0) data += l.slice(6); });
              if (!ev) return;
              var d = {}; try { d = JSON.parse(data); } catch (e) {}
              if (ev === "meta") {
                if (!st.convId) { st.convId = d.conversation_id; st.title = d.title; titleEl.textContent = d.title; st.locked = true; st.tool = payload.tool || st.tool; syncTool(); history.replaceState(null, "", "#/app/c/" + d.conversation_id); }
              } else if (ev === "delta") { text += d.text; typing.firstChild.classList.add("typing"); if (!raf) raf = requestAnimationFrame(paint); }
              else if (ev === "sources") { sources = d; }
              else if (ev === "error") { errored = true; toast(d.message || "The AI could not answer."); typing.firstChild.classList.remove("typing"); if (!text) body.textContent = d.message || "The AI could not answer."; }
            });
            return pump();
          });
        }
        return pump();
      }).catch(function (e) { if (e && e.name === "AbortError") { if (text) st.messages.push({ role: "assistant", content: text, sources: sources }); errored = true; finish(); } else { errored = true; finish(); toast("Connection lost."); } });
    }

    function send() {
      if (st.busy) { if (st.abort) st.abort.abort(); return; }
      var text = input.value.trim();
      if (!text) return;
      var payload = { message: text, tool: st.tool };
      if (st.convId) payload.conversation_id = st.convId;
      if (docSel.value) payload.document_id = parseInt(docSel.value, 10);
      if (searchChk.checked && !searchLbl.hidden) payload.web_search = true;
      input.value = ""; input.style.height = "auto";
      stream(payload, text);
    }
    function regenerate() {
      if (st.busy || !st.convId) return;
      while (st.messages.length && st.messages[st.messages.length - 1].role === "assistant") st.messages.pop();
      var payload = { conversation_id: st.convId, regenerate: true, tool: st.tool };
      if (docSel.value) payload.document_id = parseInt(docSel.value, 10);
      stream(payload, null);
    }

    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
    input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 180) + "px"; });
    var tmr; search.addEventListener("input", function () { clearTimeout(tmr); tmr = setTimeout(loadList, 250); });
    if (mic) {
      var rec = null, listening = false;
      mic.addEventListener("click", function () {
        if (listening && rec) { rec.stop(); return; }
        rec = new SR(); rec.lang = navigator.language || "en-US"; rec.interimResults = false;
        rec.onresult = function (e) { input.value = (input.value + " " + e.results[0][0].transcript).trim(); input.dispatchEvent(new Event("input")); };
        rec.onend = function () { listening = false; mic.textContent = "🎤"; mic.setAttribute("aria-pressed", "false"); };
        rec.onerror = function () { toast("Voice input is not available right now."); };
        try { rec.start(); listening = true; mic.textContent = "⏹"; mic.setAttribute("aria-pressed", "true"); } catch (e) {}
      });
    }

    var side = h("aside", { class: "side glass", "aria-label": "Chats" },
      h("button", { class: "btn primary", type: "button", text: "+ New chat", onclick: function () { go("/app"); } }), search, list);
    var chat = h("section", { class: "chat glass", "aria-label": "Chat" },
      h("div", { class: "chat-head" }, titleEl, toolBadge, toolSel), msgsEl,
      h("div", { class: "composer" },
        h("div", { class: "row" }, input, mic, sendBtn),
        h("div", { class: "opts" }, h("span", null, "Document: ", docSel), searchLbl,
          canSpeak ? h("label", { for: "speak-chk" }, speakChk, "Read replies aloud") : null)));
    var view = h("div", { class: "wrap view" }, h("div", { class: "app-shell" }, side, chat));

    Promise.all([loadTools(), api("GET", "/api/documents")]).then(function (rs) {
      fillTools();
      if (rs[1].ok) rs[1].data.documents.forEach(function (d) { docSel.appendChild(h("option", { value: d.id, text: d.filename })); });
      if (st.docId) docSel.value = String(st.docId);
      if (st.convId) {
        api("GET", "/api/conversations/" + st.convId).then(function (r) {
          if (!r.ok) { toast("That chat could not be found."); go("/app"); return; }
          st.messages = r.data.messages; st.title = r.data.conversation.title; st.tool = r.data.conversation.tool; st.locked = true;
          titleEl.textContent = st.title; toolSel.value = st.tool; syncTool(); drawMsgs(); loadList();
        });
      } else { drawMsgs(); loadList(); input.focus(); }
    });
    return view;
  }

  /* ---------- images & documents ---------- */
  function viewImages() {
    var prompt = h("textarea", { id: "img-prompt", rows: "3", maxlength: "1000", placeholder: "Describe the image you want", "aria-label": "Image prompt" });
    var err = h("div", { class: "err", role: "alert" }), grid = h("div", { class: "img-grid" }), btn = h("button", { class: "btn primary", type: "button", text: "Generate image" });
    var unavailable = h("p", { class: "muted" });
    function load() {
      api("GET", "/api/images").then(function (r) {
        clear(grid); if (!r.ok) return;
        if (!r.data.images.length) grid.appendChild(h("p", { class: "muted", text: "Your images will appear here." }));
        r.data.images.forEach(function (im) {
          var del = h("button", { class: "btn sm danger", type: "button", text: "Delete", onclick: function () { api("DELETE", "/api/images/" + im.id).then(load); } });
          grid.appendChild(h("figure", { class: "glass" }, h("img", { src: "/api/images/" + im.id + "/file", alt: im.prompt, loading: "lazy" }),
            h("figcaption", null, h("div", { text: im.prompt }), h("div", { class: "row-inline", style: "margin-top:8px" }, h("a", { class: "btn sm", href: "/api/images/" + im.id + "/file", target: "_blank", rel: "noopener", text: "Open" }), del))));
        });
      });
    }
    btn.addEventListener("click", function () {
      clear(err);
      if (!prompt.value.trim()) { err.textContent = "Describe the image first."; return; }
      btn.disabled = true; btn.textContent = "Generating...";
      api("POST", "/api/images", { prompt: prompt.value }).then(function (r) {
        btn.disabled = false; btn.textContent = "Generate image";
        if (!r.ok) { err.textContent = r.data.error; return; }
        prompt.value = ""; load();
      });
    });
    loadTools().then(function () {
      var t = S.tools.filter(function (x) { return x.id === "images"; })[0];
      if (t && !t.available) { unavailable.textContent = "Image generation is not connected yet. " + t.unavailable_reason; btn.disabled = true; }
    });
    load();
    return h("div", { class: "wrap page view" }, h("h1", { text: "Image generator" }),
      h("div", { class: "glass pad", style: "max-width:720px;margin-bottom:24px" }, unavailable, h("div", { class: "field" }, h("label", { for: "img-prompt", text: "Prompt" }), prompt), err, btn), grid);
  }

  function viewDocuments() {
    var err = h("div", { class: "err", role: "alert" }), list = h("div", { class: "tbl-wrap" });
    var file = h("input", { type: "file", id: "doc-file", accept: ".pdf,.docx,.txt,.md,.csv,.json" });
    function load() {
      api("GET", "/api/documents").then(function (r) {
        clear(list); if (!r.ok) return;
        if (!r.data.documents.length) { list.appendChild(h("p", { class: "muted", text: "No documents yet." })); return; }
        list.appendChild(h("table", { class: "tbl" }, h("thead", null, h("tr", null, ["File", "Characters read", "Uploaded", ""].map(function (t) { return h("th", { text: t }); }))),
          h("tbody", null, r.data.documents.map(function (d) {
            return h("tr", null, h("td", { text: d.filename }), h("td", { text: d.chars.toLocaleString() }), h("td", { text: fmtDate(d.created_at) }),
              h("td", null, h("div", { class: "row-inline" }, h("a", { class: "btn sm primary", href: "#/app?tool=summarize&doc=" + d.id, text: "Analyze" }),
                h("button", { class: "btn sm danger", type: "button", text: "Delete", onclick: function () { api("DELETE", "/api/documents/" + d.id).then(load); } }))));
          }))));
      });
    }
    file.addEventListener("change", function () {
      var f = file.files[0]; if (!f) return; clear(err);
      api("POST", "/api/documents", undefined, { body: f, headers: { "X-Filename": encodeURIComponent(f.name), "Content-Type": "application/octet-stream" } }).then(function (r) {
        file.value = ""; if (!r.ok) { err.textContent = r.data.error; return; } toast("Uploaded " + r.data.document.filename); load();
      });
    });
    load();
    return h("div", { class: "wrap page view" }, h("h1", { text: "Document analysis" }),
      h("p", { class: "muted", text: "Upload a PDF, Word (.docx), text, Markdown, CSV or JSON file (up to 5 MB). Only text is read. Scanned images are not supported. Your files are private to your account." }),
      h("div", { class: "glass pad", style: "margin-bottom:24px;max-width:560px" }, h("label", { for: "doc-file", text: "Choose a file" }), file, err), list);
  }

  /* ---------- account ---------- */
  function meter(label, used, limit) {
    var pct = limit == null ? 0 : Math.min(100, Math.round(used / Math.max(limit, 1) * 100));
    return h("div", { style: "margin-bottom:14px" }, h("div", { class: "row-inline", style: "justify-content:space-between" }, h("strong", { text: label }), h("span", { class: "muted", text: used + " of " + (limit == null ? "unlimited" : limit) })),
      h("div", { class: "meter", role: "progressbar", "aria-valuenow": String(used), "aria-valuemin": "0", "aria-valuemax": String(limit == null ? used : limit), "aria-label": label }, h("i", { style: "width:" + pct + "%" })));
  }

  function viewAccount() {
    var u = S.user;
    var usageBox = h("div", null, h("p", { class: "muted", text: "Loading..." }));
    api("GET", "/api/me/usage").then(function (r) {
      if (!r.ok) return; var d = r.data;
      clear(usageBox).appendChild(h("div", null, meter("Messages today", d.messages_today, d.messages_limit), meter("Images today", d.images_today, d.images_limit),
        h("p", { class: "hint", text: d.total_requests + " AI requests in total, " + d.conversations + " chats saved. Daily counts reset at midnight UTC." })));
    });
    var nameMsg = h("div", { role: "status", class: "ok-msg" }), pwMsg = h("div", { role: "status" }), delMsg = h("div", { class: "err", role: "alert" });
    var nameIn = h("input", { id: "acc-name", value: u.name, maxlength: "60", autocomplete: "name" });
    var cur = h("input", { id: "pw-cur", type: "password", autocomplete: "current-password" }), nw = h("input", { id: "pw-new", type: "password", autocomplete: "new-password", minlength: "8" });
    var delPw = h("input", { id: "del-pw", type: "password", autocomplete: "current-password" });
    var delBtn = h("button", { class: "btn danger", type: "button", text: "Delete my account" }), armed = false;
    delBtn.addEventListener("click", function () {
      clear(delMsg);
      if (!armed) { armed = true; delBtn.textContent = "Click again to permanently delete"; return; }
      api("DELETE", "/api/me", { password: delPw.value }).then(function (r) {
        if (!r.ok) { delMsg.textContent = r.data.error; armed = false; delBtn.textContent = "Delete my account"; return; }
        S.user = null; S.chat = null; go("/");
      });
    });
    return h("div", { class: "wrap page view" }, h("h1", { text: "Account" }),
      h("div", { class: "two" },
        h("section", { class: "glass pad" }, h("h2", { text: "Profile" }),
          h("p", null, h("strong", { text: "Email: " }), u.email), h("p", null, h("strong", { text: "Plan: " }), h("span", { class: "badge ok", text: u.plan }), u.role === "admin" ? h("span", { class: "badge", text: " administrator" }) : null),
          h("div", { class: "field" }, h("label", { for: "acc-name", text: "Name" }), nameIn),
          h("button", { class: "btn primary", type: "button", text: "Save name", onclick: function () { api("PATCH", "/api/me", { name: nameIn.value }).then(function (r) { nameMsg.textContent = r.ok ? "Saved." : r.data.error; if (r.ok) S.user.name = nameIn.value; }); } }), nameMsg,
          h("p", { class: "hint", style: "margin-top:16px", text: "Pro plans are arranged with the owner. Online payment is not active yet." })),
        h("section", { class: "glass pad" }, h("h2", { text: "Usage" }), usageBox)),
      h("div", { class: "two", style: "margin-top:16px" },
        h("section", { class: "glass pad" }, h("h2", { text: "Change password" }),
          h("div", { class: "field" }, h("label", { for: "pw-cur", text: "Current password" }), cur), h("div", { class: "field" }, h("label", { for: "pw-new", text: "New password" }), nw),
          h("button", { class: "btn primary", type: "button", text: "Update password", onclick: function () {
            api("POST", "/api/me/password", { current: cur.value, new: nw.value }).then(function (r) { pwMsg.className = r.ok ? "ok-msg" : "err"; pwMsg.textContent = r.ok ? "Password updated. Other devices were signed out." : r.data.error; if (r.ok) { cur.value = ""; nw.value = ""; } }); } }), pwMsg),
        h("section", { class: "glass pad" }, h("h2", { text: "Delete account" }),
          h("p", { class: "muted", text: "This permanently deletes your chats, documents and images. It cannot be undone." }),
          h("div", { class: "field" }, h("label", { for: "del-pw", text: "Confirm with your password" }), delPw), delBtn, delMsg)));
  }

  /* ---------- admin ---------- */
  function table(cols, rows) {
    return h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" }, h("thead", null, h("tr", null, cols.map(function (c) { return h("th", { text: c }); }))), h("tbody", null, rows)));
  }
  function statusBadge(st) {
    var cls = st === "ok" ? "ok" : st === "down" ? "bad" : "warn";
    return h("span", { class: "badge " + cls, text: st.replace("_", " ") });
  }

  function viewAdmin(query) {
    var tab = query.tab || "overview";
    var panel = h("div");
    var tabs = [["overview", "Overview"], ["users", "Users"], ["requests", "AI requests"], ["errors", "Errors"], ["settings", "Settings"], ["health", "Service health"], ["owner", "Owner"]];
    var bar = h("div", { class: "tabs", role: "tablist" }, tabs.map(function (t) {
      return h("button", { role: "tab", type: "button", "aria-selected": String(t[0] === tab), text: t[1], onclick: function () { go("/admin?tab=" + t[0]); } });
    }));
    var loaders = {
      overview: function () {
        api("GET", "/api/admin/stats").then(function (r) {
          if (!r.ok) { panel.textContent = r.data.error; return; } var d = r.data;
          var max = Math.max.apply(null, d.daily.map(function (x) { return x.requests; }).concat([1]));
          var stat = function (n, l) { return h("div", { class: "stat glass" }, h("b", { text: String(n == null ? "–" : n) }), h("span", { text: l })); };
          clear(panel).appendChild(h("div", null,
            h("div", { class: "stats" }, stat(d.users_total, "Users"), stat(d.users_new_7d, "New in 7 days"), stat(d.users_pro, "Pro users"), stat(d.conversations, "Chats"), stat(d.messages, "Messages"),
              stat(d.documents, "Documents"), stat(d.images, "Images"), stat(d.requests_24h, "AI requests, 24h"), stat(d.errors_24h, "AI errors, 24h"), stat(d.avg_latency_ms_24h == null ? null : d.avg_latency_ms_24h + " ms", "Avg response, 24h")),
            h("section", { class: "glass pad" }, h("h2", { text: "AI requests, last 7 days" }),
              d.daily.length ? h("div", { class: "bars", role: "img", "aria-label": "Requests per day" }, d.daily.map(function (x) {
                return h("div", { class: "bar" }, h("span", { text: String(x.requests) }), h("div", { class: "col", style: "height:" + Math.max(3, Math.round(x.requests / max * 100)) + "%" }), h("span", { text: x.day.slice(5) }));
              })) : h("p", { class: "muted", text: "No AI requests yet." }))));
        });
      },
      users: function () {
        var q = h("input", { type: "search", placeholder: "Search by email or name", "aria-label": "Search users", style: "max-width:360px;margin-bottom:14px" });
        var out = h("div"), tmr;
        function load() {
          api("GET", "/api/admin/users" + (q.value.trim() ? "?q=" + encodeURIComponent(q.value.trim()) : "")).then(function (r) {
            if (!r.ok) { out.textContent = r.data.error; return; }
            clear(out).appendChild(table(["Email", "Name", "Role", "Plan", "Status", "Requests", "Joined", "Last sign-in"], r.data.users.map(function (u) {
              var self = u.id === S.user.id;
              function patch(body) { api("PATCH", "/api/admin/users/" + u.id, body).then(function (x) { if (!x.ok) toast(x.data.error); load(); }); }
              var plan = h("select", { "aria-label": "Plan for " + u.email, style: "width:auto;padding:4px 8px" }, ["free", "pro"].map(function (p) { return h("option", { value: p, text: p, selected: u.plan === p || null }); }));
              plan.addEventListener("change", function () { patch({ plan: plan.value }); });
              var role = h("select", { "aria-label": "Role for " + u.email, style: "width:auto;padding:4px 8px", disabled: self || null }, ["user", "admin"].map(function (p) { return h("option", { value: p, text: p, selected: u.role === p || null }); }));
              role.addEventListener("change", function () { patch({ role: role.value }); });
              return h("tr", null, h("td", { text: u.email }), h("td", { text: u.name }), h("td", null, role), h("td", null, plan),
                h("td", null, self ? h("span", { class: "muted", text: "you" }) : h("button", { class: "btn sm" + (u.disabled ? "" : " danger"), type: "button", text: u.disabled ? "Enable" : "Disable", onclick: function () { patch({ disabled: !u.disabled }); } })),
                h("td", { text: String(u.requests) }), h("td", { text: fmtDate(u.created_at) }), h("td", { text: fmtDate(u.last_login) }));
            })));
          });
        }
        q.addEventListener("input", function () { clearTimeout(tmr); tmr = setTimeout(load, 250); });
        clear(panel).appendChild(h("div", null, q, h("p", { class: "hint", text: "Subscriptions are managed here by setting a user's plan. Payments are not connected." }), out)); load();
      },
      requests: function () {
        api("GET", "/api/admin/requests").then(function (r) {
          if (!r.ok) return;
          clear(panel).appendChild(table(["When", "User", "Type", "Model", "Status", "Time"], r.data.requests.map(function (x) {
            return h("tr", null, h("td", { text: fmtDate(x.created_at) }), h("td", { text: x.email || "(deleted user)" }), h("td", { text: x.kind }), h("td", { text: x.model }), h("td", null, statusBadge(x.status === "error" ? "down" : x.status)), h("td", { text: x.duration_ms == null ? "" : x.duration_ms + " ms" }));
          })));
        });
      },
      errors: function () {
        api("GET", "/api/admin/errors").then(function (r) {
          if (!r.ok) return;
          clear(panel).appendChild(r.data.errors.length ? table(["When", "Source", "Message"], r.data.errors.map(function (x) {
            return h("tr", null, h("td", { text: fmtDate(x.created_at) }), h("td", { text: x.source }), h("td", { class: "wrap-cell mono", text: x.message }));
          })) : h("p", { class: "muted", text: "No errors recorded." }));
        });
      },
      health: function () {
        api("GET", "/api/admin/health").then(function (r) {
          if (!r.ok) return;
          clear(panel).appendChild(table(["Service", "Status", "Details"], r.data.services.map(function (x) {
            return h("tr", null, h("td", { text: x.name }), h("td", null, statusBadge(x.status)), h("td", { class: "wrap-cell", text: x.detail }));
          })));
        });
      },
      owner: function () {
        var c = S.cfg;
        clear(panel).appendChild(h("section", { class: "glass pad", style: "max-width:560px" }, h("h2", { text: "Owner information" }),
          h("p", null, h("strong", { text: "Platform: " }), c.brand_name), h("p", null, h("strong", { text: "Owner: " }), c.owner_name), h("p", null, h("strong", { text: "Created by: " }), c.creator),
          h("p", null, h("strong", { text: "Email: " }), c.contact_email), h("p", null, h("strong", { text: "WhatsApp: " }), c.whatsapp),
          h("p", { class: "hint", text: "Edit these on the Settings tab. Administrator access is granted only to accounts that have the admin role in the database, never by email address." })));
      },
      settings: function () {
        api("GET", "/api/admin/settings").then(function (r) {
          if (!r.ok) return; var s = r.data.settings, ai = r.data.effective_ai, inputs = {};
          function f(key, label, type, hint) {
            var i = type === "checkbox" ? h("input", { type: "checkbox", id: "s-" + key, checked: s[key] === "true" || null, style: "width:auto" })
              : type === "provider" ? h("select", { id: "s-" + key }, [["", "Use server default (" + ai.provider + ")"], ["anthropic", "Anthropic"], ["openai", "OpenAI-compatible"]].map(function (o) { return h("option", { value: o[0], text: o[1], selected: s[key] === o[0] || null }); }))
              : h("input", { id: "s-" + key, type: type || "text", value: s[key] });
            inputs[key] = i;
            return h("div", { class: "field" }, h("label", { for: "s-" + key, text: label }), i, hint ? h("div", { class: "hint", text: hint }) : null);
          }
          var msg = h("div", { role: "status" });
          function section(title, kids) { return h("section", { class: "glass pad" }, h("h2", { text: title }), kids); }
          clear(panel).appendChild(h("div", null,
            h("div", { class: "two" },
              section("Usage limits", [f("free_daily_messages", "Free plan: messages per day", "number"), f("pro_daily_messages", "Pro plan: messages per day", "number"), f("free_daily_images", "Free plan: images per day", "number"), f("pro_daily_images", "Pro plan: images per day", "number"), f("max_message_chars", "Longest message (characters)", "number"), f("registration_open", "Allow new registrations", "checkbox")]),
              section("Model and provider", [h("p", { class: "hint", text: "Current: " + ai.provider + " / " + ai.model + ". API key " + (ai.key_configured ? "is set" : "is NOT set") + " (keys are kept in the server environment, never here)." }),
                f("ai_provider", "Provider", "provider", "Changing provider uses that vendor's standard endpoint with the same AI_API_KEY."), f("ai_model", "Model name", "text", "Leave empty to use AI_MODEL from the server environment.")])),
            h("div", { class: "two", style: "margin-top:16px" },
              section("Branding", [f("brand_name", "Product name"), f("tagline", "Tagline"), f("owner_name", "Owner name"), f("creator", "Creator attribution")]),
              section("Contact details", [f("contact_email", "Email", "email"), f("whatsapp", "WhatsApp number"), f("whatsapp_country_code", "Country code for the WhatsApp link", "text", "Used to turn a local number starting with 0 into a wa.me link.")])),
            h("div", { style: "margin-top:16px" }, h("button", { class: "btn primary", type: "button", text: "Save settings", onclick: function () {
              var body = {};
              Object.keys(inputs).forEach(function (k) { var i = inputs[k]; body[k] = i.type === "checkbox" ? i.checked : i.value; });
              ["free_daily_messages", "pro_daily_messages", "free_daily_images", "pro_daily_images", "max_message_chars"].forEach(function (k) { body[k] = body[k]; });
              api("PUT", "/api/admin/settings", body).then(function (x) {
                msg.className = x.ok ? "ok-msg" : "err"; msg.textContent = x.ok ? "Saved." : x.data.error;
                if (x.ok) api("GET", "/api/public/config").then(function (c) { if (c.ok) S.cfg = c.data; });
              }); } }), msg)));
        });
      }
    };
    (loaders[tab] || loaders.overview)();
    return h("div", { class: "wrap page view" }, h("h1", { text: "Admin dashboard" }), bar, panel);
  }

  /* ---------- router ---------- */
  function parseHash() {
    var raw = location.hash.slice(1) || "/";
    var parts = raw.split("?"), path = parts[0] || "/", q = {};
    (parts[1] || "").split("&").forEach(function (kv) { if (!kv) return; var p = kv.split("="); q[decodeURIComponent(p[0])] = decodeURIComponent(p.slice(1).join("=") || ""); });
    return { path: path, q: q };
  }

  var AUTH = { "/app": 1, "/images": 1, "/documents": 1, "/account": 1, "/admin": 1 };

  function route() {
    var r = parseHash(), path = r.path, m;
    if (!S.cfg) return;
    var convMatch = /^\/app\/c\/(\d+)$/.exec(path);
    var key = convMatch ? "/app" : path;
    if (AUTH[key] && !S.user) { go("/login?next=" + encodeURIComponent(path)); return; }
    if ((path === "/login" || path === "/register") && S.user) { go("/app"); return; }
    if (path === "/admin" && S.user.role !== "admin") { go("/app"); return; }
    var view, after;
    if (path === "/") { view = viewLanding(); after = afterLanding; }
    else if (path === "/about") view = viewAbout();
    else if (path === "/contact") view = viewContact();
    else if (path === "/tools") view = viewTools();
    else if (path === "/login") view = viewLogin();
    else if (path === "/register") view = viewRegister();
    else if (path === "/forgot") view = viewForgot();
    else if (path === "/reset") view = viewReset();
    else if (convMatch) view = viewChat(r.q, parseInt(convMatch[1], 10));
    else if (path === "/app") view = viewChat(r.q, null);
    else if (path === "/images") view = viewImages();
    else if (path === "/documents") view = viewDocuments();
    else if (path === "/account") view = viewAccount();
    else if (path === "/admin") view = viewAdmin(r.q);
    else view = h("div", { class: "wrap page view" }, h("h1", { text: "Page not found" }), h("p", null, h("a", { href: "#/", text: "Go to the home page" })));
    document.title = (path === "/" ? "" : "") + (S.cfg.brand_name || "ARNET AI");
    shell(path, view);
    if (after) after();
  }

  window.addEventListener("hashchange", route);

  Promise.all([api("GET", "/api/public/config"), api("GET", "/api/me")]).then(function (rs) {
    if (!rs[0].ok) { clear(root).appendChild(h("main", { class: "wrap page" }, h("h1", { text: "ARNET AI" }), h("p", { class: "err", text: "The server is not responding. Try again in a moment." }))); return; }
    S.cfg = rs[0].data;
    S.user = rs[1].ok ? rs[1].data.user : null;
    route();
  });
})();
