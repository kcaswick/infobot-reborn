"""CLI entry point for infobot.tools.

Usage:
    python -m infobot.tools \\
        --source /path/to/legacy/data \\
        --database data/infobot.db
"""

from infobot.tools.legacy_import import main

if __name__ == "__main__":
    main()
