# GetManyOrders

### Query

```GraphQL
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
```

### Variable Example

```JSON
{
  "first": 200,
  "query": "tag_not:printed AND status:open"
}
```



# GetOrder

### Query

```GraphQL
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
    billingAddressMatchesShippingAddress
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
    billingAddress {
      firstName
      lastName
      name
      company
      address1
      address2
      city
      province
      provinceCode
      country
      zip
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
    fulfillmentOrders(first: 5) {
      edges {
        node {
          deliveryMethod {
            methodType
            presentedName
            brandedPromise {
              handle
              name
            }
            additionalInformation {
              instructions
              phone
            }
          }
        }
      }
    }
  }
}

```

### Variable Example

```JSON
{
  "id": "gid://shopify/Order/5605132632241"
}

```
