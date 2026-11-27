# EchoLoop 交接

## 2026-11-27 前端「去 AI 味」审查与改造（最新）

- **当前状态**：已完成 `src/echoloop/static/` 全量静态页面与样式的 AI 模板化特征清理（移除径向发光+点阵背景、渐变光晕卡片、单侧装饰条、`Inter` 首选字体、Emoji/Unicode 混用图标及无 `src` 占位图），统一为一致的 1.8px 描边内联 SVG 与 CSS `mask` 图标体系。
- **核心改动**：`src/echoloop/static/{app.css,common.js,player.html,article.html,review.html,goals.html,mistakes.html,sentences.html,vocab.html,wordbook.html,settings.html}`。
- **验证**：`impeccable detect src/echoloop/static` **0 anti-patterns / 0 advisories**（此前 41 项）；全量 `uv run --no-sync python -m pytest -q` **280 passed**（67.46s）。
- **遗留问题/报错**：工作区保留既有未提交改动；浏览器端需刷新加载最新静态资源。
- **建议第一步**：在浏览器打开首页、播放器、文章精读、词句本及设置页确认图标对齐与视觉质感；如需提交请确认要纳入的改动范围。

Updated by Antigravity · 2026-11-27 09:58 +08:00

## 2026-11-27 名著验收修复

- **当前状态**：续读指向已完成章节的下一章；全部读完后隐藏书架续读按钮并提供重新开始；内容语言、加载提示、书籍 URL、短滚动误标与重复 CSS 已修复。
- **验证**：相关 pytest 52 项通过，含三种屏宽、书架与详情按钮、重载 URL、繁简内容语言、短滚动和长滚动；英文界面脚本语法通过。
- **遗留问题/报错**：尚未调用用户真实翻译服务与个人阅读数据验收；已有进度保留。
- **建议第一步**：打开一章标记已读，返回书架确认「继续阅读」指向下一章。

Updated by Codex · 2026-11-27 09:48 +08:00

## 2026-11-27 外观与语言设置扩充（最新）

- **当前状态**：已完成 `/settings/appearance` 的外观扩充改造（纯前端 `localStorage` 存储，未改动后端 `settings.py`），统一控制全局主题、4 套全局配色（`slate`/`emerald`/`amber`/`plum`）、4 种阅读字体（`serif`/`sans`/`book`/`mono`）、4 套护眼模式配色（`parchment`/`sage`/`sepia`/`gray`）及字号，并提供实时预览与护眼预览卡片。
- **核心改动**：`src/echoloop/static/common.js`、`src/echoloop/static/app.css`、`src/echoloop/static/settings.html`。
- **验证**：全量 `uv run --no-sync python -m pytest -q` **280 passed**（55.37s）；无头 Chrome 验证 `/settings/appearance`、`/player/v1`、`/reading/a1` 的主题、4 套全局配色、4 种字体、浅/深色 4 套护眼配色全部 PASS，无控制台报错。
- **遗留问题/报错**：静态资源在浏览器端可能需要强制刷新（`Ctrl+Shift+R`）以加载最新 `common.js` / `app.css` / `settings.html`。
- **建议第一步**：打开 `/settings/appearance` 切换全局配色、阅读字体与护眼模式配色，再到播放器与文章精读页确认视觉效果。

Updated by Antigravity · 2026-11-27 09:45 +08:00

## 2026-11-26 文章分类与经典名著书架（最新）

- **当前状态**：三个一级视图已接入外刊主题筛选、个人文章及名著书架；公版《傲慢与偏见》两章节选复用文章翻译与精读，支持返回目录、上下章、继续阅读和已读统计。
- **验证**：相关 pytest 129 项通过，覆盖旧数据、进度、HTTP 接口、精读缓存及 1440/900/500 宽度；隔离服务中浏览器实测第一章、标记已读、下一章及返回目录。
- **遗留问题/报错**：端到端未调用用户真实翻译引擎及词典；首次打开章节需要现有翻译引擎工作。书籍目前为两章节选，不是整本小说。
- **建议第一步**：启动应用，打开「经典名著」第一章，检查翻译、查词和句子解析缓存。

Updated by Codex · 2026-11-26 23:10 +08:00

