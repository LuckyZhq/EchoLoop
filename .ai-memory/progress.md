# EchoLoop 项目进度

## 已完成

- 2026-11-27 前端「去 AI 味」审查与改造：
  - `src/echoloop/static/app.css`：移除首页 `.lang-home::before` 径向发光+点阵背景并取消 `overflow: hidden` 裁切；移除 `.goal-card` 的 `140deg` 渐变与彩色光晕阴影（改用实体 `--button` 与中性 `--panel-shadow`/`--floating-shadow`）；移除 `.player-page` 与 `data-font="sans"` 首选 `Inter` 字体；将 `.note`、`.vitem .sent`、`.lesson-section h3`、`.speak-sample`、`.book-cover` 的单侧装饰条改为完整边框/底线/柔和底色；`.settings-row` 改用 `padding: 12px 0` 修复顶部紧贴；侧栏导航（设置/错句/复习/词书/口语/写作）改用一致的 SVG `mask` 图标替代 Unicode 字符。
  - `src/echoloop/static/common.js`：新增 `iconSvg()` 统一内联 SVG 图标集（`speak`/`headphones`/`edit`/`check`/`play`/`article`），并将侧栏 `.goal-card-icon` 的 `◎` 替换为 SVG 靶心图标、移除 `✓` 字符。
  - `src/echoloop/static/{player,article,review,goals,mistakes,sentences,vocab,wordbook,settings}.html`：移除 `✨ 解析`、`✦`、`🎧`、`🔊`、`✎`、`⏮/⏭`、`✓`、`✕` 等 Emoji/Unicode 符号，统一使用一致的 SVG 线性图标或清晰中文标签；`settings.html` 为 `#lanQr` 补充空 SVG data URI 占位避免无 `src` 破图标记。
  - 验证：`impeccable detect src/echoloop/static` 从 41 项反模式 + 1 项建议降至 **0 项**（PASS）；全量 `uv run --no-sync python -m pytest -q` **280 passed**。
- 2026-11-27 修复名著续读、内容语言、加载提示、书架 URL 与短章节误标已读；完成章节后续读下一章，全书读完可重新开始，旧进度无需迁移。
- 2026-11-27 扩充「设置 → 外观与语言」（`/settings/appearance`）：
  - `src/echoloop/static/common.js`：在 `preferenceOptions` 与 `preferenceDefaults` 中新增 `colorScheme`（`slate`/`emerald`/`amber`/`plum`）、`readingFont`（`serif`/`sans`/`book`/`mono`）和 `eyeCarePalette`（`parchment`/`sage`/`sepia`/`gray`）；`applyAppearance()` 同步设置 `dataset.palette`、`dataset.font`、`dataset.eyecarePalette`；`storage` 监听列表补充该三项以支持跨标签页实时同步。
  - `src/echoloop/static/app.css`：在 `:root` 定义 `--serif` 并支持 `data-font` 切换，移除 `.player-page` / `.article-page` 重复硬编码，使 `.review-sentence` 与 `.mistake-text` 及预览区同步使用 `var(--serif)`；新增 `emerald`、`amber`、`plum` 的深/浅色 `data-palette` 变量；将护眼模式扩展至 `parchment`、`sage`、`sepia`、`gray`（各自覆盖浅/深色并严格限定在 `.article-page[data-eyecare="1"]` 与 `.eyecare-preview[data-eyecare="1"]` 作用域）；补充 `.swatch-group` / `.swatch-btn` 与 `.eyecare-preview` 样式。
  - `src/echoloop/static/settings.html`：侧栏副标题更新为「语言、主题、字体、配色与护眼」；`#appearance` 拆分为「语言」（`#language`）与「外观」（`#display`）两张卡片，新增全局配色色块胶囊、阅读字体下拉、护眼模式配色色块胶囊及实时「护眼模式预览」卡片，并接入持久化与跨标签页同步。
  - 验证：全量 `uv run --no-sync python -m pytest -q` 280 passed；无头 Chrome 验收 `/settings/appearance`、`/player/v1`、`/reading/a1`（含浅/深色主题、4 套全局配色、4 种字体、4 套护眼配色）全部 PASS 且 0 控制台报错。

