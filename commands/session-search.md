---
description: Search Claude Code session history and print resume commands
argument-hint: "[--all] [关键词]"
allowed-tools: Bash(python3:*)
---

执行：

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/search_sessions.py $ARGUMENTS
```

把结果呈现给用户：

- `/session-search` 列出当前项目历史会话（按时间倒序）
- `/session-search <关键词>` 在当前项目历史里搜正文
- `/session-search --all` 列出全部项目历史会话
- `/session-search --all <关键词>` 在全部项目里搜

每条结果包含：项目名 / 时间 / 首条用户消息摘要 / `claude --resume <sessionId>`。

提醒用户：resume 命令要在**新终端**里运行，不能在当前会话内执行。
