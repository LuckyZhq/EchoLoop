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
  ["words", "单词", [["/review", "单词复习", "review"], ["/wordbook", "词书", "wordbook"], ["/vocab", "收藏词句", "bookmark"], ["/level", "水平与目标", "level"]]],
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
      ${icon === "review" ? '<span class="nav-badge" id="reviewBadge" hidden></span>' : ""}
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
  const reviewBadge = $("#reviewBadge");
  reviewBadge.hidden = !info.review;
  reviewBadge.textContent = info.review > 99 ? "99+" : info.review;
  reviewBadge.title = `${info.review} 个词待复习`;
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

// Pages are read from disk on every request, but the server's Python code only changes after a restart.
// When the code on disk is newer than the running server, offer the restart here.
async function checkVersion() {
  let info;
  try { info = await api("/api/version"); } catch { return; }
  if (!info.stale || $("#updateBar")) return;
  const bar = document.createElement("div");
  bar.id = "updateBar";
  bar.className = "update-bar";
  bar.setAttribute("role", "status");
  bar.innerHTML = `<span>程序已更新，重启后台服务后生效。</span><button type="button" class="btn primary">立即重启</button>`;
  const button = $("button", bar);
  button.onclick = async () => {
    button.disabled = true;
    button.textContent = "正在重启…";
    try { await api("/api/restart", { method: "POST" }); } catch { /* the server may already be going down */ }
    for (let i = 0; i < 60; i++) {
      await new Promise(resolve => setTimeout(resolve, 500));
      try { if (!(await api("/api/version")).stale) { location.reload(); return; } } catch { /* still starting */ }
    }
    button.textContent = "重启没有完成，请重新打开 IELTS-study";
  };
  document.body.prepend(bar);
}
checkVersion();

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
// ---- Learner profile: current level, target level and words to stop marking.
// Cached in the browser so pages can mark words immediately; refreshed from the server on every page.
const DEFAULT_BAND_VOCAB = { "0": 0, "1": 300, "2": 800, "2.5": 1100, "3": 1500, "3.5": 1800, "4": 2200, "4.5": 2600,
  "5": 3000, "5.5": 3500, "6": 4000, "6.5": 5000, "7": 6000, "7.5": 7000, "8": 8500, "8.5": 9500, "9": 11000 };

function readProfileCache() {
  try { const cached = JSON.parse(localStorage.getItem("profileCache") || "null"); if (cached) return cached; } catch { /* none */ }
  const old = parseFloat(readPreference("vocabLevel"));  // the earlier single "词汇水平" setting
  return { current: isNaN(old) ? null : old, target: null, vocabSize: null, known: [], mature: [], tests: [] };
}
let studyProfile = readProfileCache();
let knownCache = null;

function setProfile(profile) {
  studyProfile = profile;
  knownCache = null;
  try { localStorage.setItem("profileCache", JSON.stringify(profile)); } catch { /* private mode */ }
  window.dispatchEvent(new Event("profilechange"));
}
async function syncProfile() {
  try {
    const profile = await api("/api/profile");
    if (JSON.stringify(profile) !== JSON.stringify(studyProfile)) setProfile(profile);
  } catch { /* keep the cached one */ }
}
syncProfile();
window.addEventListener("storage", event => {
  if (event.key !== "profileCache") return;
  studyProfile = readProfileCache();
  knownCache = null;
  window.dispatchEvent(new Event("profilechange"));
});

function bandVocab(band) {
  const table = studyProfile.bandVocab || DEFAULT_BAND_VOCAB;
  return band === null || band === undefined ? null : table[String(band)] ?? null;
}
function bandLabel(band) { return band === null || band === undefined ? "未设置" : `${band} 分`; }

// Words worth marking lie between what you already know and a little beyond your target:
// lo = your vocabulary (tested, or typical for your current band), hi = typical for the target band + 20%.
function markRange(profile = studyProfile) {
  const current = profile.current ?? 5.5;
  const target = profile.target ?? Math.min(9, current + 1.5);
  const lo = profile.vocabSize ?? bandVocab(current) ?? 3500;
  const hi = Math.max((bandVocab(target) ?? lo) * 1.2, lo + 1500);
  return { lo, hi, perCue: current < 5 ? 3 : 2, current, target };
}

