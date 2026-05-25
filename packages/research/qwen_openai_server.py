"""OpenAI-compatible local server for Qwen research experiments."""

from __future__ import annotations

import argparse
import os
import time
import uuid
from functools import lru_cache
from typing import Any, Literal

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

DEFAULT_MODEL_ID = "Qwen/Qwen3-1.7B"

app = FastAPI(title="IL Ideation Qwen OpenAI-compatible Server")


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"] = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = DEFAULT_MODEL_ID
    messages: list[ChatMessage]
    max_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=0.7, ge=0)
    top_p: float | None = Field(default=0.8, ge=0, le=1)
    stream: bool = False


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": _model_ref(),
        "device": _device_name(),
    }


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    model_id = _model_ref()
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest) -> dict[str, Any]:
    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming responses are not implemented.")

    tokenizer, model = _load_model()
    messages = [_tokenizer_message(message) for message in req.messages]
    max_new_tokens = req.max_completion_tokens or req.max_tokens or _default_max_tokens()
    enable_thinking = _enable_thinking(req)
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
    )
    encoded = tokenizer([text], return_tensors="pt").to(model.device)
    generation_kwargs: dict[str, Any] = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.eos_token_id,
    }
    if req.temperature is not None and req.temperature > 0:
        generation_kwargs.update(
            {
                "do_sample": True,
                "temperature": req.temperature,
                "top_p": req.top_p if req.top_p is not None else 1.0,
            }
        )
    else:
        generation_kwargs["do_sample"] = False

    with torch.inference_mode():
        generated = model.generate(**encoded, **generation_kwargs)
    prompt_tokens = int(encoded["input_ids"].shape[-1])
    output_ids = generated[0][prompt_tokens:]
    content = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
    if not enable_thinking:
        content = _strip_thinking_block(content)

    completion_tokens = int(output_ids.shape[-1])
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model or _model_ref(),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@lru_cache(maxsize=1)
def _load_model() -> tuple[Any, Any]:
    model_ref = _model_ref()
    device = _device_name()
    tokenizer = AutoTokenizer.from_pretrained(model_ref, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_ref,
        torch_dtype=_torch_dtype(device),
        trust_remote_code=True,
    )
    model.to(device)
    model.eval()
    return tokenizer, model


def _model_ref() -> str:
    return os.environ.get("QWEN_MODEL_DIR") or os.environ.get("QWEN_MODEL_ID") or DEFAULT_MODEL_ID


def _default_max_tokens() -> int:
    return int(os.environ.get("QWEN_MAX_NEW_TOKENS", "1024"))


def _device_name() -> str:
    requested = os.environ.get("QWEN_DEVICE")
    if requested:
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _torch_dtype(device: str) -> Any:
    requested = os.environ.get("QWEN_TORCH_DTYPE")
    if requested:
        return getattr(torch, requested)
    if device == "mps":
        return torch.float16
    return "auto"


def _enable_thinking(req: ChatCompletionRequest) -> bool:
    extra = getattr(req, "__pydantic_extra__", None) or {}
    raw = extra.get("enable_thinking", os.environ.get("QWEN_ENABLE_THINKING", "false"))
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _tokenizer_message(message: ChatMessage) -> dict[str, str]:
    role = "system" if message.role == "developer" else message.role
    if role == "tool":
        role = "user"
    return {"role": role, "content": message.content}


def _strip_thinking_block(content: str) -> str:
    marker = "</think>"
    if marker in content:
        return content.rsplit(marker, 1)[-1].strip()
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("QWEN_OPENAI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("QWEN_OPENAI_PORT", "8001")))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "packages.research.qwen_openai_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
