"""OpenAI-compatible helpers for Qwen JSON-oriented chat."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from typing import Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

_log = logging.getLogger("paperpilot.llm")


class LLMConfigError(RuntimeError):
    """Missing key or SDK."""


def _require_client() -> OpenAI:
    if OpenAI is None:
        raise LLMConfigError("未安装 openai，请执行：pip install openai")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise LLMConfigError("未配置环境变量 OPENAI_API_KEY")
    base_url = (
        os.getenv(
            "OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip()
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    return OpenAI(api_key=key, base_url=base_url)


def _default_model() -> str:
    return os.getenv("OPENAI_MODEL", "qwen-turbo").strip() or "qwen-turbo"


def _message_content(resp: Any) -> str:
    choices = getattr(resp, "choices", None)
    if not choices:
        raise RuntimeError("模型返回无 choices")
    msg = choices[0].message
    if msg is None:
        raise RuntimeError("模型返回无 message")
    return (msg.content or "").strip()


def chat_text(system: str, user: str) -> str:
    """单次对话，返回助手文本。"""
    client = _require_client()
    model = _default_model()
    try:
        resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        )
    except Exception as e:  # noqa: BLE001
        _log.warning("chat.completions 非流式调用失败: %s", e)
        raise RuntimeError(f"OpenAI 兼容接口调用失败：{e}") from e
    return _message_content(resp)


def chat_text_stream(system: str, user: str) -> Iterator[str]:
    """流式对话，逐块产出助手文本。"""
    client = _require_client()
    model = _default_model()
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            part = getattr(delta, "content", None)
            if not part:
                continue
            if isinstance(part, str):
                yield part
                continue
            if isinstance(part, list):
                for item in part:
                    text = getattr(item, "text", None)
                    if text:
                        yield str(text)
                    elif isinstance(item, dict):
                        maybe = item.get("text")
                        if maybe:
                            yield str(maybe)
    except Exception as e:  # noqa: BLE001
        _log.warning("chat.completions 流式调用失败: %s", e)
        raise RuntimeError(f"OpenAI 兼容流式接口调用失败：{e}") from e


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出中抠出 JSON object。"""
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    m = re.search(r"\{[\s\S]*\}\s*$", s)
    if not m:
        m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(m.group())


def chat_json(system: str, user: str) -> dict[str, Any]:
    """要求模型只输出 JSON；解析为 dict。"""
    raw = chat_text(system, user)
    try:
        return extract_json_object(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"JSON 解析失败：{e}\n原始输出前 500 字：{raw[:500]}") from e
