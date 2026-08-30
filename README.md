# session-finder

在 Claude Code 会话内部搜索历史会话，打印 `claude --resume <id>` 命令。

## 用法

- `/session-search` — 列出**当前项目**历史会话（按时间倒序）
- `/session-search <关键词>` — 在当前项目历史里搜正文
- `/session-search --all` — 列出**全部项目**历史会话
- `/session-search --all <关键词>` — 全部项目里搜

每条结果打印：项目名 / 时间 / 首条用户消息摘要 / `claude --resume <sessionId>`。
resume 命令请在**新终端**中运行。

也可以直接运行脚本（纯 Python，无三方依赖）：

```sh
python3 scripts/search_sessions.py [--all] [--limit N] [--json] [关键词]
```

## 安装

```sh
claude plugin install /path/to/session-finder
```

## 原理

会话存储在 `~/.claude/projects/<路径转义>/<sessionId>.jsonl`（`/` 转义为 `-`）。
脚本逐行解析 jsonl，只保留 `type == "user" | "assistant"` 的记录做正文匹配，
按最后活跃时间倒序输出，sessionId 即文件名去掉 `.jsonl`。