- 2026-11-26 文章列表按「外刊精读 / 经典名著 / 我的文章」组织；外刊主题动态筛选，旧内置文章与既有阅读记录保留，API 生成文章归入个人文章；书架包含《傲慢与偏见》前两章公版英文节选，支持章节目录、继续阅读及上下章导航。
- 名著进度在文章目录的 `progress.json` 中持久化：进入记录最近阅读，滚动至末句或手动标记时完成；不覆盖文章或句子解析缓存，随文章备份。
- 2026-11-26 为文章精读页新增独立「护眼」模式开关（`#eyeCareBtn`）：使用 `storedFlag("readingEyeCare")` / `storeFlag("readingEyeCare", on)` 持久化并监听 `storage` 跨标签同步；`app.css` 通过 `.article-page[data-eyecare="1"]`（深色暖褐，含 `--hl: #3d3427`）与 `:root[data-theme="light"] .article-page[data-eyecare="1"]`（浅色米黄羊皮纸，含 `--hl: #e6dac2`）严格作用域隔离，不修改全局 `:root`。修改 `src/echoloop/static/article.html`、`src/echoloop/static/app.css`、`tests/test_article_reading.py`，全量 `uv run --no-sync python -m pytest -q` 273 passed。
- 2026-11-26 重新设计文章精读页顶部工具栏（`.article-tools`）：统一全部控件高度为 `34px`、圆角 `9px`；将阅读视图（`英文 | 双语`、`重点标注`、`A− | A+`）与操作控件（`朗读全文`、`解析与词句`、`更多`）左右分组对齐正文宽度；`A− | A+` 改为紧凑分段步进器；`重点标注`、`朗读全文`、`解析与词句`、`更多` 改用内联 SVG 图标并统一激活态。修改 `src/echoloop/static/article.html`、`src/echoloop/static/app.css`、`tests/test_article_reading.py`。
- 2026-11-26 文章精读页改为纸感阅读区与伴随式解析栏，支持句级操作、双语切换、全文连续朗读、字号调整和重点词句定位。
- `/api/sentence/analyze` 新增 `articleId`，沿用文章目录内的持久缓存、学习轨道过滤和解析引擎切换；删除文章会清理缓存。
- 文章解析命中内存缓存时同步展示；请求期间禁用引擎及刷新控件，同句重复点击不再重复发请求。句子悬停有柔和底色；操作条会避让正文，并在移向操作条时保持句子选择。
- 本轮核心文件：`src/echoloop/server.py`、`src/echoloop/static/article.html`、`src/echoloop/static/app.css`、`tests/test_sentence.py`、`tests/test_article_reading.py`。
- 验证：全量 `uv run --no-sync python -m pytest -q` 为 273 passed；Chrome 覆盖浅色/深色、桌面和窄屏，模拟验证缓存、收藏、TTS 连续播放、请求竞态及窄行宽下操作条避让。此前另在 320px 视口验证触屏呼出操作与查词。
- 2026-11-26 播放器切换改为「双语精读 / 英文精读」，并新增本句「双语 / 英文」切换；列表与当前字幕同步，单句选择在本页面保留，全局切换清除单句覆盖。原逐句暂停仍可通过 P 和设置使用，字幕切换不重置听写或循环。
- 字幕切换经过 Chrome 模拟播放器、浅色/深色及窄布局验证；全量 `uv run --no-sync python -m pytest -q` 为 251 passed。
- 2026-11-26 句子解析弹窗新增独立解析引擎下拉框（本地解析 / AI 精讲）：
  - `src/echoloop/settings.py`：新增 `settings_for_engine(engine, current)`，支持在全局翻译为 `local` 时读取已保存的 `profiles` 构造 `engine="api"` 设置；无有效 `base_url`/`model` 时抛出 `ValueError("使用 AI 精讲需要先在设置里配置 API 模型。")`。
  - `src/echoloop/server.py`：`POST /api/sentence/analyze` 校验可选 `engine`（`None`/`"local"`/`"api"`，非法值或未配置 API 返回 `400`），并向 `sentence.analyze` 透传 `explicit_engine=bool(engine)`。
  - `src/echoloop/sentence.py`：`analyze` 新增 `explicit_engine=False`；显式指定引擎时仅查对应引擎缓存（`local` 不再复用 `api` 缓存），未显式指定时保持原复用逻辑。
  - `src/echoloop/static/player.html` & `src/echoloop/static/app.css`：新增 `readLessonEngine`/`saveLessonEngine`（`localStorage` 键 `lessonEngine`）；`.lesson-foot` 右侧改为 `.lesson-actions`（`#lessonEngine` 下拉框 + `#lessonRefresh` 按钮，错误态也保留 `#lessonEngine` 可切回）；`lessonCache` 键含引擎并按实际 `source` 双写；将 `++lessonRequest` 提前并调用 `hidePop()`；新增 `.lesson-actions`/`.lesson-engine` 样式。
  - `tests/test_sentence.py`：新增 4 项单测；全量 `uv run --no-sync python -m pytest -q` 247 项通过。
