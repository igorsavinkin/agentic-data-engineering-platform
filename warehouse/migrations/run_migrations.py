#!/usr/bin/env python3
"""CLI entry point for warehouse migrations.

Usage:
    # Upgrade to latest version
    python -m warehouse.migrations run upgrade head

    # Downgrade by one version
    python -m warehouse.migrations run downgrade -1

    # Show current version
    python -m warehouse.migrations run current

    # Show migration history
    python -m warehouse.migrations run history
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found"
import sys
from pathlib import Path

# Add project root to path so we can import alembic
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def main() -> None:
    """Run alembic commands with our configuration."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Get the directory containing this script (migrations/)
    migrations_dir = Path(__file__).parent
    alembic_cfg = Config(str(migrations_dir / "alembic.ini"))

    # Override script_location to point to migrations directory
    alembic_cfg.set_main_option("script_location", str(migrations_dir))

    cmd = sys.argv[1]
    args = sys.argv[2:]

    try:
        if cmd == "upgrade":
            revision = args[0] if args else "head"
            command.upgrade(alembic_cfg, revision)
            print(f"Upgraded to {revision}")
        elif cmd == "downgrade":
            revision = args[0] if args else "-1"
            command.downgrade(alembic_cfg, revision)
            print(f"Downgraded to {revision}")
        elif cmd == "current":
            command.current(alembic_cfg)
        elif cmd == "history":
            command.history(alembic_cfg)
        elif cmd == "stamp":
            revision = args[0] if args else "head"
            command.stamp(alembic_cfg, revision)
            print(f"Stamped to {revision}")
        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)
            sys.exit(1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