function knownWords() {
  return knownCache ||= new Set([...(studyProfile.known || []), ...(studyProfile.mature || [])]);
}

function wordVisible(note, range = markRange()) {
  if (!note) return false;
  if (note.rank === undefined) return true;  // very old data without ranks
  if (knownWords().has(note.en.toLowerCase())) return false;
  const rank = note.rank || (note.exam || note.ielts ? 9000 : 0);  // not in the frequency lists: rare
  return rank > range.lo && rank <= range.hi;
}

// Phrase marks always show; word marks are the ones in your range, exam words first, then the more
// common ones (the most useful to learn next), a few per sentence.
function visibleMarks(cue, range = markRange()) {
  const marks = cue.marks || [];
  const note = key => cue.notes?.[key] || {};
  const order = key => (note(key).ielts || note(key).exam ? 0 : 1e6) + (note(key).rank || 9000);
  const words = [...new Set(marks.filter(m => m.type === "word").map(m => m.key))]
    .filter(key => wordVisible(cue.notes?.[key], range))
    .sort((a, b) => order(a) - order(b))
    .slice(0, range.perCue);
  const keep = new Set(words);
  return marks.filter(m => m.type !== "word" || keep.has(m.key));
}

let toastTimer;
// ---- Word and phrase cards, the lookup popover and 收藏: shared by the player and the article reader.
// Each page has a <div class="pop" id="pop"> and passes the sentence (cue) a card belongs to.
const savedWords = new Set();  // lower-case English of everything in 收藏词句
const lookedUp = new Map();    // "w:word" → card for a word looked up in the dictionary

async function loadSavedWords() {
  try { for (const v of await api("/api/vocab")) savedWords.add(v.en.toLowerCase()); } catch { /* none yet */ }
}

function saveKey(n) { return (n.type === "phrase" ? "p:" : "w:") + n.en; }

function noteHtml(n, cueIndex, { bare = false, k = null } = {}) {
  const isSaved = savedWords.has(n.en.toLowerCase());
  return `<div class="note ${n.type}"${bare ? ' style="border:0;padding:0"' : ""}>
    <div class="h"><b>${esc(n.en)}</b>${n.phonetic ? `<span class="ph">/${esc(n.phonetic)}/</span>` : ""}
      <span class="badge ${n.type}">${n.type === "phrase" ? "重点短语" : n.lookup ? "查词" : "难词"}</span>
      <span class="act">
        <button class="iconbtn" data-speak="${esc(n.en)}" title="发音">🔊</button>
        ${n.type === "word" && !n.lookup ? `<button class="iconbtn" data-known="${esc(n.en)}" title="以后不再标出这个词">✓ 认识</button>` : ""}
        <button class="iconbtn ${isSaved ? "saved" : ""}" data-save="${esc(saveKey(n))}" data-cue="${cueIndex}"${k === null ? "" : ` data-k="${k}"`}>${isSaved ? "★ 已收藏" : "☆ 收藏"}</button>
      </span></div>
    <div class="zh">${esc(n.zh || "（词典里没有找到）")}</div>
    ${n.note ? `<div class="tip">${esc(n.note)}</div>` : ""}
  </div>`;
}

async function lookupNote(word) {
  const info = await api(`/api/lookup?w=${encodeURIComponent(word)}`);
  const n = { type: "word", lookup: true, en: info.en || word, zh: info.zh || "", phonetic: info.phonetic || "", note: "" };
  lookedUp.set(saveKey(n), n);
  return n;
}

function showPop(anchor, html) {
  const pop = $("#pop");
  pop.innerHTML = html;
  pop.classList.add("show");
  const r = anchor.getBoundingClientRect();
  const pw = pop.offsetWidth, ph = pop.offsetHeight;
  const x = Math.min(Math.max(16, r.left + r.width / 2 - pw / 2), innerWidth - pw - 16);
  let y = r.bottom + 8;
  if (y + ph > innerHeight - 8) y = r.top - ph - 8;
  pop.style.left = x + "px"; pop.style.top = Math.max(8, y) + "px";
}
function hidePop() { $("#pop")?.classList.remove("show"); }

// Card for a clicked word: a marked phrase/hard word uses the sentence's note, any other word the dictionary.
async function showWordCard(target, cue) {
  const n = target.tagName === "MARK" ? cue.notes?.[target.dataset.key] : await lookupNote(target.dataset.w);
  if (n) showPop(target, noteHtml(n, cue.i, { bare: true, k: target.dataset.k ?? null }));
}

