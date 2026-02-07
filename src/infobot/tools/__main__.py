"""CLI entry point for infobot.tools.legacy_import.

Usage:
    python -m infobot.tools.legacy_import \\
        --source /path/to/legacy/data \\
        --database data/infobot.db
"""

from infobot.tools.legacy_import import main

if __name__ == "__main__":
    main()
