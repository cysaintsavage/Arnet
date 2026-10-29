/* Safe Markdown renderer. Builds DOM nodes with textContent only, so model output can never inject HTML or script.
   window.renderMarkdown(text, { onCode(lang, code, node) }) -> DocumentFragment */
(function () {
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function safeUrl(u) {
    return /^https?:\/\//i.test(u) ? u : null;
  }

  // Inline: `code`, **bold**, *italic*, [text](url), bare http(s) URLs. Anything else stays literal text.
  var INLINE_SRC = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\s][^*\n]*\*)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(https?:\/\/[^\s<>)\]]+)/;

  function inline(parent, text) {
    var last = 0, m;
    var INLINE = new RegExp(INLINE_SRC.source, "g"); // fresh state per call: inline() recurses
    while ((m = INLINE.exec(text))) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      var tok = m[0];
      if (m[1]) parent.appendChild(el("code", null, tok.slice(1, -1)));
      else if (m[2]) { var b = el("strong"); inline(b, tok.slice(2, -2)); parent.appendChild(b); }
      else if (m[3]) { var i = el("em"); inline(i, tok.slice(1, -1)); parent.appendChild(i); }
      else if (m[4]) {
        var lm = /^\[([^\]]+)\]\((.+)\)$/.exec(tok), href = safeUrl(lm[2]);
        if (href) { var a = el("a", null, lm[1]); a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; parent.appendChild(a); }
        else parent.appendChild(document.createTextNode(tok));
      } else {
        var url = tok.replace(/[.,;:!?]+$/, ""), a2 = el("a", null, url);
        a2.href = url; a2.target = "_blank"; a2.rel = "noopener noreferrer"; parent.appendChild(a2);
        if (url.length < tok.length) parent.appendChild(document.createTextNode(tok.slice(url.length)));
      }
      last = m.index + tok.length;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  function codeBlock(lang, code, opts) {
    var wrap = el("div", "codeblock");
    var bar = el("div", "bar");
    bar.appendChild(el("span", null, lang || "code"));
    var copy = el("button", "btn", "Copy");
    copy.type = "button";
    copy.addEventListener("click", function () {
      var done = function () { copy.textContent = "Copied"; setTimeout(function () { copy.textContent = "Copy"; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(code).then(done, function () {});
    });
    bar.appendChild(copy);
    if (opts && opts.onCode) opts.onCode(lang, code, bar);
    var pre = el("pre"), c = el("code", null, code);
    pre.appendChild(c);
    wrap.appendChild(bar); wrap.appendChild(pre);
    return wrap;
  }

  function splitRow(line) { return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(function (s) { return s.trim(); }); }

  window.renderMarkdown = function (src, opts) {
    var frag = document.createDocumentFragment();
    var lines = String(src).replace(/\r\n?/g, "\n").split("\n");
    var i = 0;
    while (i < lines.length) {
      var line = lines[i], m;
      if ((m = /^\s*(```|~~~)\s*([\w+#.-]*)\s*$/.exec(line))) {
        var fence = m[1], lang = m[2], buf = [];
        i++;
        while (i < lines.length && !new RegExp("^\\s*" + fence + "\\s*$").test(lines[i])) buf.push(lines[i++]);
        i++;
        frag.appendChild(codeBlock(lang, buf.join("\n"), opts));
        continue;
      }
      if (!line.trim()) { i++; continue; }
      if ((m = /^(#{1,4})\s+(.*)$/.exec(line))) { var h = el("h" + m[1].length); inline(h, m[2]); frag.appendChild(h); i++; continue; }
      if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { frag.appendChild(el("hr")); i++; continue; }
      if (/^\s*>/.test(line)) {
        var q = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
        var bq = el("blockquote"); bq.appendChild(window.renderMarkdown(q.join("\n"), opts)); frag.appendChild(bq); continue;
      }
      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        var table = el("table"), head = splitRow(line), thead = el("thead"), tr = el("tr");
        head.forEach(function (c) { var th = el("th"); inline(th, c); tr.appendChild(th); });
        thead.appendChild(tr); table.appendChild(thead);
        i += 2;
        var tb = el("tbody");
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
          var r = el("tr");
          splitRow(lines[i++]).forEach(function (c) { var td = el("td"); inline(td, c); r.appendChild(td); });
          tb.appendChild(r);
        }
        table.appendChild(tb); frag.appendChild(table); continue;
      }
      if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
        var ordered = /^\s*\d+[.)]\s+/.test(line), list = el(ordered ? "ol" : "ul");
        while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
          var li = el("li"); inline(li, lines[i].replace(/^\s*([-*+]|\d+[.)])\s+/, "")); list.appendChild(li); i++;
        }
        frag.appendChild(list); continue;
      }
      var para = [lines[i++]];
      while (i < lines.length && lines[i].trim() && !/^\s*(```|~~~|#{1,4}\s|>|([-*+]|\d+[.)])\s)/.test(lines[i])) para.push(lines[i++]);
      var p = el("p");
      para.forEach(function (t, k) { if (k) p.appendChild(el("br")); inline(p, t); });
      frag.appendChild(p);
    }
    return frag;
  };
})();
