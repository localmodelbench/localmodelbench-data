from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMClient:
    """Minimal Ollama /api/chat client (same pattern as run_ollama_paperwork_text_case_once)."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, model: str, messages: list[dict], temperature: float = 0.7,
             max_tokens: int = 400, think: bool = False) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": think,
            "keep_alive": "10m",
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/chat", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = body.get("message") or {}
        content = message.get("content") or ""
        thinking = message.get("thinking") or ""
        if not thinking:
            match = THINK_RE.search(content)
            if match:
                thinking = match.group(0)
                content = THINK_RE.sub("", content).strip()
        return {"content": content.strip(), "thinking": thinking, "raw": body}


@dataclass
class Player:
    seat: int
    name: str
    persona: str
    model: str
    role: str = ""
    alive: bool = True
    private_memory: list[str] = field(default_factory=list)

    @property
    def is_wolf(self) -> bool:
        return self.role == "werwolf"
