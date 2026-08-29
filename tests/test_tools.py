import json
import tempfile
import unittest
from pathlib import Path

from coding_agent.tools import LocalTools


def unpack(value: str) -> dict:
    return json.loads(value)


class LocalToolsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.tools = LocalTools(Path(self.directory.name))

    def tearDown(self):
        self.directory.cleanup()

    def test_read_write_and_list_stay_in_workspace(self):
        write = unpack(self.tools.execute("write_file", {"path": "src/hello.txt", "content": "你好"}))
        self.assertTrue(write["ok"])
        self.assertEqual(unpack(self.tools.execute("read_file", {"path": "src/hello.txt"}))["content"], "你好")
        self.assertIn("src/", unpack(self.tools.execute("list_files", {"path": "."}))["files"])

    def test_path_escape_and_dangerous_commands_are_rejected(self):
        self.assertFalse(unpack(self.tools.execute("read_file", {"path": "../secret.txt"}))["ok"])
        self.assertFalse(unpack(self.tools.execute("run_command", {"command": "rm -rf /tmp/not-real"}))["ok"])

    def test_command_policy_uses_direct_execution_and_requires_opt_in(self):
        allowed = unpack(self.tools.execute("run_command", {"command": "python3 -c 'print(123)'"}))
        self.assertTrue(allowed["ok"])
        self.assertEqual(allowed["output"].splitlines()[0], "123")
        self.assertFalse(unpack(self.tools.execute("run_command", {"command": "echo hello"}))["ok"])
        self.assertFalse(unpack(self.tools.execute("run_command", {"command": "python3 -c 'print(1)' | cat"}))["ok"])

        unsafe_tools = LocalTools(Path(self.directory.name), allow_unsafe_commands=True)
        self.assertEqual(unpack(unsafe_tools.execute("run_command", {"command": "echo hello"}))["output"].strip(), "hello")

    def test_command_timeout_is_returned_as_a_tool_error(self):
        result = unpack(self.tools.execute("run_command", {"command": "python3 -c 'import time; time.sleep(2)'", "timeout_seconds": 1}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "命令执行超时")

    def test_credentials_are_hidden_from_every_tool(self):
        Path(self.directory.name, ".env").write_text("CODING_AGENT_API_KEY=do-not-leak")
        self.assertNotIn(".env", unpack(self.tools.execute("list_files", {"path": "."}))["files"])
        self.assertFalse(unpack(self.tools.execute("read_file", {"path": ".env"}))["ok"])
        self.assertFalse(unpack(self.tools.execute("write_file", {"path": ".env", "content": "changed"}))["ok"])
        self.assertFalse(unpack(self.tools.execute("run_command", {"command": "cat .env"}))["ok"])
