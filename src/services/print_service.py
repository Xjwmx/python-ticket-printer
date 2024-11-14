# src/services/print_service.py

from datetime import datetime
import datetime as dt
from typing import List, Optional, Callable, Dict
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
import tempfile
import os
import logging
from pathlib import Path
from models.print_job import PrintJob, PrintJobStatus
from queue import Queue, Empty
from threading import Thread, Lock
import time

logger = logging.getLogger(__name__)


class PrintService:
    def __init__(self, dev_mode: bool = False):
        """Initialize print service"""
        self.dev_mode = dev_mode
        logger.info(f"Initializing PrintService (dev_mode={dev_mode})")

        # Add output directory setup for dev mode
        if self.dev_mode:
            self.output_dir = Path(__file__).parent.parent.parent / "output" / "prints"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Dev mode output directory: {self.output_dir}")

        # Rest of existing initialization
        self._printer = None
        self.active_jobs: Dict[str, PrintJob] = {}
        self.job_queue: Queue = Queue()
        self.job_lock = Lock()
        self.running = True
        self.print_thread = Thread(target=self._process_print_queue, daemon=True)
        self.print_thread.start()

    def get_print_output_dir(self) -> Optional[Path]:
        """Get the output directory for dev mode"""
        return self.output_dir if self.dev_mode else None

    @property
    def printer(self) -> QPrinter:
        """Lazy initialization of printer object"""
        if self._printer is None:
            self._printer = QPrinter(QPrinter.HighResolution)
            self._printer.setColorMode(QPrinter.Color)
            self._printer.setFullPage(False)
        return self._printer

    def get_available_printers(self) -> List[str]:
        """Get list of available printer names"""
        if self.dev_mode:
            return ["Development Printer", "PDF Output"]
        try:
            return [
                printer.printerName() for printer in QPrinterInfo.availablePrinters()
            ]
        except Exception as e:
            logger.error(f"Error getting available printers: {str(e)}")
            return []

    def get_default_printer(self) -> Optional[str]:
        """Get default printer name"""
        if self.dev_mode:
            return "Development Printer"
        try:
            default = QPrinterInfo.defaultPrinter()
            return default.printerName() if default else None
        except Exception as e:
            logger.error(f"Error getting default printer: {str(e)}")
            return None

    def submit_print_job(
        self,
        job: PrintJob,
        pdf_content: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[bool, Optional[str]], None]] = None,
    ) -> str:
        """Submit a new print job"""
        try:
            job.pdf_content = pdf_content

            with self.job_lock:
                self.active_jobs[job.id] = job

            self.job_queue.put((job, on_progress, on_complete))
            logger.info(f"Submitted print job {job.id} for {len(job.order_ids)} orders")

            return job.id

        except Exception as e:
            logger.error(f"Error submitting print job: {str(e)}")
            raise

    def get_job_status(self, job_id: str) -> Optional[PrintJobStatus]:
        """Get current status of a print job"""
        with self.job_lock:
            job = self.active_jobs.get(job_id)
            return job.status if job else None

    def shutdown(self):
        """Gracefully shut down the print service"""
        self.running = False
        if self.print_thread.is_alive():
            self.print_thread.join(timeout=5.0)

    def _process_print_queue(self):
        """Background thread for processing print jobs"""
        while self.running:
            try:
                # Get next job from queue with timeout
                try:
                    job, on_progress, on_complete = self.job_queue.get(timeout=1.0)
                except Empty:
                    continue  # No job available, continue polling

                with self.job_lock:
                    job.status = PrintJobStatus.PROCESSING

                # Process the job
                try:
                    success = self._print_job(job, on_progress)

                    with self.job_lock:
                        job.status = (
                            PrintJobStatus.COMPLETED
                            if success
                            else PrintJobStatus.FAILED
                        )
                        if not success:
                            job.error_message = "Print job failed"

                    if on_complete:
                        on_complete(success, job.error_message)

                except Exception as e:
                    logger.error(f"Error processing print job {job.id}: {str(e)}")
                    with self.job_lock:
                        job.status = PrintJobStatus.FAILED
                        job.error_message = str(e)

                    if on_complete:
                        on_complete(False, str(e))

                finally:
                    self.job_queue.task_done()

            except Exception as e:
                logger.error(f"Error in print queue processor: {str(e)}")
                time.sleep(1)  # Brief pause before retrying

        logger.info("Print queue processor shutting down")

    def _print_job(self, job: PrintJob, on_progress: Optional[Callable] = None) -> bool:
        """Process a single print job"""
        if not job.pdf_content:
            raise ValueError("No PDF content provided for print job")

        if self.dev_mode:
            logger.info(f"[DEV MODE] Processing print job {job.id}")
            try:
                # Save the PDF using correct datetime
                timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"print_job_{job.id}_{timestamp}.pdf"
                output_path = self.output_dir / filename

                logger.info(f"[DEV MODE] Attempting to save PDF to: {output_path}")

                with open(output_path, "wb") as f:
                    f.write(job.pdf_content)

                logger.info(f"[DEV MODE] Successfully saved PDF to: {output_path}")

                # Simulate printing progress
                total_steps = 5
                for step in range(total_steps):
                    if on_progress:
                        on_progress(step + 1, total_steps)
                    time.sleep(0.5)  # Simulate processing time

                logger.info(f"[DEV MODE] Completed simulated print job {job.id}")
                return True

            except Exception as e:
                logger.error(f"[DEV MODE] Error saving PDF: {str(e)}")
                logger.exception(
                    "Detailed error information:"
                )  # This will log the full stack trace
                return False

        else:
            try:
                # Real printing implementation would go here
                # For now, just simulate success
                logger.warning("Real printing not implemented yet")
                if on_progress:
                    on_progress(1, 1)
                return True

            except Exception as e:
                logger.error(f"Error printing job: {str(e)}")
                return False


def create_print_service(dev_mode: bool = False) -> PrintService:
    """
    Factory function to create a PrintService instance

    Args:
        dev_mode: If True, creates service in development mode with simulated printing

    Returns:
        PrintService instance
    """
    return PrintService(dev_mode=dev_mode)