- 2026-11-26 优化 `/api/sentence/analyze` 前后端缓存机制：
  - `src/echoloop/sentence.py`：`analyze` 签名扩展 `force=False`；缓存版本升为 `lesson-v9`，`digest` 仅绑定 `("lesson-v9", track or "", cue["text"])`，切模型、改标注或微调译文不再失效，且本地模式可复用已有 API 缓存；API 精讲落盘记录 `"model"` 元信息，返回结果附带 `"cached"`（不落盘）；命中缓存时直接返回不跑 spaCy 或模型；回退本地词汇前检查 `payload.get("candidates")`。
  - `src/echoloop/server.py`：`POST /api/sentence/analyze` 透传 `force = bool(body.get("force"))`。
  - `src/echoloop/static/player.html` & `src/echoloop/static/app.css`：新增 `lessonCache` 页内内存缓存（`profilechange` 与 `retranslate()` 后清空），拆分 `renderLesson`，状态栏改为 `.lesson-foot`（左侧 `#lessonStatus` 区分「已缓存」与新生成，右侧 `#lessonRefresh`「重新解析」按钮），适配浅色/深色主题。
  - `tests/test_sentence.py`：补充并更新 5 项缓存与 `force` 透传单测；全量 `uv run --no-sync python -m pytest -q` 243 项全部通过。

- 2026-11-26 放大字幕句子收藏星标至 18px，收藏和悬停显示黄色；Chrome 验证浅色、深色和居中均通过。样式提交 `bc55af3` 已推送至 `origin/main`。
- 2026-11-26 修复句子解析的 ECDICT 标签映射、轨道标签过滤、释义截断、本地降级选词和 API 上下文；`lesson-v8` 使旧缓存失效。真实本地 ECDICT 回归和全量 pytest 240 项通过。
- 2026-11-26 修复导入页模型名称溢出：浏览器实测原规则 `.composer-actions > .select-wrap` 未匹配嵌套在 label 内的元素；Chromium 支持 base-select，但选中文字宽于选择框。现使用限宽原生 select、省略号和完整名称提示，切换失败时恢复原提示。
- 更正此前排查：缓存和浏览器不支持 `@supports` 均未被证实为原因。此前新增的 `no-cache` 已限制到静态资源，避免改变视频等媒体的缓存策略。
- 修复精听页来源按钮：图标紧邻标题，弹窗以可选中文本显示已有的来源、原始链接、时长和已知字幕来源；无数据时显示空状态。试听提示位于标题行下方。
- 本轮修改 `src/echoloop/static/app.css`、`src/echoloop/static/index.html`、`src/echoloop/static/player.html`、`src/echoloop/server.py`、`tests/test_server.py`；Chromium 覆盖 280–1440px、选择成功与失败回退、来源弹窗及空状态，相关 pytest 30 项通过。


- 现有实现覆盖视频和音频导入、双语字幕精听、听写与错句、文章精读、词句收藏与间隔复习、口语和写作练习、备考计划。默认六级轨道，可切换四级或雅思。
- 当前工作区已将应用和 Python 包改名为 EchoLoop / `echoloop`，并加入六级专项内容及媒体探测重试。`main` 的本地 HEAD 为 `8049489`，改名和功能改动仍在工作区与暂存区。
- 2026-11-26 在 Windows 上用现有 Python 3.12.14 环境执行 `uv run --no-sync python -m pytest -q`，185 项全部通过，耗时 22.22 秒。GitHub Actions 已配置 Linux、macOS、Windows 测试矩阵。
- 已按 `AGENTS.md` 初始化 `.ai-memory/`，并通过 `GEMINI.md` 引用同一份项目规则。
- 已核实离线翻译使用 Argos 英译中模型 1.9，由 CTranslate2 在 CPU 上推理，单句测试通过。当前应用设置为 API 翻译。
- 已用本机词典和 spaCy 核对词组检测。带副词的 `is often attributed to` 已标出 `attributed to`，主动式 `attribute … to` 和 `pay close attention to` 示例漏检。同一字幕片段出现两个词组时只取一组。
- 已将词组检测改造的第一人称完整实施与验收计划写入 `transfer/局限性问题修复方案.md`（移除了备选方案章节）。

