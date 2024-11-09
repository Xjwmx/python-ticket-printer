# src/main.py
import json
import sys
import os
from pathlib import Path
import logging
from typing import Optional


def is_wsl() -> bool:
    """Check if running on Windows Subsystem for Linux (WSL)"""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except:
        return False


def setup_logging():
    """Configure application logging"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("shopify_print.log")],
    )


def check_print_output(print_service) -> Optional[dict]:
    """Check the latest print job output if it exists"""
    try:
        output_dir = print_service.get_print_output_dir()
        jobs = list(output_dir.glob("print_job_*"))

        if not jobs:
            return None

        latest_job = max(jobs, key=os.path.getctime)
        metadata_path = latest_job / "metadata.json"

        if metadata_path.exists():
            with open(metadata_path) as f:
                return json.load(f)

        return None

    except Exception as e:
        logging.error(f"Error checking print output: {str(e)}")
        return None


def main():
    """Application entry point"""
    try:
        # Set up logging first
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Starting Shopify Order Print System")

        # Add the src directory to the Python path
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if src_dir not in sys.path:
            sys.path.append(src_dir)

        # Import dependencies after sys.path is set up
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from gui.main_window import MainWindow
        from services.print_service import create_print_service

        # Initialize print service
        dev_mode = is_wsl() or os.environ.get("DEV_MODE") == "1"
        print_service = create_print_service(dev_mode=dev_mode)
        logger.info(
            f"Print service initialized in {'development' if dev_mode else 'production'} mode"
        )

        # In development mode, check latest print job
        if dev_mode:
            latest_job = check_print_output(print_service)
            if latest_job:
                logger.info("Latest print job metadata:")
                logger.info(json.dumps(latest_job, indent=2))

        # Create Qt Application
        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Use Fusion style for consistent cross-platform look

        # Create and show main window
        window = MainWindow()
        window.show()

        # Start event loop
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
