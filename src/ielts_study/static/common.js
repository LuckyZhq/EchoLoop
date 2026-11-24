// Shared helpers for IELTS Study pages.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const preferenceOptions = {
  appearance: [["system", "跟随系统"], ["light", "浅色"], ["dark", "深色"]],
  nowColor: [["green", "淡绿"], ["yellow", "淡黄"], ["blue", "淡蓝"]],
  quality: [["480", "480p"], ["720", "720p"], ["1080", "1080p"], ["1440", "1440p"], ["2160", "2160p"], ["best", "最高可用"]],
  speed: ["0.6", "0.75", "0.9", "1", "1.25", "1.5"].map(rate => [rate, rate + "×"]),
  vocabLevel: [["5.5", "5.5 及以下"], ["6", "6 分"], ["6.5", "6.5 分"], ["7", "7 分"], ["7.5", "7.5 及以上"], ["general", "不限雅思"]],
};
const preferenceDefaults = {
  appearance: "system",
  textSize: "1",
  quality: "720",
  speed: "1",
  vocabLevel: "6",
  zh: true,
  marks: true,
  follow: true,
  autoPause: false,
  loop: false,
  karaoke: true,
  gloss: true,
  nowColor: "green",
};

// Continuous preferences: [min, max]. Stored as a string number.
const preferenceRanges = { textSize: [0.8, 1.8] };

function readPreference(name) {
  const fallback = preferenceDefaults[name];
  let value;
  try { value = localStorage.getItem(name); } catch {}
  if (typeof fallback === "boolean") {
    if (value === "1") return true;
    if (value === "0") return false;
    return fallback;
  }
  if (preferenceRanges[name]) {
    const [min, max] = preferenceRanges[name];
    const n = parseFloat(value);
    return Number.isFinite(n) ? String(Math.min(max, Math.max(min, Math.round(n * 100) / 100))) : fallback;
  }
  return preferenceOptions[name].some(([option]) => option === value) ? value : fallback;
}

const systemAppearance = window.matchMedia("(prefers-color-scheme: dark)");

function applyAppearance() {
  const appearance = readPreference("appearance");
  const systemTheme = systemAppearance.matches ? "dark" : "light";
  document.documentElement.dataset.theme = appearance === "system" ? systemTheme : appearance;
  // Subtitle / study-text size; app.css multiplies reading text by --text-scale.
  document.documentElement.style.setProperty("--text-scale", readPreference("textSize"));
  document.documentElement.dataset.now = readPreference("nowColor");
}

applyAppearance();
systemAppearance.addEventListener("change", applyAppearance);
window.addEventListener("pageshow", applyAppearance);
window.addEventListener("storage", event => {
  if (event.key === null || event.key === "appearance" || event.key === "textSize" || event.key === "nowColor") applyAppearance();
});

const workspaceNav = $(".workspace-nav");
// Sidebar: the brand opens the home page; study tools are grouped by skill.
const NAV_GROUPS = [
  ["listen", "听力", [["/listening", "视频精听", "import"], ["/mistakes", "错句本", "mistakes"]]],
  ["words", "单词", [["/vocab", "收藏词句", "bookmark"]]],
  ["read", "阅读", [["/reading", "文章精读", "reading"]]],
];
function storedFlag(key) { try { return localStorage.getItem(key) === "1"; } catch { return false; } }
function storeFlag(key, on) { try { localStorage.setItem(key, on ? "1" : "0"); } catch { /* private mode */ } }