// Character ranges of the saved word/phrase in its sentence: the marked phrase (possibly split, as in
// "pick it up"), or the clicked word (data-k counts words the same way as renderMarked).
function savedSpans(cue, key, btn) {
  const marked = (cue.marks || []).filter(m => m.key === key).map(m => [m.s, m.e]);
  if (marked.length) return marked;
  const match = btn.dataset.k === undefined ? null : [...cue.text.matchAll(WORD_RE)][+btn.dataset.k];
  return match ? [[match.index, match.index + match[0].length]] : [];
}

// ✓ 认识: stop marking this word everywhere. Capture phase, so the page's own click handlers don't run.
document.addEventListener("click", async event => {
  const btn = event.target.closest?.("[data-known]");
  if (!btn) return;
  event.stopPropagation();
  event.preventDefault();
  try {
    setProfile(await api("/api/known", { method: "POST", body: { en: btn.dataset.known, known: true } }));
    hidePop();
    toast(`以后不再标出 ${btn.dataset.known}`);
  } catch (error) {
    toast(error.message);
  }
}, true);

// ☆ 收藏 / ★ 已收藏. `source` says where it came from: {videoId, time} or {articleId, sentenceIndex}.
async function toggleSaved(btn, cue, source) {
  const key = btn.dataset.save;
  const n = cue.notes?.[key] || lookedUp.get(key) || await lookupNote(key.slice(2));
  const k = n.en.toLowerCase();
  if (savedWords.has(k)) {
    await api(`/api/vocab/${encodeURIComponent(k)}`, { method: "DELETE" });
    savedWords.delete(k); toast("已取消收藏");
  } else {
    await api("/api/vocab", { method: "POST", body: { ...n, key, sentence: cue.text, sentenceZh: cue.zh, spans: savedSpans(cue, key, btn), ...source } });
    savedWords.add(k); toast("已收藏");
  }
  $$(`[data-save="${CSS.escape(key)}"]`).forEach(b => { const on = savedWords.has(k); b.classList.toggle("saved", on); b.textContent = on ? "★ 已收藏" : "☆ 收藏"; });
}

// How the Chinese was made, e.g. "DeepSeek V4.1 Flash 短语对照" or "本地翻译". `model` is empty for
// videos translated before the model name was recorded.
const MODEL_NAMES = { "deepseek-flash": "DeepSeek V4.1 Flash", "deepseek-v4-flash": "DeepSeek V4.1 Flash", "deepseek-v4-pro": "DeepSeek V4 Pro" };
function translationLabel(translator, model, aligned) {
  if (translator === "none") return "英文释义";  // English-only learners: nothing is translated
  if (!translator || translator === "local") return "本地翻译";
  const name = MODEL_NAMES[model] || model || "API";
  return `${name} ${aligned ? "短语对照" : "翻译"}${translator === "api+local" ? "（部分改用本地）" : ""}`;
}

// Study time for the daily plan ("listen" in the player, "read" in articles). On page exit a beacon is used,
// because a normal request may be cancelled while the page closes.
function logStudyTime(kind, seconds, leaving = false) {
  seconds = Math.min(120, Math.round(seconds));
  if (seconds < 1) return;
  const body = { kind, seconds };
  if (leaving && navigator.sendBeacon) {
    navigator.sendBeacon("/api/activity", new Blob([JSON.stringify(body)], { type: "application/json" }));
  } else {
    api("/api/activity", { method: "POST", body }).catch(() => { /* not important enough to bother the user */ });
  }
}

// ---- Learner language (母语): the language translations and meanings are made in
let languageInfo = null;
async function loadLanguage() {
  if (!languageInfo) {
    try { languageInfo = await api("/api/language"); } catch { languageInfo = { native: "zh-CN", nativeOptions: {} }; }
  }
  return languageInfo;
}
function storedLang(code) { return !code || code === "zh-TW" ? "zh-CN" : code; }  // Traditional is stored as Simplified
function langName(code) { return languageInfo?.nativeOptions?.[code] || code; }
// The label in front of a translation: 中文 for Chinese, otherwise the language's own name.
function translationName(code) { return storedLang(code) === "zh-CN" ? "中文" : langName(code); }

