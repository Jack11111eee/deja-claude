#!/usr/bin/env python3
"""Search Claude Code session history and print resume commands.

Sessions live in ~/.claude/projects/<escaped-cwd>/<sessionId>.jsonl,
where escaping replaces "/" with "-". Only records with
type == "user" | "assistant" carry message text.
"""

import argparse
import json
import os
import sys

PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")
SUMMARY_LEN = 40
SNIPPET_CTX = 50


NOISE_PREFIXES = (
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-",
    "<bash-",
    "<ide-",
    "<user-prompt-submit-hook>",
    "[Request interrupted by user",
)


def escape_path(path):
    return path.replace("/", "-")


def is_noise(text):
    t = text.strip()
    if not t:
        return True
    return any(t.splitlines()[0].startswith(p) for p in NOISE_PREFIXES)


def extract_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def parse_session(path, query=None):
    """Return session metadata, or None if unreadable / no valid messages."""
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    first_user_message = None
    last_timestamp = None
    message_count = 0
    snippet = None
    query_lower = query.lower() if query else None
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") not in ("user", "assistant"):
                continue
            text = extract_text(record.get("message") or {})
            if record.get("timestamp"):
                last_timestamp = record["timestamp"]
            if (
                record["type"] == "user"
                and first_user_message is None
                and text
                and not is_noise(text)
            ):
                first_user_message = text
            message_count += 1
            if query_lower and snippet is None and not is_noise(text):
                idx = text.lower().find(query_lower)
                if idx != -1:
                    start = max(0, idx - SNIPPET_CTX)
                    snippet = text[start : idx + len(query) + SNIPPET_CTX]
                    snippet = snippet.replace("\n", " ").strip()
    if message_count == 0:
        return None
    if query_lower and snippet is None:
        return None
    session_id = os.path.splitext(os.path.basename(path))[0]
    return {
        "session_id": session_id,
        "first_user_message": (first_user_message or "").strip(),
        "last_timestamp": last_timestamp or "",
        "message_count": message_count,
        "snippet": snippet,
    }


def iter_project_dirs(all_projects):
    if not os.path.isdir(PROJECTS_ROOT):
        print(f"error: {PROJECTS_ROOT} not found", file=sys.stderr)
        sys.exit(1)
    if all_projects:
        for name in sorted(os.listdir(PROJECTS_ROOT)):
            path = os.path.join(PROJECTS_ROOT, name)
            if os.path.isdir(path):
                yield path
    else:
        path = os.path.join(PROJECTS_ROOT, escape_path(os.path.abspath(os.getcwd())))
        if os.path.isdir(path):
            yield path


def search(all_projects, query):
    results = []
    for project_dir in iter_project_dirs(all_projects):
        project_name = os.path.basename(project_dir)
        try:
            files = os.listdir(project_dir)
        except OSError:
            continue
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            info = parse_session(os.path.join(project_dir, name), query)
            if info:
                info["project"] = project_name
                results.append(info)
    results.sort(key=lambda r: r["last_timestamp"], reverse=True)
    return results


def print_text(results):
    for r in results:
        summary = r["first_user_message"].replace("\n", " ")[:SUMMARY_LEN]
        print(
            f"{r['project']} | {r['last_timestamp']} | {summary} "
            f"| claude --resume {r['session_id']}"
        )
        if r["snippet"]:
            print(f"    ...{r['snippet']}...")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default=None, help="keyword to search for")
    parser.add_argument("--all", action="store_true", help="search all projects")
    parser.add_argument("--limit", type=int, default=20, help="max results (default 20)")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()

    results = search(args.all, args.query)[: args.limit]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_text(results)


if __name__ == "__main__":
    main()
