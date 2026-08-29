"""The explicit agent loop: model decision -> local action -> observation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol

from .tools import LocalTools, TOOL_SCHEMAS

SYSTEM_PROMPT = """你是一个谨慎的编程助手。只在用户指定工作区内工作。先检查相关文件，再做最小修改，并运行合适的验证命令。不要声称未验证的结果。任务完成时简洁汇报修改和验证结果。"""


class CompletionClient(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]: ...


@dataclass
class AgentResult:
    status: str
    message: str
    turns: int


class Agent:
    def __init__(
        self,
        client: CompletionClient,
        tools: LocalTools,
        max_turns: int = 12,
        max_history_messages: int = 60,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.tools = tools
        self.max_turns = max_turns
        if max_history_messages < 3:
            raise ValueError("max_history_messages 至少为 3，以保留系统提示、任务和一条执行记录")
        self.max_history_messages = max_history_messages
        self.on_event = on_event

    def run(self, task: str) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task}]
        for turn in range(1, self.max_turns + 1):
            removed_turns = self._trim_history(messages)
            if removed_turns:
                self._emit(f"[上下文] 已裁剪 {removed_turns} 个较早的完整执行轮次，保留原始任务和最近记录。")
            self._emit(f"[第 {turn}/{self.max_turns} 轮] 正在请求模型…")
            try:
                assistant = self.client.complete(messages, TOOL_SCHEMAS)
            except RuntimeError as exc:
                self._emit("[模型] 请求失败，已停止。")
                return AgentResult("model_error", str(exc), turn)
            messages.append(assistant)
            calls = assistant.get("tool_calls") or []
            if not calls:
                self._emit("[模型] 已给出最终答复。")
                return AgentResult("completed", assistant.get("content") or "任务已结束。", turn)
            for call in calls:
                function = call.get("function", {})
                tool_name = function.get("name", "未知工具")
                self._emit(f"  [工具] 正在执行 {tool_name}…")
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                    if not isinstance(arguments, dict):
                        raise ValueError("工具参数必须是 JSON 对象")
                except (json.JSONDecodeError, ValueError) as exc:
                    result = json.dumps({"ok": False, "error": f"工具参数解析失败: {exc}"}, ensure_ascii=False)
                else:
                    result = self.tools.execute(tool_name, arguments)
                self._emit(self._summarize_tool_result(tool_name, result))
                messages.append({"role": "tool", "tool_call_id": call.get("id", "unknown"), "content": result})
        self._emit("[系统] 达到最大轮数，已停止。")
        return AgentResult("max_turns", f"达到最大执行轮数（{self.max_turns}），已停止以避免无限循环。", self.max_turns)

    def _trim_history(self, messages: list[dict[str, Any]]) -> int:
        """Trim old complete turns while preserving the system prompt and original task.

        A tool-call request and its tool-result messages are one atomic turn. Keeping
        them together prevents an OpenAI-compatible API from receiving orphaned tool
        messages after the history budget is reached.
        """
        if len(messages) <= self.max_history_messages:
            return 0

        fixed_messages = messages[:2]
        turns = self._split_into_turns(messages[2:])
        kept_turns: list[list[dict[str, Any]]] = []
        kept_count = len(fixed_messages)
        for turn in reversed(turns):
            if kept_turns and kept_count + len(turn) > self.max_history_messages:
                break
            kept_turns.insert(0, turn)
            kept_count += len(turn)

        messages[:] = fixed_messages + [message for turn in kept_turns for message in turn]
        return len(turns) - len(kept_turns)

    @staticmethod
    def _split_into_turns(history: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group an assistant response with every following tool observation."""
        turns: list[list[dict[str, Any]]] = []
        current_turn: list[dict[str, Any]] = []
        for message in history:
            if message.get("role") == "assistant":
                if current_turn:
                    turns.append(current_turn)
                current_turn = [message]
            elif current_turn:
                current_turn.append(message)
            else:
                # Defensive fallback for malformed externally supplied history.
                turns.append([message])
        if current_turn:
            turns.append(current_turn)
        return turns

    def _emit(self, event: str) -> None:
        if self.on_event:
            self.on_event(event)

    @staticmethod
    def _summarize_tool_result(tool_name: str, result: str) -> str:
        """Render a small, safe progress message without exposing tool output."""
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return f"  [工具] {tool_name} 返回了无法解析的结果。"
        if data.get("ok"):
            if "exit_code" in data:
                return f"  [工具] {tool_name} 完成（退出码 {data['exit_code']}）。"
            return f"  [工具] {tool_name} 完成。"
        return f"  [工具] {tool_name} 被拒绝或执行失败。"
