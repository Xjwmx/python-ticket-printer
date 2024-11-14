# src/services/shopify_client.py

import logging
from typing import Dict, Optional, Any
import shopify
import os
from dotenv import load_dotenv
import json

# Set up logging
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Environment variables
API_VERSION = os.getenv("API_VERSION")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SHOP_URL = os.getenv("SHOP_URL")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")


class ShopifyError(Exception):
    """Base exception for Shopify client errors"""

    pass


class ShopifyClient:
    def __init__(
        self, shop_url: Optional[str] = None, access_token: Optional[str] = None
    ):
        """
        Initialize Shopify client with shop credentials. If not provided, uses environment variables.

        Args:
            shop_url: Your shop's .myshopify.com URL
            access_token: Private app access token

        Raises:
            ShopifyError: If credentials are not provided and not found in environment
        """
        self.shop_url = shop_url or SHOP_URL
        self.access_token = access_token or ACCESS_TOKEN

        if not self.shop_url or not self.access_token:
            raise ShopifyError(
                "Missing Shopify credentials. Provide them directly or via environment variables."
            )

        self._initialize_session()

    def _initialize_session(self) -> None:
        """
        Initialize the Shopify session

        Raises:
            ShopifyError: If session initialization fails
        """
        try:
            shopify.Session.setup(api_key=self.access_token, secret=None)
            session = shopify.Session(self.shop_url, API_VERSION, self.access_token)
            shopify.ShopifyResource.activate_session(session)
        except Exception as e:
            raise ShopifyError(f"Failed to initialize Shopify session: {str(e)}")

    def get_unprinted_orders(self, limit: int = 200) -> Dict[str, Any]:
        """
        Fetch unprinted orders using GraphQL query

        Args:
            limit: Maximum number of orders to fetch

        Returns:
            Dict containing order data and pagination info

        Raises:
            ShopifyError: If the query fails
        """
        try:
            client = shopify.GraphQL()
            query = """
            query GetManyOrders($first: Int!, $query: String) {
              orders(first: $first, query: $query, sortKey: CREATED_AT, reverse: true) {
                edges {
                  node {
                    id
                    createdAt
                    tags
                    totalPriceSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                    shippingAddress {
                      city
                      province
                      name
                    }
                    name
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """
            variables = {"first": limit, "query": "tag_not:printed AND status:open"}
            result = client.execute(query, variables)
            result_dict = json.loads(result)  # Parse the JSON string into a dictionary
            if "errors" in result_dict:
                raise ShopifyError(f"GraphQL query failed: {result_dict['errors']}")
            return result_dict
        except Exception as e:
            raise ShopifyError(f"Failed to fetch unprinted orders: {str(e)}")

    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Fetch detailed information for a single order using GraphQL"""
        try:
            client = shopify.GraphQL()
            query = """
            query GetOrder($id: ID!) {
              order(id: $id) {
                id
                name
                createdAt
                tags
                note
                displayFinancialStatus
                displayFulfillmentStatus
                email
                phone
                totalPriceSet {
                  shopMoney {
                    amount
                    currencyCode
                  }
                }
                shippingAddress {
                  firstName
                  lastName
                  address1
                  address2
                  city
                  province
                  zip
                  country
                  phone
                }
                lineItems(first: 50) {
                  edges {
                    node {
                      quantity
                      sku
                      vendor
                      product {
                        title
                      }
                      variant {
                        title
                        image {
                          url
                        }
                        inventoryItem {
                          inventoryLevels(first: 100) {
                            edges {
                              node {
                                location {
                                  name
                                }
                                quantities(names: ["available"]) {
                                  name
                                  quantity
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
                shippingLines(first: 1) {
                  edges {
                    node {
                      title
                      code
                    }
                  }
                }
              }
            }
            """
            variables = {"id": order_id}
            result = client.execute(query, variables)
            result_dict = json.loads(result)
            if "errors" in result_dict:
                raise ShopifyError(f"GraphQL query failed: {result_dict['errors']}")
            return result_dict
        except Exception as e:
            raise ShopifyError(f"Failed to fetch order details: {str(e)}")


def create_client() -> ShopifyClient:
    """
    Factory function to create a ShopifyClient instance using environment variables

    Returns:
        ShopifyClient instance

    Raises:
        ShopifyError: If required environment variables are missing
    """
    return ShopifyClient()
