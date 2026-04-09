"""Console entry point for the ``ollama-dashboard`` command (pip install)."""

from __future__ import annotations

import logging
import os
import sys


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)
    try:
        from app import create_app

        app = create_app()
        host = os.getenv("OLLAMA_DASHBOARD_HOST", "127.0.0.1")
        port = int(
            os.getenv(
                "OLLAMA_DASHBOARD_PORT",
                os.getenv("PORT", "5000"),
            ),
        )
        logger.info("Ollama Dashboard — http://%s:%s", host, port)
        app.run(host=host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.exception("Failed to start: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
