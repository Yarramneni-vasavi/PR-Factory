from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def parse_json_object(text: str) -> dict[str, Any]:
    content = text.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    parsed = json.loads(content[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def coerce_structured_response(response: Any, schema: type[SchemaT]) -> SchemaT:
    if isinstance(response, schema):
        return response
    if isinstance(response, dict):
        return schema.model_validate(response)
    if hasattr(response, "content"):
        return schema.model_validate(parse_json_object(str(response.content)))
    if isinstance(response, str):
        return schema.model_validate(parse_json_object(response))
    return schema.model_validate(response)


def model_json_schema_text(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), indent=2, sort_keys=True)
