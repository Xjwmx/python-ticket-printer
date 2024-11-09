# src/tests/test_shopify_client.py
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from services.shopify_client import create_client
import json


def print_json(data):
    """Print JSON data in a readable format"""
    print(json.dumps(data, indent=2))


def test_shopify_client():
    try:
        # Create client
        print("Creating Shopify client...")
        client = create_client()

        # Test getting unprinted orders
        print("\nFetching unprinted orders...")
        orders_result = client.get_unprinted_orders(limit=5)  # Limit to 5 for testing
        print("\nUnprinted Orders Result:")
        print_json(orders_result)

        # If we got orders, test getting details for the first one
        if orders_result.get("data", {}).get("orders", {}).get("edges"):
            first_order_id = orders_result["data"]["orders"]["edges"][0]["node"]["id"]
            print(f"\nFetching details for order {first_order_id}...")
            order_details = client.get_order_details(first_order_id)
            print("\nOrder Details Result:")
            print_json(order_details)
        else:
            print("\nNo unprinted orders found to test order details.")

    except Exception as e:
        print(f"\nError during testing: {str(e)}")


if __name__ == "__main__":
    test_shopify_client()
