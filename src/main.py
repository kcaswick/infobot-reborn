"""Entry point for Infobot Reborn Discord bot."""

import asyncio
import logging

from infobot.config import Config
from infobot.discord import InfobotBot


def main() -> None:
    """Start the Discord bot."""
    try:
        config = Config.from_env()

        # Configure logging with the config-specified level
        logging.basicConfig(
            level=getattr(logging, config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        bot = InfobotBot(config)
        asyncio.run(bot.run_bot())
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        raise
    except KeyboardInterrupt:
        logging.info("Bot interrupted by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
