# src/gui/main_window.py
import os
from typing import List
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStatusBar,
    QMessageBox,
)
from PySide6.QtCore import Qt
from gui.components.order_table import OrderTableWidget
from gui.dialogs.print_preview import PrintPreviewDialog
from services.shopify_client import create_client, ShopifyError
from services.document_generator import DocumentGenerator
from services.print_service import create_print_service
import logging
import json

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shopify Order Print System")
        self.setMinimumSize(1024, 768)

        # Initialize services
        try:
            self.shopify_client = create_client()
            self.document_generator = DocumentGenerator()
            # Check if running in WSL or dev mode
            dev_mode = (
                "WSL_DISTRO_NAME" in os.uname().release
                or os.environ.get("DEV_MODE") == "1"
            )
            self.print_service = create_print_service(dev_mode=dev_mode)
        except Exception as e:
            logger.error(f"Failed to initialize services: {str(e)}")
            QMessageBox.critical(
                self,
                "Error",
                "Failed to initialize application services. Please check your configuration.",
            )
            raise

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create toolbar layout
        toolbar_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Orders")
        self.refresh_button.clicked.connect(self.refresh_orders)
        self.print_button = QPushButton("Print Selected")
        self.print_button.clicked.connect(self.print_selected)
        toolbar_layout.addWidget(self.refresh_button)
        toolbar_layout.addWidget(self.print_button)
        toolbar_layout.addStretch()

        # Create order table
        self.order_table = OrderTableWidget()

        # Add widgets to main layout
        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(self.order_table)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Load initial data
        self.refresh_orders()

    def refresh_orders(self):
        """Fetch and display unprinted orders"""
        if not self.shopify_client:
            self.status_bar.showMessage("Shopify client not initialized")
            return

        try:
            self.status_bar.showMessage("Fetching orders...")
            self.refresh_button.setEnabled(False)

            orders_result = self.shopify_client.get_unprinted_orders()

            # Debug: Log the raw response
            logger.info("Raw Shopify response:")
            logger.info(json.dumps(orders_result, indent=2))

            if not orders_result:
                self.status_bar.showMessage("No orders received from Shopify")
                return

            self.order_table.load_orders(orders_result)
            count = self.order_table.rowCount()
            self.status_bar.showMessage(
                f"No orders found" if count == 0 else f"Loaded {count} orders"
            )

        except ShopifyError as e:
            logger.error(f"Shopify API error: {str(e)}")
            self.status_bar.showMessage("Failed to fetch orders from Shopify")
            QMessageBox.warning(self, "Shopify Error", str(e))
        except Exception as e:
            logger.error(f"Error refreshing orders: {str(e)}")
            self.status_bar.showMessage("Error loading orders")
            QMessageBox.critical(self, "Error", f"Failed to load orders: {str(e)}")
        finally:
            self.refresh_button.setEnabled(True)

    def print_selected(self):
        """Print selected orders"""
        selected_orders = self.order_table.get_selected_orders()
        if not selected_orders:
            self.status_bar.showMessage("No orders selected")
            return

        try:
            self.status_bar.showMessage(
                f"Preparing {len(selected_orders)} orders for printing..."
            )

            # Get full order details for selected orders
            order_details = []
            for order_id in selected_orders:
                details = self.shopify_client.get_order_details(order_id)
                if details and "data" in details and "order" in details["data"]:
                    order_details.append(details["data"]["order"])
                else:
                    raise ValueError(f"Failed to get details for order {order_id}")

            # Generate PDFs
            pdfs = self.document_generator.generate_batch_pick_tickets(order_details)
            if not pdfs:
                raise ValueError("No documents generated")

            # Combine PDFs into a single document
            combined_pdf = self._combine_pdfs(pdfs)

            # Show print preview dialog
            dialog = PrintPreviewDialog(self.print_service, self)
            dialog.set_documents(selected_orders, combined_pdf)

            if dialog.exec():
                self.status_bar.showMessage("Print job submitted successfully")
            else:
                self.status_bar.showMessage("Print cancelled")

        except Exception as e:
            logger.error(f"Error preparing print job: {str(e)}")
            self.status_bar.showMessage("Error preparing documents for printing")
            QMessageBox.critical(
                self, "Error", f"Failed to prepare documents for printing: {str(e)}"
            )

    def _combine_pdfs(self, pdf_list: List[bytes]) -> bytes:
        """Combine multiple PDFs into a single document"""
        try:
            from PyPDF2 import PdfReader, PdfWriter
            import io

            writer = PdfWriter()

            # Add each PDF to the writer
            for pdf_content in pdf_list:
                reader = PdfReader(io.BytesIO(pdf_content))
                for page in reader.pages:
                    writer.add_page(page)

            # Write the combined PDF to bytes
            output = io.BytesIO()
            writer.write(output)
            return output.getvalue()

        except Exception as e:
            logger.error(f"Error combining PDFs: {str(e)}")
            raise