- 2026-11-26 已实施词组检测方案。每句最多标两组互不重叠的搭配，第二组限精选词条。已支持固定变体、主动式 attribute … to 和首批考试搭配。视频与文章打开时按需从标注版本 6 升至 7。
- Windows 全量 pytest 198 项通过。真实四级、六级长句完成抽样；隔离库的两种页面、两种显示模式均通过 Chrome 点击验收。
- 2026-11-26 已完成播放器三项改造。标题、字幕、弹窗原句和词条改用衬线体，中文与界面保持无衬线，时间戳为等宽数字；配色沿用现有主题变量，未引入新配色。新增「单句精讲」弹窗（重点搭配、语法句型、词汇与考试标签），短语和词汇接入现有 `/api/vocab` 收藏并回显状态。顶部新增「双语精看 / 逐句精读」两个模式，与原有「逐句暂停」偏好共用 `autoPause`。
- 新增 `POST /api/sentence/analyze`。API 引擎用现有模型配置生成精讲，本地引擎用 spaCy 与词典生成；结果按句子、引擎和模型名缓存到视频目录下的 `lesson-*.json`，缓存读取或写入失败都不影响返回精讲。
- 2026-11-26 按用户要求取消模型估级（CEFR）。词汇的考试标签改为查词典数据库（`sentence.exam_info`）：变形词取自身与原形标签的并集，按中考、高考、四级、六级、考研、托福、雅思、GRE 的固定顺序显示。模型只负责选词、音标、词性和语境释义，不再给等级。
- Windows 全量 pytest 211 项通过。Chrome 无头模式在隔离库上实测 33 项检查，覆盖两种模式的播放与句末暂停、弹窗三种关闭方式、收藏与取消、缓存复用，以及 390px 窄屏布局。
- 2026-11-26 将「单句精讲」改造成扁平式「句子解析」：标题居中、原句与译文、句子结构（蓝色圆点列表）、重点词语（蓝色下划线可点击）、重点搭配三区块按固定顺序排列，缺内容时保留标题并显示空状态。移除大卡片与彩色胶囊，「重点搭配」不再逐条列考试标签。
- 考试标签在解析窗口内不显示，只在点击词汇后的查词卡片里显示为彩色胶囊（每个考试类型一种颜色）。`/api/lookup` 返回 `tags`；列表保持「单词：词性 释义」。
- 2026-11-26 重点词语按「我的目标」的考试轨道过滤，并向上拓宽一档：cet4→四级+六级、cet6→六级+考研、ielts→雅思+托福（`sentence.TRACK_EXAMS`）。`goals.track()` 读取 profile.json 的 `track`；区块标题显示「重点词语 · 六级 + 考研」。模型路径过滤后为空时回退本地同轨词汇。缓存 `lesson-v5`，键含轨道。
- 最终 `uv run --no-sync python -m pytest -q` → 221 passed；隔离库 Chrome 30/30 PASS。注意 `_local_lesson` 的参数不能叫 `labels`，会遮蔽函数内的词性字典，已改为 `pos_names`。
- 2026-11-26 收藏图标统一换成内联 SVG 星标（`starSvg`：未收藏描边、已收藏填充），替换播放器逐句收藏、查词卡片「收藏/已收藏」、重点搭配收藏按钮上的 ★/☆ 字符，并用 inline-flex 居中；侧栏「句子收藏」入口改为 CSS mask 的 SVG 星形。`player.html`、`common.js`、`app.css`、`sentences.html` 的文案同步改为「星标」。
- 最新验证：221 passed；隔离库 Chrome 33/33 PASS（新增 SVG 图标与垂直居中检查）。
- 2026-11-26 统一单词解释弹窗：去掉 `.note.word` 的赭色左边框与 `.badge.word` 的赭色配色，单词徽标一律「查词」，短语仍为「重点短语」。`/api/lookup` 和单句解析返回的词汇标签都按 `TRACK_EXAMS` 收窄到当前目标范围，所以六级目标下查词卡片只显示「六级 / 考研」，不再出现雅思。缓存升到 `lesson-v6`。
- 2026-11-26 难词标注也按目标范围过滤：`annotate.py` 给每个词条新增 `tags` 名称数组，`common.js` 的 `TRACK_SCOPE` + `scopeTags()` 同时用于 `visibleMarks()` 和 `noteHtml()`。旧数据没有 `tags` 时按 `note` 的「 / 」拆分回退，无需重新导入。标注词条现在和解析词汇共用同一套彩色标签渲染，不再输出纯文本 `note`。
- 最新验证：221 passed；隔离库 Chrome 39/39 PASS（含：范围外词不标注、范围内词标注、范围外卡片无标签、范围内卡片显示彩色标签）。

## 待办

