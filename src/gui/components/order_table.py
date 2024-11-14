# src/gui/components/order_table.py
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class OrderTableWidget(QTableWidget):
    def __init__(self):
        super().__init__()

        # Set up table structure
        self.columns = [
            "Order #",
            "Date",
            "Customer",
            "Location",
            "Total",
            "Status",
            "ID",  # ID column will be hidden
        ]
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)

        # Configure table properties
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.MultiSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)

        # Configure column properties
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Order #
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Date

        # Hide the ID column
        self.setColumnHidden(self.columns.index("ID"), True)

        # Enable sorting
        self.setSortingEnabled(True)

    def load_orders(self, orders_data):
        """Load orders data into the table"""
        try:
            logger.info("Processing orders data structure:")
            logger.info(json.dumps(orders_data, indent=2))

            self.setSortingEnabled(False)  # Disable sorting while updating
            self.setRowCount(0)  # Clear existing rows

            if not orders_data or not isinstance(orders_data, dict):
                logger.error(f"Invalid orders data received: {orders_data}")
                return

            orders = orders_data.get("data", {}).get("orders", {}).get("edges", [])
            logger.info(f"Found {len(orders)} orders to process")

            for i, edge in enumerate(orders):
                logger.info(f"Processing order {i+1}:")
                logger.info(json.dumps(edge, indent=2))

                node = edge.get("node", {})
                if not node:
                    logger.warning(f"Skipping order {i+1} - no node data")
                    continue

                try:
                    # Extract data with safe gets and defaults
                    order_name = node.get("name", "N/A")

                    # Format date
                    created_at = node.get("createdAt", "")
                    formatted_date = self._format_date(created_at)

                    # Handle shipping address safely
                    shipping_address = node.get("shippingAddress", {})
                    if shipping_address is None:
                        shipping_address = {}

                    customer_name = shipping_address.get("name", "No Name")
                    city = shipping_address.get("city", "No City")
                    province = shipping_address.get("province", "No Province")
                    location = (
                        f"{city}, {province}" if city != "No City" else "No Location"
                    )

                    # Format total price
                    money = node.get("totalPriceSet", {}).get("shopMoney", {})
                    currency = money.get("currencyCode", "USD")
                    amount = money.get("amount", "0.00")
                    formatted_total = f"{currency} {amount}"

                    # Create table items
                    items = [
                        self._create_item(order_name),
                        self._create_item(formatted_date),
                        self._create_item(customer_name),
                        self._create_item(location),
                        self._create_item(formatted_total),
                        self._create_item("Unprinted"),
                        self._create_item(node.get("id", "")),
                    ]

                    # Add row
                    row_position = self.rowCount()
                    self.insertRow(row_position)
                    for col, item in enumerate(items):
                        self.setItem(row_position, col, item)

                except Exception as e:
                    logger.error(f"Error processing order {i+1}: {str(e)}")
                    logger.error(f"Order data: {json.dumps(node, indent=2)}")
                    continue

            self.setSortingEnabled(True)  # Re-enable sorting

        except Exception as e:
            logger.error(f"Error loading orders into table: {str(e)}")
            raise

    def _format_date(self, date_str: str) -> str:
        """Format date string safely"""
        if not date_str:
            return "No Date"
        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            return "Invalid Date"

    def _create_item(self, text):
        """Create a non-editable table item"""
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def get_selected_orders(self):
        """Return list of selected order IDs"""
        selected_rows = self.selectionModel().selectedRows()
        id_column = self.columns.index("ID")
        return [self.item(row.row(), id_column).text() for row in selected_rows]
