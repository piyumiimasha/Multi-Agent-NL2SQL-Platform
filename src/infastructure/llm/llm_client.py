from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from groq import Groq


def _load_env_file(env_path: str | Path = ".env") -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ if not already set."""
    path = Path(env_path)
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int


class GroqLLMClient:
    """Thin wrapper around the Groq API for NL2SQL generation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        env_path: str | Path = ".env",
    ) -> None:
        if api_key is None:
            _load_env_file(env_path)
            api_key = os.environ.get("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError(
                "Missing Groq API key. Set GROQ_API_KEY in your .env file."
            )

        self._client = Groq(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def complete(self, *, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = (response.choices[0].message.content or "").strip()
        text = _strip_code_fences(text)

        usage = response.usage
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )


def _strip_code_fences(text: str) -> str:
    """Groq models often wrap SQL in ```sql ... ``` even when told not to. Strip it."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop first line (``` or ```sql) and last line (```) if present
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped