#!/usr/bin/env python3
"""Stop hook: append a local-rule summary of this session to the project memory.

Reads hook input JSON from stdin (session_id, transcript_path, cwd). Throttled to
one write per session per THROTTLE_SECONDS so the per-turn firing doesn't spam.

Summary is purely local parsing (no LLM, no network): user message count, top
tools, files written, tail of the last assistant text.
"""

import json
import os
import re
import sys
import time
from collections import Counter

from memory_common import ensure_parent, memory_file_for, state_file_for

THROTTLE_SECONDS = 300
MAX_ENTRIES = 5
LAST_MSG_TAIL = 200

NOISE_PREFIXES = (
    "<system-reminder>", "<command-name>", "<local-command-",
    "<bash-", "<ide-", "<user-prompt-submit-hook>",
    "[Request interrupted by user",
)
WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")


def is_noise(text):
    t = text.strip()
    if not t:
        return True
    return any(t.splitlines()[0].startswith(p) for p in NOISE_PREFIXES)


def analyze_transcript(path):
    user_msgs = 0
    tool_counts = Counter()
    written_files = []
    last_assistant_text = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rtype = rec.get("type")
            if rtype not in ("user", "assistant"):
                continue
            content = (rec.get("message") or {}).get("content")
            blocks = content if isinstance(content, list) else []
            if rtype == "user":
                if blocks and isinstance(blocks[0], dict) and blocks[0].get("type") == "tool_result":
                    continue
                text = content if isinstance(content, str) else " ".join(
                    b.get("text", "") for b in blocks
                    if isinstance(b, dict) and b.get("type") == "text"
                )
                if text.strip() and not is_noise(text):
                    user_msgs += 1
            else:
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        name = b.get("name", "?")
                        tool_counts[name] += 1
                        if name in WRITE_TOOLS:
                            inp = b.get("input") or {}
                            p = inp.get("file_path") or inp.get("notebook_path")
                            if p and p not in written_files:
                                written_files.append(p)
                    elif b.get("type") == "text":
                        t = b.get("text", "").strip()
                        if t:
                            last_assistant_text = t
    return {
        "user_msgs": user_msgs,
        "tool_counts": tool_counts,
        "written_files": written_files,
        "last_assistant_text": last_assistant_text,
    }


def summarize(stats, session_id):
    top_tools = ", ".join(
        f"{name}x{n}" for name, n in stats["tool_counts"].most_common(5)
    ) or "none"
    lines = [
        f"- **Session `{session_id[:8]}`** ({time.strftime('%Y-%m-%d %H:%M')})",
        f"  - user messages: {stats['user_msgs']}, tools: {top_tools}",
    ]
    if stats["written_files"]:
        files = ", ".join(f"`{p}`" for p in stats["written_files"][:10])
        lines.append(f"  - wrote: {files}")
    tail = stats["last_assistant_text"].replace("\n", " ")[-LAST_MSG_TAIL:]
    if tail:
        lines.append(f"  - last note: ...{tail}")
    return "\n".join(lines)


def read_existing_entries(path):
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []
    entries = re.split(r"(?=^\- \*\*Session `)", content, flags=re.M)
    return [e.strip() for e in entries if e.startswith("- **Session `")]


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    session_id = payload.get("session_id") or ""
    transcript = payload.get("transcript_path") or ""
    cwd = payload.get("cwd") or ""
    if not session_id or not transcript or not cwd or not os.path.isfile(transcript):
        sys.exit(0)

    state = state_file_for(session_id)
    now = time.time()
    try:
        if now - os.path.getmtime(state) < THROTTLE_SECONDS:
            sys.exit(0)
    except OSError:
        pass

    entry = summarize(analyze_transcript(transcript), session_id)
    mem = memory_file_for(cwd)
    entries = (read_existing_entries(mem) + [entry])[-MAX_ENTRIES:]

    ensure_parent(mem)
    with open(mem, "w", encoding="utf-8") as f:
        f.write(f"# Project memory: {os.path.basename(cwd)}\n\n")
        f.write(f"Last {len(entries)} sessions (newest last):\n\n")
        f.write("\n\n".join(entries))
        f.write("\n")

    ensure_parent(state)
    with open(state, "w") as f:
        f.write(str(now))


if __name__ == "__main__":
    main()
