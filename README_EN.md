# session-finder

**中文说明**: [README.md](README.md)

> **Positioning**: Everything — plugins, TUI, utilities — is integrated as a **Claude Code Plugin**.

A toolbox for Claude Code sessions: search & restore / export & share / cross-session memory.

---

## Feature Overview

| Capability | Trigger | What it does |
|---|---|---|
| **Search history** | `/session-search` | Find past sessions and print `claude --resume` commands |
| **Export & share** | `/session-export` | Export a session to markdown / html, optionally push to GitHub Gist |
| **Cross-session memory** | Automatic (hooks) | Persist key context between sessions; inject it into new sessions |

All scripts are pure **Python standard library** — no third-party dependencies, no API keys required.

---

## Usage

### 1. `/session-search` — Search Claude Code session history

Find past sessions across all your projects, right from inside a Claude Code session, and get a ready-to-run resume command.

```sh
/session-search                    # list current-project history (recent 20)
/session-search <keyword>          # search full text within current project
/session-search --all              # list history across all projects
/session-search --all <keyword>    # search across all projects
```

Each result shows: `project │ timestamp │ first user message excerpt │ claude --resume <sessionId>`

> ⚠️ Run the `claude --resume` command in a **new terminal tab** — not inside the current session.

### 2. `/session-export` — Export / share a session

Export a session to clean markdown or HTML. Optionally share via GitHub Gist in one command.

```sh
/session-export                          # export latest session in current project to stdout
/session-export <sessionId>              # export by id (searched in current project)
/session-export <sessionId> --all        # search id across all projects
/session-export --format html            # export as HTML
/session-export --output report.md       # write to file
/session-export --gist                   # push to a secret gist, returns a share URL
/session-export --gist --public          # create a PUBLIC gist (indexable — think twice)
```

- `--gist` requires the `gh` CLI to be authenticated with `gist` scope.
- Framework noise (`system-reminder`, `command-*`, etc.) is filtered out automatically; `tool_use`/`tool_result` pairs are rendered together.

### 3. Cross-session memory (automatic, zero setup)

No manual trigger needed — runs automatically once the plugin is installed:

- **`Stop` hook**: after each turn (throttled to once per 5 minutes), appends a summary of the session to a project-scoped memory file. Captures: message count, most-used tools, files written, and a snippet of the last assistant reply.
- **`SessionStart` hook** (fires on `startup | resume | compact`): injects the project's memory into context at the start of a new session, so you don't have to re-explain the background.

Memory files live at:

```
~/.claude/plugins/data/session-finder/memory/<escaped-project-path>.md
```

- Isolated per project.
- Rolling window — only the **last 5 sessions** are kept.
- Context injection capped at **9000 characters** (truncated if exceeded).
- This is the official Claude Code plugin data directory; it does not touch your project workspace.

The current version generates summaries with **local rules (zero LLM cost)**. An LLM-powered smart summarization hook is stubbed in but disabled by default.

---

## Installation

**From a local directory:**

```sh
claude plugin install /path/to/session-finder
```

**From GitHub:**

```sh
claude plugin install https://github.com/Jack11111eee/deja-claude
```

Restart your Claude Code session after installing — hooks take effect automatically.

---

## Directory Structure

```
session-finder/
├── .claude-plugin/
│   └── plugin.json              # plugin metadata
├── commands/
│   ├── session-search.md        # /session-search command definition
│   └── session-export.md        # /session-export command definition
├── hooks/
│   └── hooks.json               # SessionStart + Stop hook registrations
├── scripts/
│   ├── search_sessions.py       # /session-search implementation
│   ├── export_session.py        # /session-export implementation
│   ├── memory_common.py         # shared helpers for memory hooks
│   ├── session_start_hook.py    # SessionStart hook entrypoint
│   └── stop_hook.py             # Stop hook entrypoint
├── AGENTS.md
├── PLAN.md
├── LICENSE                      # MIT
└── README.md                    # this file (CN) — see README_EN.md for EN
```

---

## How it works (one-liner)

Claude Code stores sessions at `~/.claude/projects/<escaped-path>/<sessionId>.jsonl` (with `/` → `-` in paths). Scripts parse each line as JSON, keep only records with `type == "user" | "assistant"` for search/export, and silently skip everything else (mode / permission / attachment / ai-title / cost-state …).

---

## Requirements

| Requirement | Purpose |
|---|---|
| Python 3 (stdlib only, any version) | Runs all scripts |
| `gh` CLI + authenticated (optional) | `--gist` sharing |
| `claude` CLI | Plugin host |

---

## Roadmap / Backlog

- [ ] Multi-session parallel management (tmux / git worktree)
- [ ] LLM-powered memory summarization
- [ ] PDF export / semantic search / vector index / fzf UI

---

## License

[MIT](LICENSE)
