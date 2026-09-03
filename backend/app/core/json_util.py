"""JSON helpers shared by LLM response parsing."""
from __future__ import annotations

import json
import re
from typing import Any, Dict

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    fenced = _JSON_FENCE.search(raw)
    if fenced:
        raw = fenced.group(1)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(raw[start:end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("LLM did not return a JSON object")
