# src/gui/dialogs/print_preview.py
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSpinBox,
    QComboBox,
    QProgressBar,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from services.print_service import PrintServiceBase
from models.print_job import PrintJob, PrintJobStatus
import logging

logger = logging.getLogger(__name__)


class PrintPreviewDialog(QDialog):
    def __init__(self, print_service: PrintServiceBase, parent=None):
        super().__init__(parent)
        self.print_service = print_service
        self.setWindowTitle("Print Documents")
        self.setModal(True)
        self.resize(400, 200)

        # Store document data
        self.order_ids = []
        self.pdf_content = None
        self.active_job_id = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)  # Add some padding
        layout.setSpacing(10)  # Space between elements

        # Info label
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        # Controls layout
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)  # Space between controls

        # Printer selection
        printer_layout = QVBoxLayout()
        printer_label = QLabel("Printer:")
        self.printer_combo = QComboBox()
        self.printer_combo.setMinimumWidth(200)  # Make the combo box wider
        printer_layout.addWidget(printer_label)
        printer_layout.addWidget(self.printer_combo)
        controls_layout.addLayout(printer_layout)

        # Copies
        copies_layout = QVBoxLayout()
        copies_label = QLabel("Copies:")
        self.copies_spin = QSpinBox()
        self.copies_spin.setMinimum(1)
        self.copies_spin.setMaximum(99)
        copies_layout.addWidget(copies_label)
        copies_layout.addWidget(self.copies_spin)
        controls_layout.addLayout(copies_layout)

        layout.addLayout(controls_layout)
        layout.addSpacing(10)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.print_button = QPushButton("Print")
        self.print_button.setMinimumWidth(80)
        self.print_button.clicked.connect(self._start_printing)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(80)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.print_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Initialize printers
        self._refresh_printers()

    def _refresh_printers(self):
        """Refresh the list of available printers"""
        self.printer_combo.clear()

        # Add available printers
        printers = self.print_service.get_available_printers()
        if not printers:
            logger.warning("No printers found")
            self.printer_combo.addItem("No printers available")
            self.print_button.setEnabled(False)
            return

        self.printer_combo.addItems(printers)

        # Set default printer if available
        default_printer = self.print_service.get_default_printer()
        if default_printer:
            index = self.printer_combo.findText(default_printer)
            if index >= 0:
                self.printer_combo.setCurrentIndex(index)

        self.print_button.setEnabled(True)

    def set_documents(self, order_ids: List[str], pdf_content: bytes):
        """Set the documents to print"""
        self.order_ids = order_ids
        self.pdf_content = pdf_content
        self.info_label.setText(f"Ready to print {len(order_ids)} order(s)")

        # Make sure we have printers available
        if (
            self.printer_combo.count() == 0
            or self.printer_combo.currentText() == "No printers available"
        ):
            self._refresh_printers()

    def _start_printing(self):
        """Start the print job"""
        if not self.pdf_content or not self.order_ids:
            QMessageBox.warning(self, "Error", "No documents to print")
            return

        try:
            printer_name = self.printer_combo.currentText()
            if not printer_name or printer_name == "No printers available":
                QMessageBox.warning(self, "Error", "No printer selected")
                return

            # Create print job
            job = PrintJob.create(
                order_ids=self.order_ids,
                printer_name=printer_name,
                copies=self.copies_spin.value(),
            )

            # Show progress bar
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            self.progress_bar.show()

            # Disable controls
            self._set_controls_enabled(False)

            # Use QTimer to handle callbacks in main thread
            def on_progress(current: int, total: int):
                QTimer.singleShot(0, lambda: self._update_progress(current, total))

            def on_complete(success: bool, error_message: Optional[str]):
                QTimer.singleShot(
                    0, lambda: self._print_completed(success, error_message)
                )

            # Submit print job
            self.active_job_id = self.print_service.submit_print_job(
                job=job,
                pdf_content=self.pdf_content,
                on_progress=on_progress,
                on_complete=on_complete,
            )

            # Update dialog state
            self.info_label.setText("Sending to printer...")

        except Exception as e:
            logger.error(f"Error starting print job: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to start print job: {str(e)}")
            self._set_controls_enabled(True)
            self.progress_bar.hide()

    def _update_progress(self, current: int, total: int):
        """Update progress bar"""
        value = int((current / total) * 100)
        self.progress_bar.setValue(value)
        self.info_label.setText(f"Printing... {value}%")

    def _print_completed(self, success: bool, error_message: Optional[str]):
        """Handle print job completion"""
        self.progress_bar.hide()
        self._set_controls_enabled(True)

        if success:
            QMessageBox.information(self, "Success", "Documents printed successfully!")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", f"Print job failed: {error_message}")

    def _set_controls_enabled(self, enabled: bool):
        """Enable or disable controls during printing"""
        self.print_button.setEnabled(enabled)
        self.printer_combo.setEnabled(enabled)
        self.copies_spin.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)
