# src/services/document_generator.py

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
from pathlib import Path
import tempfile
import os
from typing import Dict, Any, List
import logging
from datetime import datetime
import requests
import json

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
        """Format ISO date string to human-readable format"""
        if not value:
            return ""
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            logger.error(f"Error formatting date {value}: {str(e)}")
            return value

    def _get_inventory_locations(self, variant: Dict[str, Any]) -> List[str]:
        """Extract inventory locations from variant data"""
        try:
            inventory_levels = (
                variant.get("inventoryItem", {})
                .get("inventoryLevels", {})
                .get("edges", [])
            )

            locations = []
            for level in inventory_levels:
                location_name = (
                    level.get("node", {}).get("location", {}).get("name", "Unknown")
                )
                if location_name:
                    locations.append(location_name)

            return locations if locations else ["Default Location"]

        except Exception as e:
            logger.error(f"Error getting inventory locations: {str(e)}")
            return ["Default Location"]

    def _get_shipping_method(self, order_data: Dict[str, Any]) -> str:
        """Extract shipping method with multiple fallbacks"""
        try:
            # Try shipping lines first (more reliable)
            shipping_lines = order_data.get("shippingLines", {}).get("edges", [])
            if shipping_lines and len(shipping_lines) > 0:
                first_line = shipping_lines[0].get("node", {})
                if title := first_line.get("title"):
                    return title
                if code := first_line.get("code"):
                    return code

            return "Standard Shipping"

        except Exception as e:
            logger.error(f"Error getting shipping method: {str(e)}")
            return "Standard Shipping"

    def _process_line_items(self, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process line items from order data"""
        processed_items = []
        logger.info("Processing line items...")

        try:
            line_items = order_data.get("lineItems", {}).get("edges", [])
            logger.info(f"Found {len(line_items)} raw line items")

            for edge in line_items:
                node = edge.get("node", {})
                variant = node.get("variant", {})
                product = node.get("product", {})

                # Get image URL directly from variant
                image_url = variant.get("image", {}).get(
                    "url", "/api/placeholder/150/150"
                )

                item = {
                    "sku": node.get("sku") or variant.get("sku", "No SKU"),
                    "quantity": node.get("quantity", 0),
                    "title": product.get("title", "Unknown Product"),
                    "variant_title": variant.get("title", ""),
                    "vendor": node.get("vendor", ""),
                    "locations": self._get_inventory_locations(variant),
                    "image_url": image_url,
                }

                logger.info(
                    f"Processed line item: {json.dumps({**item, 'image_url': '...'}, indent=2)}"
                )
                processed_items.append(item)

        except Exception as e:
            logger.error(f"Error processing line items: {str(e)}")
            logger.error(f"Order data: {json.dumps(order_data, indent=2)}")
            return []

        return processed_items

    def _process_order_data(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw order data into template-friendly format"""
        try:
            logger.info("Processing order data...")
            logger.info(f"Raw order data structure: {json.dumps(order_data, indent=2)}")

            # Handle both direct and nested data structures
            order_node = (
                order_data.get("data", {}).get("order", {})  # Nested structure
                if "data" in order_data
                else order_data  # Direct structure
            )

            logger.info(f"Order node: {json.dumps(order_node, indent=2)}")

            if not order_node:
                raise ValueError("Invalid order data structure")

            # Extract shipping address
            shipping = order_node.get("shippingAddress") or {}
            if not isinstance(shipping, dict):
                shipping = {}

            shipping_address = {
                "name": (
                    shipping.get("firstName", "") + " " + shipping.get("lastName", "")
                ).strip()
                or "No Name",
                "company": shipping.get("company", ""),
                "address1": shipping.get("address1", "No Address"),
                "address2": shipping.get("address2", ""),
                "city": shipping.get("city", "No City"),
                "province": shipping.get("province", "No Province"),
                "zip": shipping.get("zip", "No ZIP"),
                "country": shipping.get("country", "No Country"),
                "phone": shipping.get("phone", "No Phone"),
            }

            # Process line items
            line_items = self._process_line_items(order_node)

            # Get total
            total_price = (
                order_node.get("totalPriceSet", {})
                .get("shopMoney", {})
                .get("amount", "0.00")
            )

            # Compile template data
            template_data = {
                "order": {
                    "number": order_node.get("name", "N/A"),
                    "created_at": order_node.get("createdAt", ""),
                    "shipping_address": shipping_address,
                    "line_items": line_items,
                    "note": order_node.get("note", ""),
                    "shipping_method": self._get_shipping_method(order_node),
                    "total": total_price,
                }
            }

            logger.info(f"Final template data: {json.dumps(template_data, indent=2)}")
            return template_data

        except Exception as e:
            logger.error(f"Error processing order data: {str(e)}")
            logger.error(f"Order data: {json.dumps(order_data, indent=2)}")
            raise

    def generate_pick_ticket(self, order_data: Dict[str, Any]) -> bytes:
        """
        Generate a PDF pick ticket for an order

        Args:
            order_data: Order data from Shopify API

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
            orders_data: List of order data from Shopify API

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
