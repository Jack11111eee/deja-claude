# session-finder

**English**: [README_EN.md](README_EN.md)

> **定位**：所有插件、TUI 等等全部集成进 **Claude Code Plugin**。

Claude Code 会话工具箱：搜索恢复 / 导出分享 / 跨会话记忆。

---

## 功能概览

| 能力 | 触发方式 | 说明 |
|------|----------|------|
| **搜索历史会话** | `/session-search` | 找到历史会话并输出 `claude --resume` 命令 |
| **导出分享** | `/session-export` | 把会话导出为 markdown / html，或推送到 GitHub Gist |
| **跨会话记忆** | 自动（hooks） | 会话间自动记忆关键上下文，新会话自动注入 |

所有脚本纯 Python 标准库实现，**无三方依赖**，不需要 API key。

---

## 详细用法

### 1. `/session-search` — 搜索历史会话

在 Claude Code 会话内直接搜索所有项目的历史会话，拿到可恢复的命令。

```sh
/session-search                    # 列出当前项目历史（按时间倒序，默认 20 条）
/session-search 关键词              # 在当前项目历史正文里搜索
/session-search --all               # 列出全部项目历史
/session-search --all 关键词        # 全部项目里搜
/session-search --limit 10          # 限制结果数量
/session-search --json              # 输出机器可读 JSON
```

每条结果输出：`项目名 │ 时间 │ 首条用户消息摘要 │ claude --resume <sessionId>`

> ⚠️ `claude --resume` 命令请**复制到新终端**运行，不要在当前会话里执行。

### 2. `/session-export` — 导出/分享会话

把会话记录导出为干净的 markdown 或 HTML，可选推送到 gist 一键分享。

```sh
/session-export                          # 导出当前项目最近会话为 markdown（stdout）
/session-export <sessionId>              # 按 id 导出（在当前项目里找）
/session-export <sessionId> --all        # 跨全部项目按 id 找
/session-export --format html            # 导出 HTML
/session-export --output report.md       # 写入文件
/session-export --gist                   # 推送 secret gist，返回可分享链接
/session-export --gist --public          # 生成公开 gist（可被搜索引擎索引，慎用）
```

- `--gist` 依赖本机 `gh` CLI 已登录且 token 带 `gist` scope。
- 导出时会自动过滤 `system-reminder`、`command-*` 等框架噪音，`tool_use` 和 `tool_result` 配对渲染。

### 3. 跨会话记忆（自动，无需操作）

装好插件后自动运行，无需任何手动触发：

- **`Stop` hook**：对话停顿/结束时触发（按 session 节流 5 分钟一次），把本会话的关键摘要追加到项目专属记忆文件。包括：消息数、常用工具、写过的文件路径、最后一段 assistant 回复摘要。
- **`SessionStart` hook**（触发时机：`startup | resume | compact`）：新会话开始时，把该项目的历史记忆注入上下文，不用重新解释项目背景。

记忆文件位于插件持久数据目录下，即 `${CLAUDE_PLUGIN_DATA}/memory/<项目路径-转义及哈希>.md`，实际路径形如：

```
~/.claude/plugins/data/<插件id>/memory/<项目路径-转义及哈希>.md
```

`<插件id>` 取决于安装方式（marketplace 安装一般是插件名；`--plugin-dir` 加载会带 `-inline` 后缀）。**注意**：换安装方式后旧记忆路径会跟着变，跨安装方式想保留记忆请手动迁移旧文件。

- 按项目隔离，互不影响。
- 滚动窗口只保留最近 **5 次**会话，不会无限增长。
- 上下文注入上限 **9000 字符**，超出会截断。
- 这是 Claude Code 官方规定的插件持久数据目录，不会污染你的项目仓库。

当前版本用**本地规则生成摘要（零 LLM 成本）**；LLM 智能总结仍是后续计划，当前没有对应实现。

---

## 安装

**方式 1：从本地目录临时加载（无需安装）**

```sh
claude --plugin-dir /path/to/session-finder
```

这只对当前 Claude Code 会话生效，不会写入全局插件安装记录。

**方式 2：通过 marketplace 安装**

先把包含本插件的 marketplace 添加到 Claude Code，再使用 marketplace 中声明的插件标识安装：

```sh
claude plugin install session-finder@<marketplace-name>
```

当前 Claude Code 的 `plugin install` 不接受本地目录或 GitHub URL；开发和本地验证请使用 `--plugin-dir`。重新开启会话后，已安装插件的 hooks 会自动生效。

---

## 插件目录结构

```
session-finder/
├── .claude-plugin/
│   └── plugin.json          # 插件元信息（名称、版本、描述、author）
├── commands/
│   ├── session-search.md    # /session-search 命令
│   └── session-export.md    # /session-export 命令
├── hooks/
│   └── hooks.json           # 注册 SessionStart + Stop hooks
├── scripts/
│   ├── search_sessions.py   # /session-search 的实现
│   ├── export_session.py    # /session-export 的实现
│   ├── memory_common.py     # 跨会话记忆的公共工具函数
│   ├── session_start_hook.py # SessionStart hook 入口
│   └── stop_hook.py          # Stop hook 入口
├── AGENTS.md
├── PLAN.md
├── LICENSE                   # MIT
└── README.md                 # 本文档
```

---

## 原理（一句话版）

Claude Code 把所有会话存在 `~/.claude/projects/<路径转义>/<sessionId>.jsonl`（路径里 `/` 换成 `-`）。脚本逐行 `json.loads` 解析，只保留 `type == "user" | "assistant"` 的记录做搜索或导出，其余 type（mode/permission/attachment/ai-title/cost…）全跳过。

---

## 依赖与前置要求

| 要求 | 用途 |
|------|------|
| Python 3.9+（仅标准库） | 所有脚本运行 |
| `gh` CLI + 登录（可选） | `--gist` 分享功能 |
| `claude` CLI | 插件宿主 |

---

## Backlog（后续迭代，暂未做）

原始需求清单里 B/D（跨会话记忆）、C/E（多会话并行）有重复，本插件实现了 A（导出分享）+ B/D（跨会话记忆），C/E 类需求暂缓：

- [ ] 多会话并行管理（tmux / git worktree）
- [ ] 跨会话记忆接入 LLM 智能总结
- [ ] PDF 导出 / 语义搜索 / 向量索引 / fzf 交互

---

## License

[MIT](LICENSE)
