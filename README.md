# session-finder

Claude Code 会话工具箱：搜索恢复、导出分享、跨会话记忆。

## 功能

### 1. `/session-search` — 搜索历史会话

- `/session-search` — 列出**当前项目**历史会话（按时间倒序）
- `/session-search <关键词>` — 在当前项目历史里搜正文
- `/session-search --all` — 列出**全部项目**历史会话
- `/session-search --all <关键词>` — 全部项目里搜

每条结果打印：项目名 / 时间 / 首条用户消息摘要 / `claude --resume <sessionId>`。
resume 命令请在**新终端**中运行。

### 2. `/session-export` — 导出/分享会话

把历史会话导出成 markdown / html，可推送到 GitHub Gist 分享。

```sh
python3 scripts/export_session.py [<sessionId>] [--all]
    [--format md|html] [--output FILE] [--gist] [--public]

# 不带 sessionId = 导出当前项目最近会话
```

- 默认导出当前项目最近会话为 markdown 到 stdout
- `--format html` 导出可直接打开的 HTML
- `--gist` 推送 secret gist（🚨 内容含完整对话与代码，知道链接即可看）
- `--public` 生成公开 gist（会被索引，三思）

依据：本机 `gh` CLI 已登录且 token 带 `gist` scope。

### 3. 跨会话记忆（自动）

启用插件后自动生效，无需手动操作：

- **Stop hook**：每轮对话结束后（节流 5 分钟）把本会话的关键信息
  （消息数 / 常用工具 / 写过的文件 / 最后一段摘要）追加到项目记忆。
- **SessionStart hook**：新会话开始时自动把该项目的记忆注入上下文，
  不必重新解释背景。

记忆存放在 `~/.claude/plugins/data/session-finder/memory/<项目路径>.md`
（按项目隔离，滚动保留最近 5 次会话）。这是 Claude Code 官方规定的插件
持久数据目录，不会污染你的项目目录。当前版本用本地规则总结（零 LLM 成本），
LLM 智能总结留了接口、默认关闭。

## 安装

```sh
claude plugin install /path/to/session-finder
```

或直接本仓库：

```sh
claude plugin install https://github.com/Jack11111eee/deja-claude
```

## 原理

会话存储在 `~/.claude/projects/<路径转义>/<sessionId>.jsonl`（`/` 转义为 `-`）。
纯 Python 标准库解析，只保留 `type == "user" | "assistant"` 的记录；`tool_use`/
`tool_result` 配对渲染，过滤 `<system-reminder>` / `<command-*>` 等框架噪音。
所有脚本无三方依赖。

## Backlog（后续迭代，暂未做）

- 多会话并行管理（tmux / git worktree，复杂度高）
- 跨会话记忆的 LLM 智能总结
- PDF 导出、语义搜索、向量索引、fzf 交互
