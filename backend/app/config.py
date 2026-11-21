import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    keys: tuple[str, ...] = field(repr=False)
    database: Path
    origins: tuple[str, ...]
    simulation: bool
    model: str = "gemini/gemini-3.5-flash-lite"
    default_prompt: str = "You are a helpful assistant. Answer clearly and concisely."

    history_turns: int = 20

    @classmethod
    def load(cls):
        keys = tuple(k.strip() for k in os.getenv("LLM_API_KEYS", "").split(","))
        if not all(keys) or len(set(keys)) != len(keys) or len(keys) < 2:
            keys = ()  # The HTTP service can expose history while awaiting valid configuration.
        database = os.environ.get("DATABASE_URL", "sqlite:///./data/app.db")
        if not database.startswith("sqlite:///") or not database[10:]:
            raise ValueError("DATABASE_URL must identify a SQLite file")
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(
                ","
            )
            if origin.strip()
        )
        history_turns = int(os.getenv("MAX_HISTORY_TURNS", "20"))
        if history_turns < 1:
            raise ValueError("MAX_HISTORY_TURNS must be positive")
        return cls(
            keys,
            Path(database[10:]),
            origins,
            os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true",
            os.getenv("LLM_MODEL", cls.model),
            os.getenv("DEFAULT_SYSTEM_PROMPT", cls.default_prompt),
            history_turns,
        )
