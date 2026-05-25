from __future__ import annotations

import torch
from fastapi.testclient import TestClient

from packages.research import qwen_openai_server


class FakeEncoded(dict):
    def to(self, _device: str) -> "FakeEncoded":
        return self


class FakeTokenizer:
    eos_token_id = 0

    def apply_chat_template(self, messages, **_kwargs):
        assert messages == [{"role": "user", "content": "hello"}]
        return "prompt"

    def __call__(self, _texts, return_tensors: str):
        assert return_tensors == "pt"
        return FakeEncoded({"input_ids": torch.tensor([[1, 2]])})

    def decode(self, _ids, skip_special_tokens: bool):
        assert skip_special_tokens is True
        return "world"


class FakeModel:
    device = "cpu"

    def generate(self, **_kwargs):
        return torch.tensor([[1, 2, 3]])


def test_qwen_server_chat_completion_shape(monkeypatch) -> None:
    qwen_openai_server._load_model.cache_clear()
    monkeypatch.setattr(qwen_openai_server, "_load_model", lambda: (FakeTokenizer(), FakeModel()))
    client = TestClient(qwen_openai_server.app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "Qwen/Qwen3-1.7B",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
            "temperature": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["choices"][0]["message"]["content"] == "world"
    assert payload["usage"]["prompt_tokens"] == 2
    assert payload["usage"]["completion_tokens"] == 1
