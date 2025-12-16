"""Command-line entry point for generating the daily digest."""

import logging
import sys

from config import LOG_LEVEL
from graph import build_graph


def setup_logging():
    """Configure logging with appropriate format and level."""
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting AI News Agent")
    graph = build_graph()
    graph.invoke({})  # initial state is an empty dict
    logger.info("news.md generated successfully")
