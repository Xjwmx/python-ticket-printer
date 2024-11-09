# src/services/print_service.py

from typing import List, Optional, Callable, Dict, Union
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from pathlib import Path
import tempfile
import logging
import json
import os
import time
from datetime import datetime
from queue import Queue
from threading import Thread, Lock, Event
import shutil
from abc import ABC, abstractmethod

from models.print_job import PrintJob, PrintJobStatus

logger = logging.getLogger(__name__)


class PrintServiceBase(ABC):
    """Base class for print services"""

    @abstractmethod
    def get_available_printers(self) -> List[str]:
        """Get list of available printer names"""
        pass

    @abstractmethod
    def get_default_printer(self) -> Optional[str]:
        """Get default printer name"""
        pass

    @abstractmethod
    def submit_print_job(
        self,
        job: PrintJob,
        pdf_content: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[bool, Optional[str]], None]] = None,
    ) -> str:
        """Submit a print job"""
        pass

    @abstractmethod
    def get_job_status(self, job_id: str) -> Optional[PrintJobStatus]:
        """Get current status of a print job"""
        pass


class DevPrintService(PrintServiceBase):
    """Development-friendly print service that simulates printing operations"""

    def __init__(self):
        # Set up output directory
        self.output_dir = Path(tempfile.gettempdir()) / "shopify_print_output"
        self.output_dir.mkdir(exist_ok=True)

        # Create mock printers with properties
        self.mock_printers = {
            "DEV_PDF_Printer": {
                "type": "pdf",
                "status": "online",
                "delay": 1.0,  # Seconds per page
                "error_rate": 0.0,  # 0% error rate
            },
            "DEV_Preview_Printer": {
                "type": "preview",
                "status": "online",
                "delay": 0.5,
                "error_rate": 0.1,  # 10% error rate
            },
            "DEV_Network_Printer": {
                "type": "network",
                "status": "online",
                "delay": 2.0,
                "error_rate": 0.2,  # 20% error rate
            },
        }

        # Job management
        self.active_jobs: Dict[str, PrintJob] = {}
        self.job_queue: Queue = Queue()
        self.job_lock = Lock()
        self.stop_event = Event()

        # Start worker thread
        self.worker_thread = Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

        logger.info(
            f"Dev Print Service initialized. Output directory: {self.output_dir}"
        )

    def get_available_printers(self) -> List[str]:
        """Get list of mock printer names"""
        return [
            name
            for name, info in self.mock_printers.items()
            if info["status"] == "online"
        ]

    def get_default_printer(self) -> Optional[str]:
        """Get default mock printer name"""
        available = self.get_available_printers()
        return available[0] if available else None

    def submit_print_job(
        self,
        job: PrintJob,
        pdf_content: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[bool, Optional[str]], None]] = None,
    ) -> str:
        """Simulate printing by saving to file"""
        try:
            # Create job-specific directory
            job_dir = self.output_dir / f"print_job_{job.id}"
            job_dir.mkdir(exist_ok=True)
            job.output_path = job_dir

            # Save PDF content
            pdf_path = job_dir / "output.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_content)

            # Update job status and save metadata
            job.update_status(PrintJobStatus.PENDING)
            job.to_json_file(job_dir / "metadata.json")

            # Add to processing queue
            with self.job_lock:
                self.active_jobs[job.id] = job
            self.job_queue.put((job, on_progress, on_complete))

            logger.info(f"Dev print job {job.id} saved to {job_dir}")
            return job.id

        except Exception as e:
            error_msg = f"Error in dev print job {job.id}: {str(e)}"
            logger.error(error_msg)
            if on_complete:
                on_complete(False, error_msg)
            raise

    def get_job_status(self, job_id: str) -> Optional[PrintJobStatus]:
        """Get current status of a print job"""
        try:
            # Check active jobs first
            with self.job_lock:
                if job_id in self.active_jobs:
                    return self.active_jobs[job_id].status

            # Check completed job files
            job_dir = self.output_dir / f"print_job_{job_id}"
            if not job_dir.exists():
                return None

            metadata_path = job_dir / "metadata.json"
            if metadata_path.exists():
                job = PrintJob.from_json_file(metadata_path)
                return job.status

            return None

        except Exception as e:
            logger.error(f"Error getting job status: {str(e)}")
            return None

    def _process_queue(self):
        """Background worker for processing print jobs"""
        while not self.stop_event.is_set():
            try:
                # Get next job from queue
                job, on_progress, on_complete = self.job_queue.get(timeout=1.0)

                try:
                    # Simulate printing
                    job.update_status(PrintJobStatus.PROCESSING)
                    printer_info = self.mock_printers.get(job.printer_name, {})

                    # Simulate progress
                    total_pages = len(job.order_ids)
                    for i in range(total_pages):
                        if on_progress:
                            on_progress(i + 1, total_pages)
                        time.sleep(printer_info.get("delay", 1.0))

                    # Simulate potential failures
                    import random

                    success = random.random() > printer_info.get("error_rate", 0.0)

                    # Update job status
                    status = (
                        PrintJobStatus.COMPLETED if success else PrintJobStatus.FAILED
                    )
                    error_msg = (
                        None
                        if success
                        else f"Simulated printer error for {job.printer_name}"
                    )

                    job.update_status(status, error_msg)
                    if job.output_path:
                        job.to_json_file(job.output_path / "metadata.json")

                    if on_complete:
                        on_complete(success, error_msg)

                except Exception as e:
                    logger.error(f"Error processing job {job.id}: {str(e)}")
                    job.update_status(PrintJobStatus.FAILED, str(e))
                    if job.output_path:
                        job.to_json_file(job.output_path / "metadata.json")
                    if on_complete:
                        on_complete(False, str(e))

                finally:
                    # Remove from active jobs if complete
                    if job.status.is_terminal():
                        with self.job_lock:
                            self.active_jobs.pop(job.id, None)
                    self.job_queue.task_done()

            except Queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in print queue processor: {str(e)}")
                time.sleep(1)

    def get_print_output_dir(self) -> Path:
        """Get the directory where print jobs are saved"""
        return self.output_dir

    def shutdown(self):
        """Shutdown the print service"""
        self.stop_event.set()
        self.worker_thread.join()
        logger.info("Print service shut down")


