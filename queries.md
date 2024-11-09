# Query to fetch multiple orders by date range or tag
query GetManyOrders($first: Int!, $query: String) {
  orders(first: $first, query: $query) {
    edges {
      node {
        id
        name
        email
        note
        phone
        createdAt
        displayFulfillmentStatus
        tags
        customer {
          firstName
          lastName
          email
          phone
        }
        shippingAddress {
          address1
          address2
          city
          province
          zip
          country
          name
          phone
        }
        lineItems(first: 50) {
          edges {
            node {
              name
              quantity
              sku
              vendor
              originalUnitPrice {
                amount
              }
              location {
                name
              }
            }
          }
        }
        totalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}

# Query to fetch a single order by ID
query GetOrder($id: ID!) {
  order(id: $id) {
    id
    name
    email
    note
    phone
    createdAt
    displayFulfillmentStatus
    tags
    customer {
      firstName
      lastName
      email
      phone
    }
    shippingAddress {
      address1
      address2
      city
      province
      zip
      country
      name
      phone
    }
    lineItems(first: 50) {
      edges {
        node {
          name
          quantity
          sku
          vendor
          originalUnitPrice {
            amount
          }
          location {
            name
          }
        }
      }
    }
    totalPriceSet {
      shopMoney {
        amount
        currencyCode
      }
    }
  }
}

# Query to get inventory levels for a variant across all locations
query GetInventoryLevelsByVariant($variantId: ID!) {
  productVariant(id: $variantId) {
    id
    title
    sku
    inventoryQuantity
    barcode
    displayName
    image {
      url
      altText
    }
    inventoryItem {
      id
      tracked
      inventoryLevels(first: 10) {
        edges {
          node {
            available
            location {
              id
              name
              active
              address {
                address1
                address2
                city
                province
                zip
                country
              }
            }
            quantities(names: ["available", "committed", "incoming"]) {
              name
              quantity
            }
          }
        }
      }
    }
    product {
      title
      vendor
    }
  }
}

# Mutation to add "printed" tag to an order
mutation AddPrintedTag($id: ID!) {
  tagsAdd(
    id: $id
    tags: ["printed"]
  ) {
    node {
      id
      tags
    }
    userErrors {
      field
      message
    }
  }
}