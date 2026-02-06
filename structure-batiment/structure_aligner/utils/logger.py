import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure logging with the PRD-specified format."""
    fmt = "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
    logging.basicConfig(
        level=getattr(logging, level),
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
