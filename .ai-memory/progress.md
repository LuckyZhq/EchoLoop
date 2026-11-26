# EchoLoop 项目进度

## 已完成

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

- 本次方案验收完成。更复杂的嵌套从句仍受 spaCy 依存分析质量限制。

## 本轮文件

- 播放器改造：`src/echoloop/static/{player.html,app.css,common.js}`、`src/echoloop/{server.py,sentence.py}`、`tests/test_sentence.py`
- 视频精听收藏图标居中（去边框，复用 starSvg）：`src/echoloop/static/app.css`；字幕文本内残留时间戳行清理：`src/echoloop/media.py`
- `src/echoloop/annotate.py`、`src/echoloop/dictionary.py`、`src/echoloop/phrases_curated.json`、`tests/test_phrase_annotation.py`、`.ai-memory/{progress,decisions,handoff}.md`

## 发布

- 词组修复和 13 项回归测试已推送至 origin/main（724dc84）。在远端包结构中独立验证，全量 189 项通过。