// Asks before translating a video or article again, saying which engine and language will be used.
async function confirmRetranslate(count, what) {
  let settings, lang;
  try { [settings, lang] = await Promise.all([api("/api/settings"), loadLanguage()]); }
  catch (e) { toast(e.message); return false; }
  const target = langName(lang.native);
  const how = lang.native === "en"
    ? "改为只用英文释义，不翻译字幕。"
    : settings.engine === "api"
      ? `用 ${settings.model} 翻译成${target}，并按单词、短语对照。\n会按服务商价格计费。`
      : `用本地离线翻译翻成${target}（没有短语对照）。第一次用这种语言时会先下载它的离线翻译模型。`;
  return confirmDialog(`重新翻译${what}的 ${count} 句？`, { detail: how, ok: "重新翻译" });
}

// A dialog in the middle of the page (the browser's own confirm/alert sit at the top edge).
// Resolves true for the main button; Esc, the backdrop and Cancel resolve false.
function showDialog(message, { detail = "", ok = "确定", cancel = "取消", danger = false, alert = false } = {}) {
  return new Promise(resolve => {
    const dialog = document.createElement("dialog");
    dialog.className = "app-dialog";
    dialog.innerHTML = `
      <p class="app-dialog-msg"></p>
      ${detail ? `<p class="app-dialog-detail"></p>` : ""}
      <div class="app-dialog-actions">
        ${alert ? "" : `<button type="button" class="btn" data-answer="0">${esc(cancel)}</button>`}
        <button type="button" class="btn primary${danger ? " danger" : ""}" data-answer="1">${esc(ok)}</button>
      </div>`;
    $(".app-dialog-msg", dialog).textContent = message;
    if (detail) $(".app-dialog-detail", dialog).textContent = detail;
    let answer = false;
    dialog.addEventListener("click", e => {
      const b = e.target.closest("[data-answer]");
      if (b) { answer = b.dataset.answer === "1"; dialog.close(); }
      else if (e.target === dialog) dialog.close();  // a click on the backdrop
    });
    dialog.addEventListener("close", () => { dialog.remove(); resolve(answer); });
    document.body.append(dialog);
    dialog.showModal();
    $("[data-answer='1']", dialog).focus();
  });
}
function confirmDialog(message, options = {}) { return showDialog(message, options); }
function alertDialog(message) { return showDialog(message, { alert: true, ok: "知道了" }); }

// A bar saying the content was translated into another language than the learner's, with a button to switch.
function showLanguageNotice(el, contentLang, what, onSwitch) {
  loadLanguage().then(lang => {
    if (storedLang(lang.native) === storedLang(contentLang)) { el.hidden = true; return; }
    // label: value pairs read naturally in every interface language (no language name in mid-sentence)
    el.innerHTML = `<span>译文语言：<b>${esc(langName(storedLang(contentLang)))}</b> · 你的母语：<b>${esc(langName(lang.native))}</b></span>
      <button type="button" class="btn">↻ 重新翻译：${esc(langName(lang.native))}</button>`;
    el.querySelector("button").onclick = onSwitch;
    el.hidden = false;
  });
}

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

// ---- Dictation grading: shared by the player and the mistakes notebook.
const DICT_PASS = 0.9; // below this a sentence goes on the "练错句" list
const NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
  "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"];
