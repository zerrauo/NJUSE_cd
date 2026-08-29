"""Local tools and their workspace/security boundaries."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "list_files", "description": "列出工作区中匹配的文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "相对工作区的目录，默认 ."}}, "required": []}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取工作区内的 UTF-8 文本文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "相对工作区的文件路径"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "创建或完全覆盖工作区内的 UTF-8 文本文件。", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "在工作区内运行测试或构建命令并返回输出。默认仅允许常见开发命令，危险命令会被拒绝。", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60}}, "required": ["command"]}}},
]


class LocalTools:
    """All paths are resolved beneath one user-selected workspace."""

    MAX_FILE_BYTES = 100_000
    BLOCKED_COMMANDS = {"sudo", "shutdown", "reboot", "mkfs", "dd", "git push"}
    SAFE_EXECUTABLES = {"python", "python3", "pytest", "npm", "go", "cargo", "mvn", "gradle", "./gradlew", "./mvnw"}
    SHELL_OPERATORS = {"|", "||", "&&", ";", ">", ">>", "<", "<<"}
    SENSITIVE_FILE_NAMES = {".env", ".ssh", "id_rsa", "id_ed25519", "credentials"}
    SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

    def __init__(self, workspace: Path, allow_unsafe_commands: bool = False) -> None:
        self.workspace = workspace.resolve()
        self.allow_unsafe_commands = allow_unsafe_commands
        if not self.workspace.is_dir():
            raise ValueError(f"工作区不存在或不是目录: {workspace}")

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            handler = getattr(self, f"_{name}")
        except AttributeError:
            return self._error(f"未知工具: {name}")
        try:
            return handler(arguments)
        except subprocess.TimeoutExpired:
            return self._error("命令执行超时")
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            return self._error(str(exc))

    def _resolve(self, raw_path: str) -> Path:
        candidate = (self.workspace / raw_path).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise ValueError("拒绝访问工作区以外的路径")
        self._assert_not_sensitive(candidate)
        return candidate

    def _assert_not_sensitive(self, candidate: Path) -> None:
        """Keep credentials outside the model's observable file system."""
        if candidate == self.workspace:
            return
        for part in candidate.relative_to(self.workspace).parts:
            lowered = part.lower()
            if lowered in self.SENSITIVE_FILE_NAMES or any(lowered.endswith(suffix) for suffix in self.SENSITIVE_SUFFIXES):
                raise ValueError("拒绝访问可能包含凭据的文件或目录")

    @classmethod
    def _is_sensitive(cls, candidate: Path, workspace: Path) -> bool:
        if candidate == workspace:
            return False
        for part in candidate.relative_to(workspace).parts:
            lowered = part.lower()
            if lowered in cls.SENSITIVE_FILE_NAMES or any(lowered.endswith(suffix) for suffix in cls.SENSITIVE_SUFFIXES):
                return True
        return False

    def _list_files(self, args: dict[str, Any]) -> str:
        target = self._resolve(args.get("path", "."))
        if not target.is_dir():
            raise ValueError("指定路径不是目录")
        entries = []
        for path in sorted(target.iterdir()):
            if self._is_sensitive(path, self.workspace):
                continue
            relative = path.relative_to(self.workspace)
            entries.append(f"{relative}{'/' if path.is_dir() else ''}")
            if len(entries) >= 200:
                entries.append("... 已截断（最多 200 项）")
                break
        return self._ok({"files": entries})

    def _read_file(self, args: dict[str, Any]) -> str:
        target = self._resolve(self._required_string(args, "path"))
        if not target.is_file():
            raise ValueError("文件不存在或不是普通文件")
        if target.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError(f"文件超过 {self.MAX_FILE_BYTES} 字节，请改为读取更小的文件")
        return self._ok({"path": str(target.relative_to(self.workspace)), "content": target.read_text(encoding="utf-8")})

    def _write_file(self, args: dict[str, Any]) -> str:
        target = self._resolve(self._required_string(args, "path"))
        content = args.get("content")
        if not isinstance(content, str):
            raise ValueError("参数 content 必须是字符串")
        if len(content.encode("utf-8")) > self.MAX_FILE_BYTES:
            raise ValueError(f"单次写入不得超过 {self.MAX_FILE_BYTES} 字节")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self._ok({"path": str(target.relative_to(self.workspace)), "bytes_written": len(content.encode("utf-8"))})

    def _run_command(self, args: dict[str, Any]) -> str:
        command = self._required_string(args, "command")
        normalized = command.lower().strip()
        secret_markers = (".env", ".ssh", "id_rsa", "id_ed25519", "credentials", ".pem", ".key", "printenv", " env", "echo $")
        if any(blocked in normalized for blocked in self.BLOCKED_COMMANDS) or "rm -rf" in normalized or any(marker in normalized for marker in secret_markers):
            raise ValueError("命令被安全策略拒绝")
        command_parts = shlex.split(command)
        if not command_parts:
            raise ValueError("命令不能为空")
        if any(part in self.SHELL_OPERATORS for part in command_parts):
            raise ValueError("默认策略不支持管道、重定向等 shell 语法")
        if not self.allow_unsafe_commands and command_parts[0] not in self.SAFE_EXECUTABLES:
            raise ValueError(f"默认策略只允许测试或构建命令；如确有需要，请使用 --allow-unsafe-commands：{command_parts[0]}")
        timeout = args.get("timeout_seconds", 30)
        if not isinstance(timeout, int) or not 1 <= timeout <= 60:
            raise ValueError("timeout_seconds 必须是 1 到 60 的整数")
        completed = subprocess.run(
            command_parts,
            shell=False,
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=timeout,
            # Do not pass API keys or other parent-process variables to tools.
            env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
        )
        output = (completed.stdout + completed.stderr)[-12_000:]
        return self._ok({"exit_code": completed.returncode, "output": output, "truncated": len(completed.stdout + completed.stderr) > 12_000})

    @staticmethod
    def _required_string(args: dict[str, Any], key: str) -> str:
        value = args.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"参数 {key} 必须是非空字符串")
        return value

    @staticmethod
    def _ok(value: dict[str, Any]) -> str:
        return json.dumps({"ok": True, **value}, ensure_ascii=False)

    @staticmethod
    def _error(message: str) -> str:
        return json.dumps({"ok": False, "error": message}, ensure_ascii=False)
