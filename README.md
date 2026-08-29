# Nju Coding Agent

一个独立实现的命令行编程智能体。它使用模型原生的 Tool Calling，在指定工作区内读取、写入文件并执行命令；不依赖任何 Agent 框架。

## 当前能力

- OpenAI 兼容的 Chat Completions + Tool Calling 客户端；
- 自实现的 Agent 循环、消息历史裁剪、最大轮数停止条件；
- 本地 `list_files`、`read_file`、`write_file`、`run_command` 工具；
- 路径越界、危险命令、超时和工具异常的基础防护。

## 运行

需要 Python 3.11+。复制 `.env.example` 为 `.env`，填入模型配置（`.env` 不会提交）；再执行：

```bash
set -a; source .env; set +a
python -m coding_agent "修复当前项目的测试失败" --workspace /path/to/project
```

开发阶段也可运行：

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

正式提交用的 `README.txt` 将在功能与演示方案稳定后单独编写，以满足题目 1000 字限制。
