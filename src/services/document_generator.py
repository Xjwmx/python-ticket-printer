# src/services/document_generator.py

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
from pathlib import Path
import tempfile
import os
from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentGenerator:
    def __init__(self):
        """Initialize the document generator with templates"""
        # Get the absolute path to the templates directory
        self.template_dir = Path(__file__).parent.parent / "templates"

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)), autoescape=True
        )

        # Add custom filters
        self.env.filters["date"] = self._format_date

        # Load base CSS files
        self.base_css = CSS(filename=str(self.template_dir / "styles" / "base.css"))
        self.print_css = CSS(filename=str(self.template_dir / "styles" / "print.css"))

    def _format_date(self, value):
        """
        Custom Jinja2 filter to format dates

        Args:
            value: ISO date string from Shopify

        Returns:
            str: Formatted date string
        """
        if not value:
            return ""
        try:
            # Parse ISO format date and convert to local timezone
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            logger.error(f"Error formatting date {value}: {str(e)}")
            return value

    def _process_line_items(self, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract and process line items from order data"""
        processed_items = []

        try:
            line_items = order_data.get("lineItems", {}).get("edges", [])
            for edge in line_items:
                node = edge.get("node", {})
                variant = node.get("variant", {})
                product = node.get("product", {})

                # Get inventory location
                inventory_levels = (
                    variant.get("inventoryItem", {})
                    .get("inventoryLevels", {})
                    .get("edges", [])
                )
                locations = [
                    level.get("node", {}).get("location", {}).get("name", "Unknown")
                    for level in inventory_levels
                ]

                item = {
                    "sku": node.get("sku", "N/A"),
                    "quantity": node.get("quantity", 0),
                    "title": product.get("title", "Unknown Product"),
                    "variant_title": variant.get("title", ""),
                    "vendor": node.get("vendor", ""),
                    "locations": locations,
                }
                processed_items.append(item)

        except Exception as e:
            logger.error(f"Error processing line items: {str(e)}")

        return processed_items

    def _process_order_data(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw order data into template-friendly format"""
        try:
            # Extract shipping address
            shipping = order_data.get("shippingAddress", {})
            shipping_address = {
                "name": shipping.get("firstName", "")
                + " "
                + shipping.get("lastName", ""),
                "company": shipping.get("company", ""),
                "address1": shipping.get("address1", ""),
                "address2": shipping.get("address2", ""),
                "city": shipping.get("city", ""),
                "province": shipping.get("province", ""),
                "zip": shipping.get("zip", ""),
                "country": shipping.get("country", ""),
                "phone": shipping.get("phone", ""),
            }

            # Process line items
            line_items = self._process_line_items(order_data)

            # Compile template data
            template_data = {
                "order_number": order_data.get("name", "N/A"),
                "created_at": order_data.get("createdAt", ""),
                "shipping_address": shipping_address,
                "line_items": line_items,
                "note": order_data.get("note", ""),
                "shipping_method": self._get_shipping_method(order_data),
                "total": (
                    order_data.get("totalPriceSet", {})
                    .get("shopMoney", {})
                    .get("amount", "0.00")
                ),
            }

            return template_data

        except Exception as e:
            logger.error(f"Error processing order data: {str(e)}")
            raise

    def _get_shipping_method(self, order_data: Dict[str, Any]) -> str:
        """Extract shipping method from order data"""
        try:
            fulfillment_orders = order_data.get("fulfillmentOrders", {}).get(
                "edges", []
            )
            if fulfillment_orders:
                method = (
                    fulfillment_orders[0]
                    .get("node", {})
                    .get("deliveryMethod", {})
                    .get("methodType", "Unknown")
                )
                return method
        except Exception as e:
            logger.error(f"Error getting shipping method: {str(e)}")
        return "Unknown"

    def generate_pick_ticket(self, order_data: Dict[str, Any]) -> bytes:
        """
        Generate a PDF pick ticket for an order

        Args:
            order_data: Processed order data from Shopify

        Returns:
            bytes: Generated PDF content

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Process order data for template
            template_data = self._process_order_data(order_data)

            # Get template
            template = self.env.get_template("pick_ticket.html")

            # Render HTML
            html_content = template.render(**template_data)

            # Create temporary file for HTML
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False
            ) as temp_html:
                temp_html.write(html_content)
                temp_html_path = temp_html.name

            try:
                # Generate PDF
                html = HTML(filename=temp_html_path)
                pdf_content = html.write_pdf(
                    stylesheets=[self.base_css, self.print_css]
                )
                return pdf_content

            finally:
                # Clean up temporary file
                os.unlink(temp_html_path)

        except Exception as e:
            logger.error(f"Failed to generate pick ticket: {str(e)}")
            raise

    def generate_batch_pick_tickets(
        self, orders_data: List[Dict[str, Any]]
    ) -> List[bytes]:
        """
        Generate PDF pick tickets for multiple orders

        Args:
            orders_data: List of order data from Shopify

        Returns:
            List[bytes]: List of generated PDF contents

        Raises:
            Exception: If batch generation fails
        """
        pdfs = []
        errors = []

        for order_data in orders_data:
            try:
                pdf = self.generate_pick_ticket(order_data)
                pdfs.append(pdf)
            except Exception as e:
                order_number = order_data.get("name", "Unknown")
                errors.append(f"Order {order_number}: {str(e)}")

        if errors:
            error_msg = "\n".join(errors)
            raise Exception(f"Errors generating pick tickets:\n{error_msg}")

        return pdfs
