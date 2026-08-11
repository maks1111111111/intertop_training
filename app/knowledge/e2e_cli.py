"""E2E CLI for grounded Knowledge Base question answering.

Runs the full tenant-scoped retrieval and grounded AI answering pipeline
against an existing database and published knowledge documents.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from app.ai.config import OpenAIConfig
from app.ai.knowledge_answer_interfaces import KnowledgeAnswerResult
from app.env import load_project_env
from app.knowledge.question_answering_bootstrap import (
    create_knowledge_question_answering_service,
)
from app.knowledge.question_answering_service import KnowledgeQuestionAnsweringError

_SUPPORTED_LANGUAGES = ("ru", "kk", "en")


def _format_result(result: KnowledgeAnswerResult) -> str:
    """Format a grounded answer result for human-readable CLI output."""
    lines = [
        "ANSWER",
        result.answer,
        "",
        "SUFFICIENT_CONTEXT",
        str(result.sufficient_context).lower(),
        "",
        "CITATIONS",
    ]
    if result.citations:
        for citation in result.citations:
            lines.append(f"- source_number={citation.source_number}")
            lines.append(f"  document_id={citation.document_id}")
            lines.append(f"  chunk_index={citation.chunk_index}")
    else:
        lines.append("(none)")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run grounded Knowledge Base question answering against an "
            "existing database."
        ),
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--company-id",
        required=True,
        help="Tenant company identifier.",
    )
    parser.add_argument(
        "--question",
        required=True,
        help="Question to answer from the Knowledge Base.",
    )
    parser.add_argument(
        "--language",
        choices=_SUPPORTED_LANGUAGES,
        default="ru",
        help="Response language (default: ru).",
    )
    parser.add_argument(
        "--retrieval-limit",
        type=int,
        default=None,
        help="Optional positive retrieval limit override.",
    )
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    """Execute the E2E knowledge question answering CLI.

    Args:
        argv: Optional argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 on success, non-zero on failure).
    """
    load_project_env()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.retrieval_limit is not None and args.retrieval_limit <= 0:
        print(
            "Error: --retrieval-limit must be a positive integer.",
            file=sys.stderr,
        )
        return 2

    db_path = Path(args.db)
    if not db_path.exists():
        print("Error: database file does not exist.", file=sys.stderr)
        return 2

    try:
        config = OpenAIConfig.from_environment()
        service = create_knowledge_question_answering_service(config)
        result = service.answer(
            db_path,
            company_id=args.company_id,
            question=args.question,
            language=args.language,
            retrieval_limit=args.retrieval_limit,
        )
    except KnowledgeQuestionAnsweringError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_format_result(result))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
