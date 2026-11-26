# EchoLoop 交接

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

