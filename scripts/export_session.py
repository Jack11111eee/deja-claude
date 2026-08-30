#!/usr/bin/env python3
"""Export a Claude Code session (jsonl) to markdown / html, optionally push to gist.

Sessions live in ~/.claude/projects/<escaped-cwd>/<sessionId>.jsonl.
Only type == user | assistant records carry conversation content.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys

PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")
TOOL_RESULT_MAX = 1024
SUMMARY_LEN = 80

NOISE_PREFIXES = (
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<ide-selection>",
    "<ide-opened-files>",
    "<user-prompt-submit-hook>",
)


def escape_path(path):
    return path.replace("/", "-")


def is_noise(text):
    t = text.strip()
    return any(t.startswith(p) for p in NOISE_PREFIXES)


def truncate(text, limit=TOOL_RESULT_MAX):
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} chars truncated)"


def find_session_file(session_id, all_projects):
    """Locate the jsonl for a session id. Returns path or None."""
    if session_id.endswith(".jsonl") and os.path.isfile(session_id):
        return session_id
    session_id = session_id.removesuffix(".jsonl")
    if all_projects:
        candidates = []
        for name in os.listdir(PROJECTS_ROOT):
            p = os.path.join(PROJECTS_ROOT, name, session_id + ".jsonl")
            if os.path.isfile(p):
                candidates.append(p)
        return candidates[0] if candidates else None
    p = os.path.join(
        PROJECTS_ROOT, escape_path(os.path.abspath(os.getcwd())), session_id + ".jsonl"
    )
    return p if os.path.isfile(p) else None


def latest_session_file():
    project_dir = os.path.join(
        PROJECTS_ROOT, escape_path(os.path.abspath(os.getcwd()))
    )
    if not os.path.isdir(project_dir):
        return None
    files = [
        os.path.join(project_dir, f)
        for f in os.listdir(project_dir)
        if f.endswith(".jsonl")
    ]
    return max(files, key=os.path.getmtime) if files else None


class Block:
    """One conversation block: (kind, payload). kind in:
    user / assistant / tool_use / tool_result / thinking"""

    __slots__ = ("kind", "text", "name", "tool_input")

    def __init__(self, kind, text="", name="", tool_input=None):
        self.kind = kind
        self.text = text
        self.name = name
        self.tool_input = tool_input


def parse_session(path):
    """Parse jsonl into a list of Blocks. Returns (blocks, meta)."""
    blocks = []
    tool_use_index = {}  # tool_use_id -> Block (the tool_use block, for result attach)
    first_user_message = None
    first_ts = None
    last_ts = None
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
            ts = rec.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
            message = rec.get("message") or {}
            content = message.get("content")

            # plain-string content (old/simple format)
            if isinstance(content, str):
                if rtype == "user" and not is_noise(content):
                    if first_user_message is None:
                        first_user_message = content
                    blocks.append(Block("user", text=content))
                elif rtype == "assistant":
                    blocks.append(Block("assistant", text=content))
                continue

            if not isinstance(content, list):
                continue

            # "user" record whose first block is tool_result -> result carrier, not a turn
            if (
                rtype == "user"
                and content
                and isinstance(content[0], dict)
                and content[0].get("type") == "tool_result"
            ):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        result_text = extract_result_text(item.get("content"))
                        tu = tool_use_index.get(item.get("tool_use_id"))
                        if tu is not None:
                            tu.text = truncate(result_text)  # attach result to tool_use
                        else:
                            blocks.append(
                                Block("tool_result", text=truncate(result_text))
                            )
                continue

            for item in content:
                if not isinstance(item, dict):
                    continue
                btype = item.get("type")
                if btype == "text":
                    text = item.get("text", "")
                    if rtype == "user":
                        if is_noise(text):
                            continue
                        if first_user_message is None:
                            first_user_message = text
                        blocks.append(Block("user", text=text))
                    else:
                        blocks.append(Block("assistant", text=text))
                elif btype == "tool_use":
                    blk = Block(
                        "tool_use",
                        name=item.get("name", "?"),
                        tool_input=item.get("input"),
                    )
                    tool_use_index[item.get("id")] = blk
                    blocks.append(blk)
                elif btype == "thinking":
                    blocks.append(Block("thinking", text=item.get("thinking", "")))
    meta = {
        "session_id": os.path.splitext(os.path.basename(path))[0],
        "first_user_message": (first_user_message or "").strip(),
        "first_ts": first_ts or "",
        "last_ts": last_ts or "",
        "project": os.path.basename(os.path.dirname(path)),
    }
    return blocks, meta


def extract_result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    return ""


def render_markdown(blocks, meta):
    out = []
    title = meta["first_user_message"].replace("\n", " ")[:SUMMARY_LEN] or meta[
        "session_id"
    ]
    out.append(f"# Claude Code Session: {title}")
    out.append("")
    out.append(f"- **Project**: `{meta['project']}`")
    out.append(f"- **Session**: `{meta['session_id']}`")
    out.append(f"- **Time**: {meta['first_ts']} → {meta['last_ts']}")
    out.append(f"- **Resume**: `claude --resume {meta['session_id']}`")
    out.append("")
    out.append("---")
    out.append("")
    for b in blocks:
        if b.kind == "user":
            out.append("## 🧑 User")
            out.append("")
            out.append(b.text)
        elif b.kind == "assistant":
            out.append("## 🤖 Assistant")
            out.append("")
            out.append(b.text)
        elif b.kind == "tool_use":
            out.append(f"> 🔧 **Tool**: `{b.name}`")
            if b.tool_input:
                out.append(">")
                for line in truncate(
                    json.dumps(b.tool_input, ensure_ascii=False, indent=2)
                ).splitlines():
                    out.append(f"> {line}")
            if b.text:  # attached tool_result
                out.append(">")
                out.append("> **Result**:")
                for line in b.text.splitlines():
                    out.append(f"> {line}")
        elif b.kind == "tool_result":
            out.append("> 📥 **Tool result**:")
            for line in b.text.splitlines():
                out.append(f"> {line}")
        elif b.kind == "thinking":
            out.append("<details><summary>💭 thinking</summary>")
            out.append("")
            out.append(b.text)
            out.append("")
            out.append("</details>")
        out.append("")
    return "\n".join(out)


def render_html(blocks, meta):
    # minimal but valid HTML; markdown body rendered structurally
    body = []
    title = html.escape(
        meta["first_user_message"].replace("\n", " ")[:SUMMARY_LEN]
        or meta["session_id"]
    )
    body.append(f"<h1>Claude Code Session: {title}</h1>")
    body.append(
        f"<ul>"
        f"<li><b>Project</b>: <code>{html.escape(meta['project'])}</code></li>"
        f"<li><b>Session</b>: <code>{meta['session_id']}</code></li>"
        f"<li><b>Time</b>: {html.escape(meta['first_ts'])} → {html.escape(meta['last_ts'])}</li>"
        f"<li><b>Resume</b>: <code>claude --resume {meta['session_id']}</code></li>"
        f"</ul><hr>"
    )
    for b in blocks:
        if b.kind in ("user", "assistant"):
            who = "🧑 User" if b.kind == "user" else "🤖 Assistant"
            body.append(
                f"<h2>{who}</h2><pre>{html.escape(b.text)}</pre>"
            )
        elif b.kind == "tool_use":
            body.append(
                f"<blockquote>🔧 <b>Tool</b>: <code>{html.escape(b.name)}</code>"
            )
            if b.tool_input:
                body.append(
                    f"<pre>{html.escape(truncate(json.dumps(b.tool_input, ensure_ascii=False, indent=2)))}</pre>"
                )
            if b.text:
                body.append(f"<b>Result</b>:<pre>{html.escape(b.text)}</pre>")
            body.append("</blockquote>")
        elif b.kind == "tool_result":
            body.append(
                f"<blockquote>📥 <b>Tool result</b>:<pre>{html.escape(b.text)}</pre></blockquote>"
            )
        elif b.kind == "thinking":
            body.append(
                f"<details><summary>💭 thinking</summary><pre>{html.escape(b.text)}</pre></details>"
            )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Claude Session {meta['session_id']}</title>"
        "<style>body{max-width:60em;margin:2em auto;font-family:system-ui;padding:0 1em}"
        "pre{white-space:pre-wrap;word-wrap:break-word;background:#f6f8fa;padding:.5em;border-radius:4px}"
        "blockquote{border-left:3px solid #ccc;margin:0;padding-left:1em;color:#555}"
        "</style></head><body>\n" + "\n".join(body) + "\n</body></html>"
    )


def push_gist(path, description, public):
    cmd = ["gh", "gist", "create", path, "-d", description]
    if public:
        cmd.append("--public")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"error: gh gist create failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    # gh prints the gist URL on stdout
    url = result.stdout.strip().splitlines()[-1]
    return url


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "session",
        nargs="?",
        default="--latest",
        help="session id or .jsonl path (omit to use newest session in current project)",
    )
    ap.add_argument("--all", action="store_true", help="search session id across all projects")
    ap.add_argument("--format", choices=["md", "html"], default="md")
    ap.add_argument("--output", "-o", help="write to file instead of stdout")
    ap.add_argument("--gist", action="store_true", help="push result to a GitHub gist (secret by default)")
    ap.add_argument("--public", action="store_true", help="with --gist: make the gist PUBLIC (visible to anyone)")
    args = ap.parse_args()

    if not os.path.isdir(PROJECTS_ROOT):
        print(f"error: {PROJECTS_ROOT} not found", file=sys.stderr)
        sys.exit(1)

    if args.session == "--latest":
        path = latest_session_file()
        if not path:
            print("error: no session found in current project", file=sys.stderr)
            sys.exit(1)
    else:
        path = find_session_file(args.session, args.all)
        if not path:
            print(f"error: session '{args.session}' not found", file=sys.stderr)
            sys.exit(1)

    blocks, meta = parse_session(path)
    if not blocks:
        print("error: session has no conversation content", file=sys.stderr)
        sys.exit(1)

    if args.format == "md":
        rendered, ext = render_markdown(blocks, meta), "md"
    else:
        rendered, ext = render_html(blocks, meta), "html"

    if args.gist:
        # gist needs a real file on disk
        if args.output:
            out_file = args.output
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(rendered)
        else:
            import tempfile

            fd, out_file = tempfile.mkstemp(suffix=f"-{meta['session_id']}.{ext}")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(rendered)
        if args.public:
            print(
                "⚠️  creating a PUBLIC gist — anyone with the link can see the full "
                "conversation including code. Ctrl-C within 3s to abort.",
                file=sys.stderr,
            )
            import time

            time.sleep(3)
        url = push_gist(out_file, f"Claude Code session {meta['session_id']}", args.public)
        print(url)
        if not args.output:
            os.unlink(out_file)
    elif args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(args.output)
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