- 用用户实际翻译引擎及词典验收名著首次导入、句子解析缓存、查词和收藏；本轮端到端使用隔离数据与替身翻译。
- 新字幕切换尚未用真实视频媒体验收。
- 句子解析修复及其他原有工作区改动仍未提交，本次只推送了收藏星标样式。
- 句子解析本轮未调用真实 LLM，可用已有配置对含六级词的字幕做端到端验收。
- 本次方案验收完成。更复杂的嵌套从句仍受 spaCy 依存分析质量限制。

## 本轮文件

- 名著验收修复：`src/echoloop/static/{reading.html,article.html,app.css}`、`src/echoloop/{server.py,i18n/en.json}`、`tests/{test_reading_library,test_i18n}.py`、`.ai-memory/{progress,handoff}.md`。
- 文章分类与书架：`src/echoloop/{classics,graded,reading,server}.py`、`src/echoloop/static/{reading.html,article.html,app.css}`、`src/echoloop/i18n/en.json`、`tests/{test_reading,test_reading_library,test_server}.py`、`.ai-memory/{progress,decisions,handoff}.md`。
- 字幕显示切换：`src/echoloop/static/player.html`、`src/echoloop/static/app.css`、`tests/test_player_subtitle_modes.py`、`.ai-memory/{progress,handoff}.md`。
- 句子解析独立引擎切换：`src/echoloop/{settings,server,sentence}.py`、`src/echoloop/static/{player.html,app.css}`、`tests/test_sentence.py`、`.ai-memory/{progress,handoff}.md`。
- 句子解析前后端缓存优化：`src/echoloop/sentence.py`、`src/echoloop/server.py`、`src/echoloop/static/{player.html,app.css}`、`tests/test_sentence.py`、`.ai-memory/{progress,handoff}.md`。

- 收藏星标：`src/echoloop/static/app.css`、`.ai-memory/{progress,handoff}.md`。
- 句子解析修复：`src/echoloop/sentence.py`、`tests/test_sentence.py`、`.ai-memory/{progress,decisions,handoff}.md`。
- 播放器改造：`src/echoloop/static/{player.html,app.css,common.js}`、`src/echoloop/{server.py,sentence.py}`、`tests/test_sentence.py`
- 视频精听收藏图标居中（去边框，复用 starSvg）：`src/echoloop/static/app.css`；字幕文本内残留时间戳行清理：`src/echoloop/media.py`
- `src/echoloop/annotate.py`、`src/echoloop/dictionary.py`、`src/echoloop/phrases_curated.json`、`tests/test_phrase_annotation.py`、`.ai-memory/{progress,decisions,handoff}.md`

## 发布

- 词组修复和 13 项回归测试已推送至 origin/main（724dc84）。在远端包结构中独立验证，全量 189 项通过。


- 2026-11-26 修复一批稳健性问题：`sentence._local_lesson` 候选词优先考纲标签词；`annotate.word_info` 全大写字幕不再误当专名、分词形容词继承原形标签，`_hard_words` 带标签词排前；`translate._json_reply` 容错前后说明文字，`meaning_instructions` 兼顾语境义与核心义项、CJK/非 CJK 分别限长，`MEANING_BATCH` 降为 20；`media._clean_text` 清理多次重复时间戳；`common.js`/`player.html`/`article.html` 前端状态与交互统一。新增 `tests/test_robustness.py`。

- 2026-11-26 新增 `scripts/clean_old_timestamps.py <videoId> [--apply]`：清理旧库英文字幕里残留的时间戳行（默认预览，`--apply` 先备份为 `data.before-timestamp-clean.json`，并清掉受影响句的 marks/notes 以便重新标注）。已对 `tedtalk-1042` 的 39 句执行；中文译文里的乱码时间戳需用「重新翻译」处理。浏览器验收：精讲弹窗中 Esc 先关查词卡片、再关弹窗。

- 2026-11-26 补齐 `sentence.py` 清单：新增 `_track_candidates`（候选词前置，标签按空格拆分比较）、`_instructions(labels)`（raw JSON、non-overlapping、2–6 段、≤5 个单词、lemma 字段、meaning ≤15 字、expressions 不与 vocabulary 重复）、`_local_vocabulary`（API 词汇被过滤为空时只补词汇不重跑句法分析）；`_model_lesson` 读 lemma 并保留、按 candidates 过滤；`_local_lesson` 的 `word` 存原句词形、`lemma` 存原型；缓存版本 `lesson-v6`→`lesson-v7`，`analyze` 显式构造 `target` 路径。新增 6 个用例。全量 234 项通过。