const CONTRACTIONS = [[/^can't$/, "can not"], [/^cannot$/, "can not"], [/^won't$/, "will not"], [/^shan't$/, "shall not"],
  [/^(\w+)n't$/, "$1 not"], [/^(\w+)'m$/, "$1 am"], [/^(\w+)'re$/, "$1 are"], [/^(\w+)'ve$/, "$1 have"],
  [/^(\w+)'ll$/, "$1 will"], [/^(\w+)'d$/, "$1 would"], [/^(\w+)'s$/, "$1 is"]];

function dictTokens(text) {
  return text.replace(/[’‘`]/g, "'").match(/[A-Za-z0-9]+(?:'[A-Za-z]+)*/g) || [];
}

// British and American spellings compare equal (IELTS accepts both).
function spelling(w) {
  if (w.length <= 4) return w;
  return w.replace(/our(s?)$/, "or$1").replace(/is(e|ed|es|ing|ation|ations)$/, "iz$1")
    .replace(/ys(e|ed|es|ing)$/, "yz$1").replace(/tre(s?)$/, "ter$1");
}

function normalizeWord(word) {
  let w = word.toLowerCase();
  const n = NUM_WORDS.indexOf(w);
  if (n >= 0) return [String(n)];
  if (w === "ok") w = "okay";
  for (const [re, full] of CONTRACTIONS) if (re.test(w)) return w.replace(re, full).split(" ").map(spelling);
  return [spelling(w)];
}

function flatten(words) {
  const flat = [];
  words.forEach((word, owner) => normalizeWord(word).forEach(norm => flat.push({ norm, owner })));
  return flat;
}

function editDistance(a, b) {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = row;
  }
  return prev[b.length];
}

function lcsPairs(a, b) {
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const pairs = [];
  for (let i = 0, j = 0; i < n && j < m;) {
    if (a[i] === b[j]) { pairs.push([i, j]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  return pairs;
}

// Compare what was typed with the cue text, word by word.
function gradeDictation(answer, typed) {
  const words = dictTokens(answer), typedWords = dictTokens(typed);
  const a = flatten(words), b = flatten(typedWords);
  const status = a.map(() => ({ s: "miss", typed: null }));
  const extras = [];
  let pi = -1, pj = -1;
  for (const [ni, nj] of [...lcsPairs(a.map(x => x.norm), b.map(x => x.norm)), [a.length, b.length]]) {
    const gapA = [], gapB = [];
    for (let i = pi + 1; i < ni; i++) gapA.push(i);
    for (let j = pj + 1; j < nj; j++) gapB.push(j);
    gapA.forEach((i, k) => {
      const j = gapB[k];
      if (j === undefined) return;
      const close = editDistance(a[i].norm, b[j].norm) <= Math.max(1, Math.floor(a[i].norm.length / 4));
      status[i] = { s: close ? "spell" : "wrong", typed: typedWords[b[j].owner] };
    });
    gapB.slice(gapA.length).forEach(j => extras.push(typedWords[b[j].owner]));
    if (ni < a.length) status[ni] = { s: "ok", typed: typedWords[b[nj].owner] };
    pi = ni; pj = nj;
  }
  const ok = status.filter(x => x.s === "ok").length, spell = status.filter(x => x.s === "spell").length;
  // rounded like the server stores it, so the result and the saved score show the same percentage
  const score = a.length ? Math.round((ok + spell * 0.5) / (a.length + extras.length * 0.5) * 1000) / 1000 : 1;
  const display = words.map((text, owner) => {
    const parts = status.filter((_, i) => a[i].owner === owner);
    const kinds = new Set(parts.map(p => p.s));
    const s = kinds.size === 1 ? [...kinds][0] : [...kinds].every(k => k === "ok" || k === "spell") ? "spell" : "wrong";
    const typedText = [...new Set(parts.map(p => p.typed).filter(Boolean))].join(" ");
    return { text, s, typed: typedText };
  });
  return { score, words: display, extras: [...new Set(extras)] };
}

// The graded sentence: each word marked ok / spelling / misheard / missed. `hint` goes on the right of the score.
function gradeHtml(result, hint = "") {
  const pct = Math.round(result.score * 100);
  const verdict = pct === 100 ? "全对" : pct >= 90 ? "很好，看看小错" : pct >= 60 ? "对照红色部分，再听一遍" : "建议慢速重听几遍";
  const words = result.words.map(w => w.s === "ok"
    ? `<span class="dw ok">${esc(w.text)}</span>`
    : `<span class="dw ${w.s}">${w.typed && w.s !== "miss" ? `<s>${esc(w.typed)}</s>` : ""}<span>${esc(w.text)}</span></span>`).join(" ");
  return `
    <div class="dict-score ${pct >= DICT_PASS * 100 ? "good" : "bad"}"><b>${pct}%</b><span>${verdict}</span>${hint ? `<span class="dict-next">${hint}</span>` : ""}</div>
    <div class="dict-words">${words}</div>
    ${result.extras.length ? `<div class="dict-extra">多写了：${result.extras.map(esc).join("、")}</div>` : ""}
    <div class="dict-legend"><span class="dw spell"><span>拼写</span></span><span class="dw wrong"><span>听错</span></span><span class="dw miss"><span>漏听</span></span></div>`;
}