## 2026-11-26 文章精读页护眼模式（最新）

- **当前状态**：已在文章精读页工具栏新增 `#eyeCareBtn`（「护眼」）开关，基于 `readingEyeCare` 持久化与 `storage` 跨标签同步；`app.css` 仅在 `.article-page[data-eyecare="1"]` 下覆盖浅色暖纸与深色暖褐变量（含 `--hl: #e6dac2` / `#3d3427`，使 `.badge.phrase` 同步呈暖色调），不影响全局主题与其他页面。
- **验证**：`tests/test_article_reading.py` 6 passed（无头 Chrome 覆盖浅色/深色主题下护眼开关、持久化及纸张背景色断言）；此前全量 `uv run --no-sync python -m pytest -q` 为 **273 passed**。
- **遗留问题**：静态资源需在浏览器强制刷新（`Ctrl+Shift+R`）后查看新样式；原有工作区未提交改动均保留。
- **建议第一步**：刷新文章精读页，分别在浅色和深色主题下点击「护眼」按钮检查正文、辅助栏、浮层与查词弹窗的暖色一致性。

Updated by Antigravity · 2026-11-26 22:49 +08:00

## 2026-11-26 文章解析缓存与操作条

- **当前状态**：文章解析内存缓存同步渲染；请求期间禁用引擎及刷新，同句重复操作不会重复请求。句子悬停有柔和底色，浮层在正文位置不足时移至侧边；文章缓存位于独立文章目录，删除文章时一并删除。
- **验证**：全量 `uv run --no-sync python -m pytest -q` 为 273 passed；无头 Chrome 覆盖浅色/深色、桌面/窄屏，以及缓存、请求失败与竞态、操作条避让和目标保持。
- **遗留问题**：未调用真实 AI 服务，也未使用真实音频设备实听。原有工作区改动均保留。
- **建议第一步**：刷新文章精读页，打开一句解析并试用朗读。

Updated by Codex · 2026-11-26 21:55 +08:00

## 2026-11-26 文章精读工具栏重设计（最新）

- **当前状态**：已完成文章精读页 `.article-tools` 样式、布局与尺寸重设计（`34px` 等高、`9px` 圆角、左右分组对齐、紧凑 `A− | A+` 步进器、内联 SVG 图标、激活态统一）。
- **验证**：全量 `uv run --no-sync python -m pytest -q` 273 passed；`tests/test_article_reading.py` 已在无头 Chrome 浅色/深色与桌面/窄屏下校验工具栏等高与对齐。
- **遗留问题**：静态资源需在浏览器刷新（`Ctrl+Shift+R`）后查看新样式。
- **建议第一步**：刷新文章精读页，确认顶部工具栏在浅色/深色及窄屏下的视觉观感。

Updated by Antigravity · 2026-11-26 21:27 +08:00

## 2026-11-26 文章精读与句子解析

- **当前状态**：文章页已接入真实文章、查词、收藏及句子解析接口；文章解析缓存位于各文章目录，删除文章时一并清理。
- **验证**：全量 pytest 271 passed；Chrome 覆盖浅色/深色、桌面与窄屏、句级操作、收藏、模拟 TTS、引擎缓存及请求竞态；另在 320px 视口验证触屏操作与查词。
- **遗留问题**：未调用真实 AI 服务，也未通过音频设备实听；工作区原有未提交改动均保留。
- **建议第一步**：打开一篇已有文章，选择句子试用「解析」和「朗读全文」。

Updated by Codex · 2026-11-26 20:47 +08:00

## 2026-11-26 字幕显示切换（最新）

- **当前状态**：全局为「双语精读 / 英文精读」，当前句有独立「双语 / 英文」控件；对应字幕列表同步。单句覆盖在当前页面保留，全局切换清除全部单句覆盖；C 同步全局选择，P 仍控制逐句暂停。
- **验证**：Chrome 模拟播放器测试浅色/深色、两种初始设置、切换、句子导航、听写输入和窄布局；全量 pytest 251 passed。
- **遗留问题**：未用真实视频媒体验收；本次改动未提交。
- **建议第一步**：刷新播放器，切换全局与当前句显示并观察字幕列表。

