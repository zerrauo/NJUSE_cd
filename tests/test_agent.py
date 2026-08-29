import tempfile
import unittest
from pathlib import Path

from coding_agent.agent import Agent
from coding_agent.tools import LocalTools


class FakeClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "write_file", "arguments": '{"path":"note.txt","content":"done"}'}}]}
        return {"role": "assistant", "content": "已写入并完成。"}


class AgentTest(unittest.TestCase):
    def test_agent_returns_after_a_tool_round(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            events = []
            agent = Agent(FakeClient(), LocalTools(workspace), on_event=events.append)
            result = agent.run("创建 note 文件")
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.turns, 2)
            self.assertEqual((workspace / "note.txt").read_text(), "done")
            self.assertIn("[第 1/12 轮] 正在请求模型…", events)
            self.assertIn("  [工具] 正在执行 write_file…", events)
            self.assertIn("  [工具] write_file 完成。", events)
            self.assertIn("[模型] 已给出最终答复。", events)
