# 跨 Agent 协同与共享记忆协议

本项目由多个 AI Coding Agent（如 OpenAI Codex、Google Antigravity、Claude Code 等）接力开发。为保证上下文连贯、避免重复劳动与代码冲突，你必须严格遵守以下工作流规范。

## 1. 共享记忆目录结构
所有持久化状态均保存在项目根目录的 `.ai-memory/` 文件夹中：
- `.ai-memory/progress.md`：当前任务进度、已完成事项、待办清单（TODO）及最新改动的文件列表。
- `.ai-memory/decisions.md`：架构设计决策、技术选型理由及已踩过的坑（严禁推翻已记录的决策，除非用户明确要求）。
- `.ai-memory/handoff.md`：交接备忘录，用于记录当前未完结的调试现场、临时命令或下一步具体指令。

## 2. 强制执行生命周期（Read -> Execute -> Write）

### 阶段一：开工前（强制读取）
在回答任何问题、修改任何代码或执行任何终端命令**之前**，你必须先检查并读取：
1. `.ai-memory/progress.md`
2. `.ai-memory/decisions.md`
3. `.ai-memory/handoff.md`
（如果上述文件尚不存在，请主动创建 `.ai-memory/` 目录并初始化这些文件。）

### 阶段二：执行中（约束规范）
- 修改代码前，先确认是否与 `decisions.md` 中的约定冲突。
- 保持修改原子化，不要顺手重构与当前任务无关的模块，以免干扰其他 Agent 的工作区。

### 阶段三：收工前（强制更新）
在结束本轮任务、向用户汇报结果**之前**，你必须更新记忆文件（保持语言精炼，使用要点列表，避免长篇大论）：
1. **更新 `.ai-memory/progress.md`**：将已完成的项移入“已完成”，补充新发现的“待办事项”，并列出本轮修改的核心文件路径。
2. **更新 `.ai-memory/decisions.md`**（仅当本轮做出了重要架构调整或解决了隐蔽 Bug 时追加）。
3. **更新 `.ai-memory/handoff.md`**：写明【当前状态】、【遗留问题/报错信息】以及【建议下一个 Agent 执行的第一步操作】，并在末尾标注你的身份与时间戳（例如：`Updated by Antigravity / Codex`）。