Updated by Codex · 2026-11-26 19:30 +08:00

Updated by Codex · 2026-11-26 23:10 +08:00

## 2026-11-26 句子解析独立引擎切换（最新）

- **当前状态**：已在句子解析弹窗底部新增 `#lessonEngine`（「本地解析」/「AI 精讲」）下拉框与 `localStorage.lessonEngine` 记忆，支持独立于全局翻译引擎切换并严格隔离显式切换时的缓存；错误态（如未配置 API 返回 400）仍保留 `#lessonEngine` 供切回。
- **验证**：`uv run --no-sync python -m pytest -q` 全量 **247 passed**（耗时 41.04s），新增覆盖全局 `local` 下使用已保存 API 配置、未配置 API 返回 400、非法 `engine` 返回 400、显式 `engine="local"` 不复用 `api` 缓存。
- **遗留问题**：本轮未启动浏览器进行 UI 交互与浅/深色主题视觉验收。
- **建议第一步**：刷新播放器页面，打开「句子解析」弹窗测试「本地解析」与「AI 精讲」切换、刷新记忆保持及未配置 API 时的 400 回退交互。

Updated by Antigravity · 2026-11-26 19:21 +08:00

## 2026-11-26 句子解析前后端缓存优化

- **当前状态**：已完成 `/api/sentence/analyze` 后端磁盘缓存键收敛（`lesson-v9`）、本地模式复用 API 缓存修复、`force` 强制重解透传，以及播放器前端内存缓存 `lessonCache`、「已缓存」状态提示和「重新解析」按钮。
- **验证**：`uv run --no-sync python -m pytest -q` 全量 **243 passed**（耗时 28.12s），覆盖缓存命中、切模型/改 `notes` 命中、本地模式复用 API 缓存、`force=True` 强制重解及端点透传。
- **遗留问题**：本轮未启动浏览器做前端交互截图验收，旧版 `lesson-v8` 磁盘缓存保留但不再读取（首次解析将按 `lesson-v9` 重建）。
- **建议第一步**：刷新播放器页面，点击同一句的「句子解析」确认二次秒开显示「已缓存」，并测试「重新解析」按钮与 `profilechange` 清缓存行为。

Updated by Antigravity · 2026-11-26 17:24 +08:00

## 2026-11-26 字幕收藏星标（最新）

- **当前状态**：字幕收藏星标放大到 18px，收藏和悬停为黄色；提交 `bc55af3` 已推送至 `origin/main`。
- **验证**：Chrome 检查浅色与深色主题的未收藏、已收藏尺寸、颜色及居中，均通过。
- **遗留问题**：此前的句子解析修复及其他工作区改动仍未提交，本次只推送星标样式。
- **建议第一步**：刷新播放器，检查字幕时间下方的收藏星标。

Updated by Codex · 2026-11-26 17:19 +08:00

## 2026-11-26 句子解析验收修复（最新）

- **当前状态**：真实 ECDICT 英文标签可匹配中文轨道；模型与本地词汇只返回目标标签，长释义和变形说明得以保留。API 降级直接从句子选词，不重跑本地句法结构。
- **验证**：真实本地 ECDICT 候选词进入模型结果；全量 `uv run --no-sync python -m pytest -q` 为 240 passed。
- **遗留问题**：本轮 API 响应使用模拟数据，未调用真实 LLM；旧版本缓存保留但不再读取。
- **建议第一步**：使用已有模型配置分析一句包含六级词汇的字幕，核对真实响应。

Updated by Codex · 2026-11-26 16:56 +08:00

## 2026-11-26 模型选择器与来源弹窗（最新）

- **当前状态**：模型长名称在框内显示省略号，悬停可看全名；来源按钮紧邻标题，弹窗正确显示纯文本信息。
- **验证**：Chromium 在 280–1440px 下无横向溢出，模拟切换成功、失败回退和来源空状态均通过；`tests/test_server.py` 与 `tests/test_i18n.py` 共 30 项通过。
- **遗留问题**：先前关于浏览器缓存及不支持 `@supports` 的归因未证实，不应继续引用。Firefox 和 Safari 未实测。静态资源缓存范围的 Python 改动将在服务下次启动后生效；当前页面 CSS/HTML 已可刷新加载。
- **建议第一步**：刷新视频精听导入页，查看当前模型名称和标题旁的来源按钮。

