"""Prompt builder for AI practical-task generation."""

from __future__ import annotations

from app.ai.practical_task_generation_interfaces import PracticalTaskGenerationRequest


class PracticalTaskPromptBuilder:
    """Build text prompts for AI practical-task generation."""

    def build_practical_task_generation_prompt(
        self,
        request: PracticalTaskGenerationRequest,
    ) -> str:
        """Build a prompt for generating one structured practical task."""
        lesson = request.lesson
        title = lesson.title.strip() or "Untitled lesson"
        content = lesson.content.strip()

        if not content:
            return ""

        lines = [
            "Create one structured practical task for the lesson below.",
            "",
            "Your task:",
            "1. Design a realistic hands-on exercise based only on the lesson material.",
            "2. Do not invent corporate rules or procedures absent from the source.",
            "3. The task must be actionable and verifiable.",
            "",
            "Return ONLY valid JSON.",
            "Do not use Markdown.",
            "Do not wrap JSON in code fences.",
            "Use exactly this schema:",
            "",
            "{",
            '  "structured_practical_task": {',
            '    "title": "...",',
            '    "description": "...",',
            '    "expected_result": "...",',
            '    "estimated_minutes": 10',
            "  }",
            "}",
            "",
            "Field rules:",
            '- "structured_practical_task.title": short, action-oriented task title.',
            '- "structured_practical_task.description": clear instructions',
            "  describing what the learner should do.",
            '- "structured_practical_task.expected_result": observable acceptance',
            "  criteria indicating successful completion.",
            '- "structured_practical_task.estimated_minutes": positive integer',
            "  estimate for completing the task, or null when no reasonable",
            "  estimate is available.",
            "",
            f"Lesson title: {title}",
            "",
            "Lesson content:",
            content,
        ]
        return "\n".join(lines)
