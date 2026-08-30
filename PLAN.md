# session-finder 设计方案

## 目标
在 Claude Code 会话内部搜索历史会话，打印 `claude --resume <id>` 命令。

## 行为
- `/session-search`               → 列出**当前项目**历史会话（按时间倒序）
- `/session-search <关键词>`       → 在当前项目历史里搜正文
- `/session-search --all`          → 列出**全部项目**历史会话
- `/session-search --all <关键词>`  → 全部项目里搜

每条结果打印：项目名 / 时间 / 首条用户消息摘要 / `claude --resume <sessionId>`。

## 关键事实（已调研确认）
- 会话存储: `~/.claude/projects/<路径转义>/<sessionId>.jsonl`
- 路径转义: `/` → `-`（`/Users/x/p` → `-Users-x-p`）
- 有效消息: `type == "user"|"assistant"`，正文在 `message.content`（str 或 list[{type:text,text}]）
- 其余 type（mode/permission-mode/file-history-snapshot/attachment/ai-title/cost-state…）跳过
- 每条记录含 `timestamp`(ISO8601), `cwd`, `gitBranch`, `sessionId`
- 当前项目目录名: `os.getcwd()` 的绝对路径做 `/`→`-` 转义
- resume 命令: `claude --resume <sessionId>`（sessionId = 文件名去 .jsonl）

## plugin 结构
```
session-finder/
├── .claude-plugin/plugin.json
├── commands/session-search.md
├── scripts/search_sessions.py
├── PLAN.md
└── README.md
```

## 实现要点
### search_sessions.py（纯 Python 无三方依赖，无需 LLM）
- argparse: `query`（可选位置参数）, `--all `--limit N（默认 20）, `--json`
- `iter_projects()`: 遍历 `~/.claude/projects/*`
- `parse_session(jsonl_path)`: 逐行 json.loads，只保留 type user/assistant；
  抽出 first_user_message（content 为 list 时拼 text 部分）、最后时间戳、消息数
- `search(project_dirs, query)`: 对每个 jsonl，若 query 为空则全收，否则在拼接的
  user/assistant 正文里做大小写不敏感子串匹配；命中则记录命中片段上下文
- 输出: 按最后活跃时间倒序，每条打印
  `项目 | 最后时间 | 首条消息摘要(40字) | claude --resume <id>`
  若带 query，附命中片段上下文
- 防御：单行 json 解析失败跳过、文件读失败跳过、content 为 list 时取 text 块

### commands/session-search.md
frontmatter:
```
---
description: Search Claude Code session history and print resume commands
argument-hint: "[--all] [关键词]"
allowed-tools: Bash(python3:*)
---
执行: python3 <plugin>/scripts/search_sessions.py $ARGUMENTS
并把结果呈现给用户；强调 resume 命令要在**新终端**运行。
```

### plugin.json
```
{
  "name": "session-finder",
  "version": "0.1.0",
  "description": "Search Claude Code session history from inside a session and print resume commands",
  "commands": "./commands"
}
```

## 验证步骤
1. `python3 search_sessions.py --all 杭州` 应能列出 hangzhou-weather 的会话
2. `python3 search_sessions.py` 在本项目目录应只列本项目会话
3. 手动复制一条 resume 命令到新终端，确认能恢复
4. `claude plugin` 加载本目录后 `/session-search 杭州` 可用

## 暂不做（后续迭代）
- 多会话并行管理、跨会话持久记忆（第二三迭代）
- 语义搜索 / 向量索引 / fzf 交互
- 会话导出分享
