"""Parse AI model responses into structured practical-task generation results."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.ai.practical_task_generation_interfaces import PracticalTaskGenerationResult
from app.content.practical_task import PracticalTask


class PracticalTaskResponseParser:
    """Convert raw AI text responses into :class:`PracticalTaskGenerationResult`."""

    def parse_practical_task(self, response: str) -> PracticalTaskGenerationResult:
        """Parse model output into a structured practical task."""
        if response == "":
            raise ValueError("Response must not be empty.")

        data = json.loads(response)
        if not isinstance(data, dict):
            raise ValueError("Response root must be a JSON object.")

        task = _parse_structured_practical_task(data)
        return PracticalTaskGenerationResult(task=task)


def _parse_structured_practical_task(data: dict[str, Any]) -> PracticalTask:
    if "structured_practical_task" not in data:
        raise ValueError("Field 'structured_practical_task' is missing.")

    value = data["structured_practical_task"]
    if value is None:
        raise ValueError("Field 'structured_practical_task' must not be null.")
    if not isinstance(value, dict):
        raise ValueError("Field 'structured_practical_task' must be a JSON object.")

    for field_name in ("title", "description", "expected_result"):
        if field_name not in value:
            raise ValueError(f"Field 'structured_practical_task.{field_name}' is missing.")
        field_value = value[field_name]
        if not isinstance(field_value, str):
            raise ValueError(
                f"Field 'structured_practical_task.{field_name}' must be a string."
            )
        if not field_value.strip():
            raise ValueError(
                f"Field 'structured_practical_task.{field_name}' must not be empty."
            )

    estimated_minutes: Optional[int] = None
    if "estimated_minutes" in value:
        raw_minutes = value["estimated_minutes"]
        if raw_minutes is None:
            estimated_minutes = None
        elif isinstance(raw_minutes, bool) or not isinstance(raw_minutes, int):
            raise ValueError(
                "Field 'structured_practical_task.estimated_minutes' "
                "must be an integer or null."
            )
        else:
            estimated_minutes = raw_minutes

    return PracticalTask(
        title=value["title"].strip(),
        description=value["description"].strip(),
        expected_result=value["expected_result"].strip(),
        estimated_minutes=estimated_minutes,
    )
