"""DashScope (Qwen) helpers — JSON-oriented chat."""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    from http import HTTPStatus

    import dashscope
    from dashscope import Generation
except ImportError:
    dashscope = None
    Generation = None
    HTTPStatus = None


class LLMConfigError(RuntimeError):
    """Missing key or SDK."""


def _require_client() -> None:
    if Generation is None or dashscope is None:
        raise LLMConfigError("未安装 dashscope，请执行：pip install dashscope")
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise LLMConfigError("未配置环境变量 DASHSCOPE_API_KEY")
    dashscope.api_key = key


def _default_model() -> str:
    return os.getenv("QWEN_MODEL", "qwen-turbo").strip() or "qwen-turbo"


def _message_content(resp: Any) -> str:
    out = resp.output
    if isinstance(out, dict):
        choices = out.get("choices") or []
        if not choices:
            raise RuntimeError("模型返回无 choices")
        msg = choices[0].get("message") or {}
        return (msg.get("content") or "").strip()
    choices = getattr(out, "choices", None)
    if not choices:
        raise RuntimeError("模型返回无 choices")
    msg = getattr(choices[0], "message", None)
    if msg is None:
        raise RuntimeError("模型返回无 message")
    return (getattr(msg, "content", None) or "").strip()


def chat_text(system: str, user: str) -> str:
    """单次对话，返回助手文本。"""
    _require_client()
    model = _default_model()
    resp = Generation.call(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        result_format="message",
    )
    code = getattr(resp, "status_code", None)
    if code is not None and HTTPStatus is not None and code != HTTPStatus.OK:
        msg = getattr(resp, "message", None) or str(resp)
        raise RuntimeError(f"DashScope 错误 ({code}): {msg}")
    return _message_content(resp)


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
