import pytest
from pathlib import Path
import os
from datetime import datetime
from src.services.document_generator import DocumentGenerator
from PyPDF2 import PdfReader
import io
import tempfile
import json


@pytest.fixture
def document_generator():
    """Fixture to create a DocumentGenerator instance"""
    return DocumentGenerator()


@pytest.fixture
def sample_order_data():
    """Fixture providing sample order data matching Shopify's structure"""
    return {
        "id": "gid://shopify/Order/12345",
        "name": "#1001",
        "createdAt": "2024-01-15T10:30:00Z",
        "note": "Please handle with care",
        "shippingAddress": {
            "firstName": "John",
            "lastName": "Doe",
            "company": "ACME Corp",
            "address1": "123 Main St",
            "address2": "Suite 100",
            "city": "Springfield",
            "province": "IL",
            "zip": "62701",
            "country": "United States",
            "phone": "555-123-4567",
        },
        "totalPriceSet": {"shopMoney": {"amount": "156.99", "currencyCode": "USD"}},
        "lineItems": {
            "edges": [
                {
                    "node": {
                        "sku": "WIDGET-001",
                        "quantity": 2,
                        "vendor": "WidgetCo",
                        "product": {"title": "Premium Widget"},
                        "variant": {
                            "title": "Blue / Large",
                            "inventoryItem": {
                                "inventoryLevels": {
                                    "edges": [
                                        {
                                            "node": {
                                                "location": {"name": "Main Warehouse"}
                                            }
                                        }
                                    ]
                                }
                            },
                        },
                    }
                }
            ]
        },
        "fulfillmentOrders": {
            "edges": [{"node": {"deliveryMethod": {"methodType": "SHIPPING"}}}]
        },
    }


def test_initialization(document_generator):
    """Test proper initialization of DocumentGenerator"""
    assert document_generator.env is not None
    assert document_generator.template_dir.exists()
    assert (document_generator.template_dir / "styles" / "base.css").exists()
    assert (document_generator.template_dir / "styles" / "print.css").exists()


def test_format_date_filter(document_generator):
    """Test the custom date formatting filter"""
    test_date = "2024-01-15T10:30:00Z"
    formatted = document_generator._format_date(test_date)
    assert formatted == "2024-01-15 10:30"

    # Test invalid date
    assert document_generator._format_date("invalid-date") == "invalid-date"

    # Test empty date
    assert document_generator._format_date("") == ""


def test_process_line_items(document_generator, sample_order_data):
    """Test line item processing from order data"""
    processed_items = document_generator._process_line_items(sample_order_data)

    assert len(processed_items) == 1
    item = processed_items[0]

    assert item["sku"] == "WIDGET-001"
    assert item["quantity"] == 2
    assert item["title"] == "Premium Widget"
    assert item["variant_title"] == "Blue / Large"
    assert item["vendor"] == "WidgetCo"
    assert item["locations"] == ["Main Warehouse"]


def test_process_order_data(document_generator, sample_order_data):
    """Test order data processing for template"""
    processed_data = document_generator._process_order_data(sample_order_data)

    assert processed_data["order_number"] == "#1001"
    assert processed_data["created_at"] == "2024-01-15T10:30:00Z"
    assert processed_data["note"] == "Please handle with care"
    assert processed_data["total"] == "156.99"

    # Check shipping address
    shipping = processed_data["shipping_address"]
    assert shipping["name"] == "John Doe"
    assert shipping["company"] == "ACME Corp"
    assert shipping["address1"] == "123 Main St"
    assert shipping["city"] == "Springfield"
    assert shipping["province"] == "IL"

    # Check line items
    assert len(processed_data["line_items"]) == 1
    assert processed_data["shipping_method"] == "SHIPPING"


def test_generate_pick_ticket(document_generator, sample_order_data):
    """Test PDF generation for a single order"""
    pdf_content = document_generator.generate_pick_ticket(sample_order_data)

    assert pdf_content is not None
    assert len(pdf_content) > 0

    # Verify PDF structure
    pdf = PdfReader(io.BytesIO(pdf_content))
    assert len(pdf.pages) == 1  # Each order should be one page


def test_generate_batch_pick_tickets(document_generator, sample_order_data):
    """Test batch PDF generation"""
    # Create multiple orders
    orders = [sample_order_data, sample_order_data.copy()]
    orders[1]["name"] = "#1002"  # Change order number for second order

    pdfs = document_generator.generate_batch_pick_tickets(orders)

    assert len(pdfs) == 2
    for pdf_content in pdfs:
        assert len(pdf_content) > 0
        pdf = PdfReader(io.BytesIO(pdf_content))
        assert len(pdf.pages) == 1


def test_error_handling(document_generator):
    """Test error handling for invalid data"""
    # Test with empty order data
    with pytest.raises(Exception):
        document_generator.generate_pick_ticket({})

    # Test with missing required fields
    invalid_order = {
        "id": "test",
        "name": "#1003",
        # Missing other required fields
    }
    with pytest.raises(Exception):
        document_generator.generate_pick_ticket(invalid_order)


def test_template_rendering(document_generator, sample_order_data):
    """Test template rendering without PDF generation"""
    template_data = document_generator._process_order_data(sample_order_data)
    template = document_generator.env.get_template("pick_ticket.html")
    html_content = template.render(**template_data)

    # Verify essential elements in HTML
    assert sample_order_data["name"] in html_content
    assert "John Doe" in html_content
    assert "Premium Widget" in html_content
    assert "WIDGET-001" in html_content


def test_css_loading(document_generator):
    """Test CSS file loading"""
    assert document_generator.base_css is not None
    assert document_generator.print_css is not None

    # Verify CSS content
    base_css_path = document_generator.template_dir / "styles" / "base.css"
    print_css_path = document_generator.template_dir / "styles" / "print.css"

    assert base_css_path.exists()
    assert print_css_path.exists()