Updated by Codex · 2026-11-26 16:16 +08:00

## 句子解析弹窗扁平化（最新）

- **当前状态**：`/api/sentence/analyze` 的契约与弹窗均已改为 `sentence / translation / structure / vocabulary / expressions` 五字段，弹窗按「句子解析」标题、英文原句、中文译文、句子结构、重点词语、重点搭配的固定顺序渲染。三个区块始终显示，无内容时显示一行灰色空状态。
- **本轮补充**：词汇列表不显示考试标签，保持「单词：词性 释义」；标签只在点击词汇后的查词卡片里显示为彩色胶囊（中考/高考/四级/六级/考研/托福/雅思/GRE 各用一种颜色，`.exam-tag`）。`/api/lookup` 新增 `tags` 字段，数据仍来自 ECDICT。
- **目标对齐**：重点词语只保留「我的目标」轨道对应的词，并向上拓宽一档：`TRACK_EXAMS = {cet4: 四级+六级, cet6: 六级+考研, ielts: 雅思+托福}`。`goals.track()` 读 `track`，`sentence.analyze(..., track)` 过滤；区块标题只写「重点词语」，不显示范围。模型结果过滤后为空时回退本地同轨词汇。缓存 `lesson-v5`，键含轨道。
- **收藏图标**：所有 ★/☆ 字符换成内联 SVG 星标（`common.js` 的 `starSvg(on)`，描边/填充两种状态），按钮改 inline-flex 居中；侧栏收藏入口用 CSS mask 的 SVG 星形。
- **单词解释框**：统一为同一套卡片与徽标，单词一律「查词」；`.note.word` 的赭色边框和 `.badge.word` 的赭色已移除。查词接口与单句解析返回的标签都按目标范围过滤（六级目标只出现六级/考研），缓存 `lesson-v6`。
- **难词逻辑**：`annotate.py` 的词条现在带 `tags`（中文考试名数组）；`common.js` 的 `TRACK_SCOPE`/`scopeTags()` 同时过滤标注高亮和弹窗标签。难词本身仍按 ECDICT 词频排名落在 `markRange`（当前词汇量到目标+15%）之间、排除已认识词、每句 2~3 个。
- **验证**：`uv run --no-sync python -m pytest -q` → 221 passed；Chrome 无头模式在隔离库上 39/39 PASS（含范围外词不标注、范围内外卡片标签差异）。截图在 `%TEMP%\echoloop-player-shots\final-{desktop,word-card,narrow}.png`。
- **注意**：ECDICT 标签分布不均，样例句在六级+考研范围内仍只有 `conference` 命中，属预期；要再放宽就调整 `TRACK_EXAMS`。
- **遗留问题**：真实 LLM 返回只经过 mock 测试，未实际调用模型核对 JSON；深色主题未重新截图验收。临时库里写入的收藏只存在于 `%TEMP%\echoloop-flat\lib`。
- **建议第一步**：需要核对真实模型输出时，配置好 API Key 后对一句真实字幕请求 `/api/sentence/analyze`，检查 `structure/vocabulary/expressions` 是否完整。

Updated by Codex · 2026-11-26

## 播放器精读改造

- **当前状态**：三项改造已完成并通过验证。Windows 全量 pytest 211 项通过；Chrome 在隔离库上完成 33 项交互检查，截图保存在 `%TEMP%\echoloop-player-shots`。真实资料库未被写入测试数据。
- **行为说明**：「逐句精读」复用设置页的「逐句暂停」（`autoPause`）。每句播完暂停，再按播放进入下一句。右侧「逐句字幕 / 本片词句」面板和听写练习入口保留。
- **遗留问题**：本地引擎的精讲由句法规则和词典拼成，质量低于模型精讲。词汇的考试标签来自 ECDICT，部分词（如 `quickly`、`vulnerability`）在库中没有标签，短语没有标签，此时只显示「词汇」。模型可能把同一个短语同时列入重点搭配和词汇。界面文案尚未加入 `i18n` 翻译表，非中文界面下会保持中文。
- **建议第一步**：如需改进本地精讲或补充界面翻译，先运行 `uv run --no-sync python -m pytest -q tests/test_sentence.py`。

