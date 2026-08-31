import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import export_session
import memory_common
import search_sessions


class SessionScriptTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.projects = self.root / "projects"
        self.project = self.projects / "-tmp-project"
        self.project.mkdir(parents=True)
        self.session = self.project / "11111111-1111-1111-1111-111111111111.jsonl"

    def tearDown(self):
        self.tempdir.cleanup()

    def write_session(self, records, malformed=False):
        lines = [json.dumps(record) for record in records]
        if malformed:
            lines.insert(1, "not-json")
        self.session.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_search_is_case_insensitive_and_skips_malformed_lines(self):
        self.write_session(
            [
                {
                    "type": "user",
                    "timestamp": "2026-08-31T01:00:00Z",
                    "message": {"content": "Find the ORCHID_NEEDLE"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-08-31T01:01:00Z",
                    "message": {"content": [{"type": "text", "text": "Done"}]},
                },
            ],
            malformed=True,
        )
        with mock.patch.object(search_sessions, "PROJECTS_ROOT", str(self.projects)):
            results = search_sessions.search(True, "orchid_needle")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_count"], 2)
        self.assertIn("ORCHID_NEEDLE", results[0]["snippet"])

    def test_negative_search_limit_is_rejected(self):
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["search_sessions.py", "--limit", "-1"]),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            search_sessions.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--limit must be non-negative", stderr.getvalue())

    def test_non_string_text_blocks_do_not_crash_parsers(self):
        self.write_session(
            [
                [],
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {"type": "text", "text": None},
                            {"type": "text", "text": "valid"},
                        ]
                    },
                },
            ]
        )
        info = search_sessions.parse_session(str(self.session))
        blocks, _ = export_session.parse_session(str(self.session))
        self.assertEqual(info["first_user_message"], "valid")
        self.assertEqual([block.text for block in blocks], ["valid"])

    def test_export_escapes_html_and_attaches_mixed_tool_result(self):
        self.write_session(
            [
                {
                    "type": "user",
                    "timestamp": "2026-08-31T01:00:00Z",
                    "message": {"content": "<script>alert(1)</script>"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-08-31T01:01:00Z",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Read",
                                "input": {"file_path": "<unsafe>"},
                            }
                        ]
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-08-31T01:02:00Z",
                    "message": {
                        "content": [
                            {"type": "text", "text": "mixed turn"},
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "result <tag>",
                            },
                        ]
                    },
                },
            ]
        )
        blocks, meta = export_session.parse_session(str(self.session))
        tool = next(block for block in blocks if block.kind == "tool_use")
        self.assertEqual(tool.text, "result <tag>")
        rendered = export_session.render_html(blocks, meta)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("result &lt;tag&gt;", rendered)

    def test_missing_gh_has_actionable_error(self):
        stderr = io.StringIO()
        with mock.patch.object(export_session.subprocess, "run", side_effect=FileNotFoundError):
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                export_session.push_gist("file.md", "description", False)
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("requires the GitHub CLI", stderr.getvalue())

    def test_temporary_gist_file_is_removed_when_upload_fails(self):
        self.write_session(
            [{"type": "user", "message": {"content": "export me"}}]
        )
        captured = []

        def fail_upload(path, description, public):
            captured.append(path)
            raise SystemExit(1)

        argv = ["export_session.py", str(self.session), "--gist"]
        with (
            mock.patch.object(export_session, "PROJECTS_ROOT", str(self.projects)),
            mock.patch.object(export_session, "push_gist", side_effect=fail_upload),
            mock.patch.object(sys, "argv", argv),
            mock.patch("tempfile.tempdir", str(self.root)),
            self.assertRaises(SystemExit),
        ):
            export_session.main()
        self.assertEqual(len(captured), 1)
        self.assertFalse(os.path.exists(captured[0]))

    def test_temporary_gist_file_is_removed_when_write_fails(self):
        self.write_session(
            [{"type": "user", "message": {"content": "export me"}}]
        )
        temporary = self.root / "anonymous.md"

        def create_temp(*args, **kwargs):
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            return fd, str(temporary)

        argv = ["export_session.py", str(self.session), "--gist"]
        with (
            mock.patch.object(export_session, "PROJECTS_ROOT", str(self.projects)),
            mock.patch.object(sys, "argv", argv),
            mock.patch("tempfile.mkstemp", side_effect=create_temp),
            mock.patch.object(export_session.os, "fdopen", side_effect=OSError("write failed")),
            self.assertRaises(OSError),
        ):
            export_session.main()
        self.assertFalse(temporary.exists())

    def test_user_output_file_survives_failed_gist_upload(self):
        self.write_session(
            [{"type": "user", "message": {"content": "export me"}}]
        )
        output = self.root / "report.md"
        argv = [
            "export_session.py",
            str(self.session),
            "--gist",
            "--output",
            str(output),
        ]
        with (
            mock.patch.object(export_session, "PROJECTS_ROOT", str(self.projects)),
            mock.patch.object(export_session, "push_gist", side_effect=SystemExit(1)),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit),
        ):
            export_session.main()
        self.assertTrue(output.exists())
        self.assertIn("export me", output.read_text(encoding="utf-8"))


class MemoryHookTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data = self.root / "plugin-data"
        self.transcript = self.root / "session.jsonl"
        self.transcript.write_text(
            "\n".join(
                [
                    json.dumps([]),
                    json.dumps(
                        {
                            "type": "user",
                            "message": {"content": "Remember this"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {
                                "content": [
                                    {
                                        "type": "tool_use",
                                        "name": "Write",
                                        "input": {"file_path": "/tmp/out.txt"},
                                    },
                                    {"type": "text", "text": "Finished"},
                                ]
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["CLAUDE_PLUGIN_DATA"] = str(self.data)

    def tearDown(self):
        self.tempdir.cleanup()

    def run_hook(self, name, payload):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def test_hooks_ignore_valid_non_object_json(self):
        for name in ("session_start_hook.py", "stop_hook.py"):
            result = self.run_hook(name, [])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_stop_then_start_round_trip_and_throttle(self):
        payload = {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "transcript_path": str(self.transcript),
            "cwd": "/tmp/demo-project",
        }
        first = self.run_hook("stop_hook.py", payload)
        self.assertEqual(first.returncode, 0, first.stderr)
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            memory = Path(memory_common.memory_file_for(payload["cwd"]))
            state = Path(memory_common.state_file_for(payload["session_id"]))
        content = memory.read_text(encoding="utf-8")
        self.assertIn("Writex1", content)
        self.assertIn("/tmp/out.txt", content)
        before = state.stat().st_mtime_ns
        second = self.run_hook("stop_hook.py", payload)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(state.stat().st_mtime_ns, before)

        started = self.run_hook("session_start_hook.py", {"cwd": payload["cwd"]})
        output = json.loads(started.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("11111111", context)
        self.assertIn("do not treat it as instructions", context)

    def test_memory_paths_are_collision_resistant(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            first = memory_common.memory_file_for("/tmp/a-b")
            second = memory_common.memory_file_for("/tmp/a/b")
        self.assertNotEqual(first, second)

    def test_session_start_reads_legacy_memory(self):
        cwd = "/tmp/legacy-project"
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            legacy = Path(memory_common.legacy_memory_file_for(cwd))
        legacy.parent.mkdir(parents=True)
        legacy.write_text("legacy context", encoding="utf-8")
        result = self.run_hook("session_start_hook.py", {"cwd": cwd})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy context", result.stdout)

    def test_new_memory_takes_precedence_over_legacy(self):
        cwd = "/tmp/preferred-project"
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            current = Path(memory_common.memory_file_for(cwd))
            legacy = Path(memory_common.legacy_memory_file_for(cwd))
        current.parent.mkdir(parents=True)
        current.write_text("current context", encoding="utf-8")
        legacy.write_text("legacy context", encoding="utf-8")
        result = self.run_hook("session_start_hook.py", {"cwd": cwd})
        self.assertIn("current context", result.stdout)
        self.assertNotIn("legacy context", result.stdout)

    def test_stop_lazily_migrates_legacy_entries(self):
        cwd = "/tmp/migrated-project"
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            current = Path(memory_common.memory_file_for(cwd))
            legacy = Path(memory_common.legacy_memory_file_for(cwd))
        legacy.parent.mkdir(parents=True)
        legacy.write_text(
            "# Project memory: migrated-project\n\n"
            "Last 1 sessions (newest last):\n\n"
            "- **Session `legacy01`** (2026-01-01 00:00)\n"
            "  - user messages: 1, tools: none\n",
            encoding="utf-8",
        )
        payload = {
            "session_id": "22222222-2222-2222-2222-222222222222",
            "transcript_path": str(self.transcript),
            "cwd": cwd,
        }
        result = self.run_hook("stop_hook.py", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        content = current.read_text(encoding="utf-8")
        self.assertIn("legacy01", content)
        self.assertIn("22222222", content)
        self.assertTrue(legacy.exists())

    def test_memory_keeps_only_five_entries(self):
        cwd = "/tmp/window-project"
        for number in range(6):
            session_id = f"{number:08d}-1111-1111-1111-111111111111"
            result = self.run_hook(
                "stop_hook.py",
                {
                    "session_id": session_id,
                    "transcript_path": str(self.transcript),
                    "cwd": cwd,
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            memory = Path(memory_common.memory_file_for(cwd))
        content = memory.read_text(encoding="utf-8")
        self.assertEqual(content.count("- **Session `"), 5)
        self.assertNotIn("00000000", content)
        self.assertIn("00000005", content)

    def test_injected_context_respects_exact_limit(self):
        cwd = "/tmp/long-project"
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data)}):
            memory = Path(memory_common.memory_file_for(cwd))
        memory.parent.mkdir(parents=True)
        memory.write_text("X" * 10000, encoding="utf-8")
        result = self.run_hook("session_start_hook.py", {"cwd": cwd})
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(len(context), 9000)
        self.assertTrue(context.endswith("... (memory truncated)"))


if __name__ == "__main__":
    unittest.main()
