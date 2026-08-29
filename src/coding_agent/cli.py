from __future__ import annotations

import argparse
from pathlib import Path

from .agent import Agent
from .client import ModelClient
from .config import Settings
from .tools import LocalTools


def main() -> None:
    parser = argparse.ArgumentParser(description="独立实现的命令行编程智能体")
    parser.add_argument("task", help="要完成的编程任务")
    parser.add_argument("--workspace", default=".", help="允许 Agent 操作的工作区，默认当前目录")
    parser.add_argument("--max-turns", type=int, default=12, help="最大模型调用轮数，默认 12")
    parser.add_argument("--quiet", action="store_true", help="不显示中间进度日志")
    args = parser.parse_args()
    if args.max_turns < 1:
        parser.error("--max-turns 必须大于 0")

    on_event = None if args.quiet else lambda event: print(event, flush=True)
    agent = Agent(
        ModelClient(Settings.from_environment()),
        LocalTools(Path(args.workspace)),
        max_turns=args.max_turns,
        on_event=on_event,
    )
    result = agent.run(args.task)
    print(f"[{result.status}] {result.message}\n(模型调用轮数: {result.turns})")