Updated by Codex · 2026-11-26

## 项目背景

- 共享记忆库已初始化。Gemini CLI 入口 `GEMINI.md` 通过 `@./AGENTS.md` 加载项目规则。
- 原有改名与功能改动仍在当前工作区和暂存区。Windows 上现有 pytest 套件已跑通 185 项。

## 此前验证

- 本轮 pytest 无报错。浏览器、真实媒体导入及云端服务尚未做端到端验证。本机缺少 Gemini CLI，已按官方导入语法检查文件内容和引用路径。

## 方案准备

- 收到开发指令后，按 `AGENTS.md` 读取三份共享记忆文件，再用 `git status --short` 核对当前工作区，识别已有改动。
- 本轮已将第一人称完整可执行计划写入 `transfer/局限性问题修复方案.md`，未修改源码与测试。

## 本地翻译核对

- 当前设置为 API 翻译。离线路径使用 Argos 模型及分词器，直接由 CTranslate2 在 CPU 上运行。本机已安装英译中模型 1.9，单句离线推理通过。
- 核对时保留了现有翻译设置。若继续检查离线翻译，入口见 `src/echoloop/translate.py` 中的 `translate_local`。

## 词组检测验收

- **当前状态**：方案四步已完成。新增 13 项回归测试，Windows 全量 198 项通过。Chrome 在隔离的版本 6 视频和文章上实测普通及逐词对照模式，18 次高亮点击均显示正确释义。
- **真题抽样**：四级长句命中 take account of，六级长句同时命中 Figuring out 和 shed light on。来源见[四级真题](https://www.tccu.edu.cn/jcb/2023/0428/c1832a38915/page.htm)和[六级真题](https://wy.jssnu.edu.cn/_t73/2015/0701/c746a3501/page.htm)。
- **遗留问题**：依存树将目标介词挂到嵌套动词时仍可能漏检，例如 They attribute a desire to succeed to their training. 未扩展为跨从句搜索。
- **建议第一步**：后续若调整词组规则，先运行 `uv run --no-sync python -m pytest -q tests/test_phrase_annotation.py`。
- **代码复核与复测**：Antigravity 已逐文件复核 `src/echoloop/{annotate.py,dictionary.py,phrases_curated.json}` 与 `tests/test_phrase_annotation.py`，并复跑 `uv run --no-sync python -m pytest -q`（198 passed in 19.92s），确认 4 步改造及单测均符合计划要求（本轮未重开浏览器复测）。

Updated by Antigravity · 2026-11-26 11:01 +08:00

## 视频精听收藏图标与字幕时间戳（最新）

- **当前状态**：
  - 收藏图标已居中：`.cue .tm .save-sent` 改为 13px 无边框 flex 居中，复用 `common.js` 的 `starSvg`，未新建 SVG（`src/echoloop/static/app.css`）。
  - 红框重复已修：`src/echoloop/media.py` 新增 `_TS_LINE`，`_clean_text` 首步剥离字幕文本内重复出现的时间行。根因是源 SRT/VTT 的文本行本身含 `00:01:24.917 --> 00:01:30.076`，原解析器只取首条时间行、把文本内的 `-->` 当可见文字渲染，导致英文与中文各出现一次时间戳+句子重复。
- **验证**：`uv run --no-sync python -m pytest -q` 221 passed；用截图同款 SRT 块复测，`-->` 不再出现在 cue 文本中。
- **遗留事项**：截图里句子文本本身仍出现两次（源 SRT 就写了两次），这是源数据内容，非解析器产物，未改动。
- **建议下一步**：在浏览器打开视频精听页，确认收藏星标在 39px 时间列内居中、红框 cue 不再显示时间戳。

## 发布交接

- 当前状态：已核实 origin/main 指向 724dc84。
- 遗留事项：EchoLoop 改名及其他功能改动仍在本地。
- 建议第一步：后续发布改名时，将新测试的 echoloop 导入与其他包路径改动一并提交。

Updated by Codex · 2026-11-26 11:05 +08:00



## 2026-11-26 视频精听页 UI 修复

- 当前状态：已完成。导入页 API/模型选择器超宽已加 max-width 截断 + option title；player 标题右侧已加来源信息图标按钮 + 弹窗。pytest 222 项通过。
- 遗留事项：未做浏览器端视觉回归验证（本机无 GUI 浏览器）；绿框图标在窄屏（<700px）下随标题行换行，未单独断点调优。
- 建议下一个 Agent 执行的第一步：在浏览器打开视频精听页与 player 页，确认选择器截断与来源信息弹窗显示正常。

Updated by Codex · 2026-11-26 12:15 +08:00

- 2026-11-26 修复一批稳健性问题：`sentence._local_lesson` 候选词优先考纲标签词；`annotate.word_info` 全大写字幕不再误当专名、分词形容词继承原形标签，`_hard_words` 带标签词排前；`translate._json_reply` 容错前后说明文字，`meaning_instructions` 兼顾语境义与核心义项、CJK/非 CJK 分别限长，`MEANING_BATCH` 降为 20；`media._clean_text` 清理多次重复时间戳；`common.js`/`player.html`/`article.html` 前端状态与交互统一。新增 `tests/test_robustness.py`。


## 2026-11-26 静态资源缓存根因（重要）

- 当前状态：已修复。`server.py` `_file` 对所有静态资源发 `Cache-Control: no-cache`（此前仅 .html/.js 有，CSS 无头导致浏览器磁盘缓存旧 app.css，重启浏览器无效）。
- 服务已重启（PID 新），8765 在跑，version stale=false，pytest 226 通过。
- 遗留事项：用户浏览器仍可能缓存旧 app.css，需强制刷新（Ctrl+Shift+R 或清空缓存）才能看到本次两个 UI 改动。
- 建议下一个 Agent 执行的第一步：告知用户强制刷新浏览器；若仍无变化，检查是否连的是 8765 且非旧端口。

Updated by Codex · 2026-11-26 12:50 +08:00


## 2026-11-26 下拉框超出——真因与状态

- 当前状态：已修复。截断规则原写在 `@supports (appearance: base-select) and selector(select::picker(select))` 内，用户浏览器不匹配 → 规则被丢弃 → 刷新无效。已移到 @supports 外，改用容器 max-width + select width:100%（select 不响应 max-width/text-overflow）。
- 服务在跑（8765，PID 36436），CSS 发 no-cache，pytest 229 通过。
- 遗留事项：需用户浏览器强制刷新（Ctrl+Shift+R）确认；本地无 GUI 浏览器，未做像素级视觉验证。
- 建议下一个 Agent 执行的第一步：用户确认红框不再超出；若仍超出，检查是否连的 8765 且浏览器版本。

Updated by Codex · 2026-11-26 13:05 +08:00

- 2026-11-26 新增 `scripts/clean_old_timestamps.py <videoId> [--apply]`：清理旧库英文字幕里残留的时间戳行（默认预览，`--apply` 先备份为 `data.before-timestamp-clean.json`，并清掉受影响句的 marks/notes 以便重新标注）。已对 `tedtalk-1042` 的 39 句执行；中文译文里的乱码时间戳需用「重新翻译」处理。浏览器验收：精讲弹窗中 Esc 先关查词卡片、再关弹窗。

- 2026-11-26 补齐 `sentence.py` 清单：新增 `_track_candidates`（候选词前置，标签按空格拆分比较）、`_instructions(labels)`（raw JSON、non-overlapping、2–6 段、≤5 个单词、lemma 字段、meaning ≤15 字、expressions 不与 vocabulary 重复）、`_local_vocabulary`（API 词汇被过滤为空时只补词汇不重跑句法分析）；`_model_lesson` 读 lemma 并保留、按 candidates 过滤；`_local_lesson` 的 `word` 存原句词形、`lemma` 存原型；缓存版本 `lesson-v6`→`lesson-v7`，`analyze` 显式构造 `target` 路径。新增 6 个用例。全量 234 项通过。

Updated by Codex · 2026-11-26 16:56 +08:00

Updated by Codex · 2026-11-26 17:19 +08:00

Updated by Codex · 2026-11-26 19:30 +08:00

Updated by Codex · 2026-11-27 09:48 +08:00