if (workspaceNav) {
  let current = location.pathname;
  if (current.startsWith("/player/") || current === "/index.html") current = "/listening";
  if (current.startsWith("/reading/")) current = "/reading";
  if (current.startsWith("/settings/")) current = "/settings";
  const link = (href, label, icon) => `
    <a class="workspace-link" href="${href}"${href === current ? ' aria-current="page"' : ""}>
      <span class="nav-icon nav-${icon}" aria-hidden="true"></span><span>${label}</span>
      ${icon === "mistakes" ? '<span class="nav-badge" id="mistakeBadge" hidden></span>' : ""}
    </a>`;
  const collapsed = storedFlag("recentCollapsed");
  workspaceNav.innerHTML = `
    <a class="workspace-label" href="/"${current === "/" ? ' aria-current="page"' : ""} title="首页">
      <span class="workspace-mark" aria-hidden="true"></span><span>IELTS Study</span></a>
    <nav class="workspace-groups" aria-label="主要导航">${NAV_GROUPS.map(([id, title, links]) => `
      <section class="nav-group nav-group-${id}" aria-labelledby="navGroup-${id}">
        <div class="nav-group-title" id="navGroup-${id}">${title}</div>
        <div class="workspace-links">${links.map(([href, label, icon]) => link(href, label, icon)).join("")}</div>
      </section>`).join("")}
    </nav>
    <section class="workspace-recent${collapsed ? " collapsed" : ""}" hidden>
      <button type="button" class="workspace-subhead recent-toggle" aria-expanded="${!collapsed}" aria-controls="recentList">
        <span>最近在看</span><span class="recent-chevron" aria-hidden="true"></span>
      </button>
      <div class="recent-list" id="recentList"${collapsed ? " hidden" : ""}></div>
    </section>
    <div class="workspace-footer">${link("/settings", "设置", "settings")}</div>`;
  $(".recent-toggle").addEventListener("click", event => {
    const open = event.currentTarget.getAttribute("aria-expanded") !== "true";
    event.currentTarget.setAttribute("aria-expanded", open);
    $("#recentList").hidden = !open;
    $(".workspace-recent").classList.toggle("collapsed", !open);
    storeFlag("recentCollapsed", !open);
  });
  refreshSidebar();
}

// Mistake count and "recently watched" come from the server; refreshed after dictation and on return to a page.
async function refreshSidebar() {
  if (!workspaceNav) return;
  let info;
  try { info = await api("/api/sidebar"); } catch { return; }
  const badge = $("#mistakeBadge");
  badge.hidden = !info.mistakes;
  badge.textContent = info.mistakes > 99 ? "99+" : info.mistakes;
  badge.title = `${info.mistakes} 句待重练`;
  const playing = location.pathname.startsWith("/player/") ? decodeURIComponent(location.pathname.split("/").pop()) : null;
  $(".workspace-recent").hidden = !info.recent.length;
  $("#recentList").innerHTML = info.recent.map(v => {
    const pct = v.duration ? Math.min(100, Math.round(v.time / v.duration * 100)) : 0;
    return `
      <a class="recent-item" href="/player/${encodeURIComponent(v.id)}?t=${v.time}"${v.id === playing ? ' aria-current="page"' : ""} title="${esc(v.title)}">
        <span class="recent-title">${esc(v.title)}</span>
        <span class="recent-meta">${fmtTime(v.time)} / ${fmtTime(v.duration)}${v.dictated ? ` · 听写 ${v.dictated}/${v.cueCount}` : ""}</span>
        <span class="recent-bar" aria-hidden="true"><i style="width:${pct}%"></i></span>
      </a>`;
  }).join("");
}
window.addEventListener("pageshow", event => { if (event.persisted) refreshSidebar(); });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtTime(t) {
  t = Math.max(0, Math.floor(t || 0));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: opts.body ? { "content-type": "application/json" } : undefined,
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || `请求失败 ${r.status}`), { status: r.status });
  return data;
}

