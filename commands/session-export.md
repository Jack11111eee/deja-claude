---
description: Export a Claude Code session to markdown/html, optionally share via gist
argument-hint: "[sessionId] [--all] [--format html] [--gist] [--public]"
allowed-tools: Bash(python3:*)
---

执行：

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/export_session.py $ARGUMENTS
```

用法：

- `/session-export` — 导出当前项目最近的会话为 markdown（打印到输出）
- `/session-export <sessionId>` — 按 id 导出（在当前项目里找）
- `/session-export <sessionId> --all` — 跨全部项目按 id 找
- 加 `--format html` 导出 HTML；加 `--output FILE` 写入文件
- 加 `--gist` 推送到 GitHub gist（默认 secret），返回可分享链接；`--public` 生成公开 gist

提醒用户：

- 导出的 markdown 可直接贴博客/wiki；gist 链接可直接分享。
- **gist 内容包含完整对话与代码**，secret 知道链接即可看，`--public` 会被搜索引擎索引，三思。
- sessionId 可以先用 `/session-search` 找到。
