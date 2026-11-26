# EchoLoop 基础架构

以下基线来自当前代码与配置。

- **运行与入口**。Python 3.12+，由 `uv` 管理，依赖见 `pyproject.toml` 和 `uv.lock`。`uv run echoloop` 进入 `src/echoloop/__init__.py`，由 `server.py` 使用标准库 `ThreadingHTTPServer` 提供页面和 JSON API。默认地址为 `127.0.0.1:8765`。根目录 `EchoLoop.bat` 是 Windows 启动入口，`scripts/` 存放平台脚本，`assets/` 存放图标、打包脚本与截图。
- **界面与学习功能**。`src/echoloop/static/` 存放原生 HTML、CSS、JavaScript，`i18n.py` 与 `i18n/` 提供界面语言。`goals.py`、`placement.py`、`plan.py` 管理备考目标、测评和计划。`reading.py`、`review.py`、`speaking.py`、`writing.py` 等模块实现学习功能。
- **媒体和语言处理**。`pipeline.py` 管理后台导入任务与进度，经 `media.py` 用 yt-dlp、Deno 与 FFmpeg 获取并处理媒体，优先取字幕，必要时用 Whisper 转写。Apple Silicon 使用 MLX Whisper，其余平台使用 faster-whisper。注释与词义依赖 spaCy 和 ECDICT，翻译支持本地 Argos 或用户配置的兼容 API，朗读使用 Kokoro。
- **持久化与兼容性**。学习记录以本地 JSON 和媒体文件保存。`data/` 存放词典及应用设置，`library/` 存放媒体库及学习记录，`articles/` 存放自建和分级阅读材料。三处均被 Git 忽略。`backup.py` 管理 ZIP 备份与恢复，支持旧 IELTS Study 备份。新环境变量采用 `ECHOLOOP_*`，`config.py` 为已有入口保留相应旧变量兼容。
- **验证入口**。`tests/` 使用 pytest。`.github/workflows/tests.yml` 为各平台准备 ECDICT 后运行测试。已有依赖和词典时，可用 `uv run --no-sync python -m pytest -q` 复跑。
- **主动式 attribute … to**。本项目的 spaCy 模型在验收句中将第一个介词 to 挂在直接宾语 failure 上。规则优先检查动词本身，再检查其直接宾语的介词子节点，避免误选同句其他动词的 to。
