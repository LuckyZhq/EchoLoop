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
  ["words", "单词", [["/review", "单词复习", "review"], ["/vocab", "收藏词句", "bookmark"], ["/level", "水平与目标", "level"]]],
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
  return confirm(`重新翻译${what}的 ${count} 句？\n${how}`);
}

// A bar saying the content was translated into another language than the learner's, with a button to switch.
function showLanguageNotice(el, contentLang, what, onSwitch) {
  loadLanguage().then(lang => {
    if (storedLang(lang.native) === storedLang(contentLang)) { el.hidden = true; return; }
    el.innerHTML = `<span>${what}的译文是${esc(langName(storedLang(contentLang)))}，你的母语设置是${esc(langName(lang.native))}。</span>
      <button type="button" class="btn">↻ 换成${esc(langName(lang.native))}</button>`;
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
