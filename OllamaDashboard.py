#!/usr/bin/env python
"""Ollama Dashboard - Main entry point.

This is the proper entrypoint for running the Ollama Dashboard application.
Usage: python OllamaDashboard.py
"""

import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for Ollama Dashboard."""
    try:
        # Ensure we're in the right directory
        app_dir = Path(__file__).parent
        os.chdir(app_dir)
        sys.path.insert(0, str(app_dir))

        logger.info("=" * 70)
        logger.info("OLLAMA DASHBOARD - STARTING")
        logger.info("=" * 70)
        logger.info("📦 Loading Flask application...")

        # Import and create Flask app
        from app import create_app
        app = create_app()
        logger.info("✅ Flask loaded")

        # Run the development server
        logger.info("\n" + "=" * 70)
        logger.info("🚀 STARTING SERVER")
        logger.info("=" * 70)
        logger.info("📍 http://127.0.0.1:5000")
        logger.info("=" * 70 + "\n")

        # Start server (localhost only)
        app.run(
            host='127.0.0.1',
            port=5000,
            debug=False,
            threaded=True
        )

    except KeyboardInterrupt:
        logger.info("\n✅ Stopped")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
