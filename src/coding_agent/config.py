from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_environment(cls) -> "Settings":
        api_key = os.environ.get("CODING_AGENT_API_KEY")
        if not api_key:
            raise ValueError("缺少 CODING_AGENT_API_KEY；请通过环境变量提供，不要写入代码。")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("CODING_AGENT_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            model=os.environ.get("CODING_AGENT_MODEL", "gpt-4.1-mini"),
        )