class ProductionPrintService(PrintServiceBase):
    """Production print service for real printing operations"""

    def __init__(self):
        # Initialize printer settings
        self.printer = QPrinter(QPrinter.HighResolution)
        self.printer.setColorMode(QPrinter.Color)
        self.printer.setFullPage(False)

        # Job management
        self.active_jobs: Dict[str, PrintJob] = {}
        self.job_lock = Lock()

        logger.info("Production Print Service initialized")

    def get_available_printers(self) -> List[str]:
        """Get list of system printers"""
        return [printer.printerName() for printer in QPrinterInfo.availablePrinters()]

    def get_default_printer(self) -> Optional[str]:
        """Get system default printer"""
        default = QPrinterInfo.defaultPrinter()
        return default.printerName() if default else None

    def submit_print_job(
        self,
        job: PrintJob,
        pdf_content: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_complete: Optional[Callable[[bool, Optional[str]], None]] = None,
    ) -> str:
        """Submit a real print job"""
        try:
            # Save PDF temporarily
            temp_file = None
            try:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_file.write(pdf_content)
                temp_file.close()

                # Configure printer
                self.printer.setPrinterName(job.printer_name)
                self.printer.setCopyCount(job.copies)
                self.printer.setDocName(f"Order Print Job {job.id}")

                # Print using system command
                if os.name == "nt":  # Windows
                    cmd = f'Start-Process -FilePath "{temp_file.name}" -Verb Print -PrinterName "{job.printer_name}"'
                    success = os.system(f'powershell -Command "{cmd}"') == 0
                else:  # Unix/Linux
                    success = (
                        os.system(
                            f'lp -n {job.copies} -d "{job.printer_name}" "{temp_file.name}"'
                        )
                        == 0
                    )

                if not success:
                    raise Exception("Print command failed")

                # Update progress
                if on_progress:
                    on_progress(1, 1)

                # Update job status
                with self.job_lock:
                    job.update_status(PrintJobStatus.COMPLETED)
                    self.active_jobs[job.id] = job

                if on_complete:
                    on_complete(True, None)

                return job.id

            finally:
                # Clean up temp file
                if temp_file and os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)

        except Exception as e:
            error_msg = f"Print job failed: {str(e)}"
            logger.error(error_msg)

            with self.job_lock:
                job.update_status(PrintJobStatus.FAILED, error_msg)
                self.active_jobs[job.id] = job

            if on_complete:
                on_complete(False, error_msg)
            raise

    def get_job_status(self, job_id: str) -> Optional[PrintJobStatus]:
        """Get current status of a print job"""
        with self.job_lock:
            job = self.active_jobs.get(job_id)
            return job.status if job else None


def create_print_service(dev_mode: bool = True) -> PrintServiceBase:
    """Create print service based on environment"""
    if dev_mode:
        return DevPrintService()
    return ProductionPrintService()
