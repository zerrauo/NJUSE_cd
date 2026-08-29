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


class LongTaskClient:
    def __init__(self):
        self.calls = 0
        self.request_histories = []

    def complete(self, messages, tools):
        self.calls += 1
        self.request_histories.append(list(messages))
        if self.calls <= 4:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"call_{self.calls}",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": '{"path":"note.txt","content":"progress"}'},
                }],
            }
        return {"role": "assistant", "content": "完成。"}


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

    def test_context_keeps_task_and_complete_tool_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []
            client = LongTaskClient()
            agent = Agent(client, LocalTools(Path(directory)), max_history_messages=4, on_event=events.append)
            result = agent.run("始终保留的任务目标")

            self.assertEqual(result.status, "completed")
            for history in client.request_histories:
                self.assertEqual(history[0]["role"], "system")
                self.assertEqual(history[1], {"role": "user", "content": "始终保留的任务目标"})
                self.assertLessEqual(len(history), 4)
                if len(history) > 2:
                    self.assertEqual([message["role"] for message in history[2:]], ["assistant", "tool"])
            self.assertTrue(any(event.startswith("[上下文] 已裁剪") for event in events))