// Wrap words so each one can be clicked; key-point ranges become <mark>.
// Every word also gets data-k (its index in the cue) so the player can highlight the word being spoken.
const WORD_RE = /[A-Za-z][A-Za-z'’-]*/g;
function renderMarked(text, marks = []) {
  let k = 0;
  const words = (s, inMark) => {
    let html = "", end = 0;
    for (const match of s.matchAll(WORD_RE)) {
      const word = esc(match[0]);
      const lookupWord = esc(match[0].replaceAll("’", "'"));
      html += esc(s.slice(end, match.index)) + (inMark
        ? `<span data-k="${k++}">${word}</span>`
        : `<span class="w" data-w="${lookupWord}" data-k="${k++}">${word}</span>`);
      end = match.index + match[0].length;
    }
    return html + esc(s.slice(end));
  };
  let out = "", pos = 0;
  for (const m of [...marks].sort((a, b) => a.s - b.s)) {
    if (m.s < pos) continue;
    out += words(text.slice(pos, m.s), false);
    out += `<mark class="${m.type}" data-key="${esc(m.key)}">${words(text.slice(m.s, m.e), true)}</mark>`;
    pos = m.e;
  }
  return out + words(text.slice(pos), false);
}

// Word / phrase layout: the caption is cut into columns, English on top and its Chinese underneath.
// `seg` (from API translation) groups words into phrases with a Chinese meaning in context;
// words outside any phrase show their dictionary gloss from `gloss`. Words keep data-k (same numbering
// as renderMarked), so lookups and the spoken-word highlight keep working.
function renderInterlinear(text, marks = [], gloss = [], seg = []) {
  gloss = gloss || []; seg = seg || [];
  const matches = [...text.matchAll(WORD_RE)];
  const sortedMarks = [...marks].sort((a, b) => a.s - b.s);
  const markAt = (s, e) => sortedMarks.find(m => m.s <= s && e <= m.e);
  const segAt = (s, e) => seg.findIndex(g => g.s <= s && e <= g.e);
  const groups = [];
  let group = null;
  const lead = text.slice(0, matches[0]?.index ?? text.length).trim();
  if (lead) groups.push({ html: esc(lead), zh: "", id: "lead" });
  matches.forEach((m, k) => {
    const s = m.index, e = s + m[0].length;
    const next = matches[k + 1]?.index ?? text.length;
    const [, attach, rest] = text.slice(e, next).match(/^(\S*)\s*([\s\S]*?)\s*$/);
    const si = segAt(s, e);
    const mark = markAt(s, e);
    let word = mark
      ? `<mark class="${mark.type}" data-key="${esc(mark.key)}"><span data-k="${k}">${esc(m[0])}</span></mark>`
      : `<span class="w" data-w="${esc(m[0].replaceAll("’", "'"))}" data-k="${k}">${esc(m[0])}</span>`;
    word += esc(attach);
    if (si >= 0 && group && group.id === si) group.html += " " + word;
    else {
      group = { html: word, zh: si >= 0 ? seg[si].zh : (gloss[k] || ""), id: si >= 0 ? si : `w${k}`, phrase: si >= 0 };
      groups.push(group);
    }
    if (rest) {
      if (si >= 0 && next <= seg[si].e) group.html += " " + esc(rest);  // e.g. the "5" in "5 simple exercises"
      else { group = { html: esc(rest), zh: "", id: `x${k}` }; groups.push(group); }
    }
  });
  return groups.map(g => `<span class="ic${g.phrase ? " ic-phrase" : ""}"><span class="ic-en">${g.html}</span>` +
    `<span class="ic-zh">${g.zh ? esc(g.zh) : "&nbsp;"}</span></span>`).join("");
}

// ---- Vocabulary level: which saved hard-word candidates to highlight.
// IELTS levels show IELTS-list words rarer than the level's frequency rank (more common = assumed known).
const LEVEL_RANK = { "5.5": 2500, "6": 3500, "6.5": 4500, "7": 6000, "7.5": 8000 };
const GENERAL_RANK = 4000;
const MAX_WORDS_PER_CUE = 2;

function wordVisible(note, level) {
  if (!note || note.rank === undefined) return true; // older data without ranks
  if (level === "general") return note.rank > GENERAL_RANK || (note.rank === 0 && note.exam);
  return note.ielts && (note.rank === 0 || note.rank > LEVEL_RANK[level]);
}

// Phrase marks always show; word marks are filtered by level, rarest first, at most 2 per cue.
function visibleMarks(cue, level = readPreference("vocabLevel")) {
  const marks = cue.marks || [];
  const rarity = key => cue.notes?.[key]?.rank || 1e9;
  const words = [...new Set(marks.filter(m => m.type === "word").map(m => m.key))]
    .filter(key => wordVisible(cue.notes?.[key], level))
    .sort((a, b) => rarity(b) - rarity(a))
    .slice(0, MAX_WORDS_PER_CUE);
  const keep = new Set(words);
  return marks.filter(m => m.type !== "word" || keep.has(m.key));
}

let toastTimer;
function toast(msg) {
  let el = $(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1600);
}

// Offline text-to-speech (macOS system voices).
function speak(text, rate = 0.95) {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = rate;
  const v = speechSynthesis.getVoices().find(v => v.lang === "en-US" && /Samantha|Alex|Ava|Allison/.test(v.name));
  if (v) u.voice = v;
  speechSynthesis.speak(u);
}
