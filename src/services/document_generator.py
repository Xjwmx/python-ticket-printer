import json
import tempfile
import shutil
import hashlib
from urllib.parse import urlparse
import requests
from datetime import datetime
from pathlib import Path
import logging
import os
import base64
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

logger = logging.getLogger(__name__)


class DocumentGenerator:
    def __init__(self):
        """Initialize the document generator with templates"""
        # Get the absolute path to the templates directory
        self.template_dir = Path(__file__).parent.parent / "templates"

        # Create a temp directory for image caching
        self.image_cache_dir = Path(tempfile.gettempdir()) / "shopify_print_images"
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Jinja2 environment with the templates directory
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)), autoescape=True
        )

        # Add custom filters
        self.env.filters["date"] = self._format_date
        self.env.filters["cached_image_path"] = self._get_cached_image_path

        # Get absolute paths for CSS files
        css_dir = self.template_dir / "styles"
        self.base_css = CSS(filename=str(css_dir / "base.css"))
        self.print_css = CSS(filename=str(css_dir / "print.css"))

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

    def _get_placeholder_data_uri(self) -> str:
        """Generate a simple SVG placeholder as a data URI"""
        svg = """<?xml version="1.0" encoding="UTF-8"?>
        <svg width="150" height="150" version="1.1" viewBox="0 0 150 150" xmlns="http://www.w3.org/2000/svg">
            <rect width="150" height="150" fill="#f0f0f0"/>
            <text x="75" y="75" font-family="Arial" font-size="14" 
                  text-anchor="middle" dominant-baseline="middle" fill="#666">
                No Image
            </text>
        </svg>"""

        encoded = base64.b64encode(svg.encode()).decode()
        return f"data:image/svg+xml;base64,{encoded}"

    def _download_image(self, url: str) -> Optional[Path]:
        """
        Download and cache an image from a URL

        Args:
            url: Image URL

        Returns:
            Path to cached image or None if download fails
        """
        try:
            # Create a unique filename based on the URL
            url_hash = hashlib.md5(url.encode()).hexdigest()
            parsed_url = urlparse(url)
            extension = Path(parsed_url.path).suffix or ".jpg"
            cached_path = self.image_cache_dir / f"{url_hash}{extension}"

            # If already cached, return path
            if cached_path.exists():
                return cached_path

            # Download the image
            response = requests.get(url, stream=True, timeout=5)
            response.raise_for_status()

            # Save to cache
            with open(cached_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)

            logger.info(f"Downloaded and cached image from {url} to {cached_path}")
            return cached_path

        except Exception as e:
            logger.error(f"Failed to download image from {url}: {str(e)}")
            return None

    def _get_cached_image_path(self, url: str) -> str:
        """
        Jinja2 filter to get path to cached image

        Args:
            url: Original image URL

        Returns:
            Path to cached image or data URI for placeholder
        """
        if not url:
            return self._get_placeholder_data_uri()

        if url.startswith("/api/placeholder"):
            return self._get_placeholder_data_uri()

        cached_path = self._download_image(url)
        if cached_path:
            return str(cached_path)
        return self._get_placeholder_data_uri()

    def _get_inventory_locations(self, variant: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract inventory locations and quantities from variant data"""
        try:
            inventory_levels = (
                variant.get("inventoryItem", {})
                .get("inventoryLevels", {})
                .get("edges", [])
            )

            locations = []
            for level in inventory_levels:
                node = level.get("node", {})
                location_name = node.get("location", {}).get("name", "Unknown")

                # Get available quantity
                quantities = node.get("quantities", [])
                available = 0
                for q in quantities:
                    if q.get("name") == "available":
                        available = q.get("quantity", 0)
                        break

                if location_name:
                    locations.append({"name": location_name, "quantity": available})

            # Sort locations by name for consistent display
            locations.sort(key=lambda x: x["name"])
            return (
                locations
                if locations
                else [{"name": "Default Location", "quantity": 0}]
            )

        except Exception as e:
            logger.error(f"Error getting inventory locations: {str(e)}")
            return [{"name": "Default Location", "quantity": 0}]

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
        try:
            line_items = order_data.get("lineItems", {}).get("edges", [])
            logger.info(f"Found {len(line_items)} raw line items")

            for edge in line_items:
                try:
                    node = edge.get("node", {})
                    variant = node.get("variant", {}) or {}
                    product = node.get("product", {}) or {}

                    # Get image URL with better fallback handling
                    image_url = None
                    if variant and variant.get("image", {}).get("url"):
                        image_url = variant["image"]["url"]
                    elif product.get("featuredImage", {}).get("url"):
                        image_url = product["featuredImage"]["url"]

                    if not image_url:
                        image_url = "/api/placeholder/150/150"

                    # Get inventory locations with quantities
                    locations = self._get_inventory_locations(variant)

                    item = {
                        "sku": node.get("sku", "No SKU"),
                        "quantity": node.get("quantity", 0),
                        "title": product.get("title", "Unknown Product"),
                        "variant_title": variant.get("title", ""),
                        "vendor": node.get("vendor", "No Vendor"),
                        "locations": locations,
                        "image_url": image_url,
                    }

                    processed_items.append(item)

                except Exception as e:
                    logger.error(f"Error processing line item: {str(e)}")
                    continue

            return processed_items

        except Exception as e:
            logger.error(f"Error processing line items: {str(e)}")
            return []

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
                # Generate PDF with base URL for asset resolution
                html = HTML(filename=temp_html_path, base_url=str(self.template_dir))
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

    def __del__(self):
        """Cleanup temporary files on deletion"""
        try:
            if hasattr(self, "image_cache_dir"):
                shutil.rmtree(self.image_cache_dir, ignore_errors=True)
        except:
            pass
