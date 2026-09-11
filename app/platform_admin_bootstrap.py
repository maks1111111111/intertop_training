"""One-time operator command for establishing the first platform owner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from app.database.db import initialize_database
from app.repositories.platform_admin_repository import PlatformAdminRepository


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--user-id", type=int, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    initialize_database(args.db)
    try:
        owner = PlatformAdminRepository().bootstrap_owner(args.db, args.user_id)
    except (RuntimeError, ValueError) as error:
        print(f"Platform owner bootstrap failed: {error}", file=sys.stderr)
        return 2

    print(f"Platform owner bootstrap completed for user_id={owner.user_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
