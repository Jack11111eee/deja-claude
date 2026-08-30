#!/usr/bin/env python3
"""Shared helpers for the cross-session memory hooks.

Memory is stored per-project at:
  ${CLAUDE_PLUGIN_DATA}/memory/<escaped-cwd>.md

CLAUDE_PLUGIN_DATA is injected by claude when running plugin hooks; fall back to
~/.claude/plugins/data/session-finder for direct invocation / testing.
"""

import os
import re

FALLBACK_DATA_DIR = os.path.expanduser("~/.claude/plugins/data/session-finder")


def plugin_data_dir():
    return os.environ.get("CLAUDE_PLUGIN_DATA") or FALLBACK_DATA_DIR


def memory_file_for(cwd):
    safe = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd))
    return os.path.join(plugin_data_dir(), "memory", safe + ".md")


def state_file_for(session_id):
    safe = re.sub(r"[^A-Za-z0-9-]", "", session_id)
    return os.path.join(plugin_data_dir(), "state", safe)


def ensure_parent(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def escape_path(path):
    return path.replace("/", "-")
