**Sample input Payload**:

Vector:

{
  "question": "black shoes",
  "filters": {
        "price": {"min": 3, "max": 50},
        "rating": 2}
}
{
  "question": "watches for casual use for women",
  "filters": {"category": "Accessories",
        "price": {"min": 3, "max": 50},
        "brand": "Being Human",
        "rating": 2
}
}


Hybrid:

{
  "question": "black sports shoes",
  "filters": {
        "category": "Footwear",
        "price": {"min": 3, "max": 50},
        "brand": "Nike",
        "rating": 2
    }
}

NLTOSQL:
{
  "question": "shoes for women with price less than 10$",
  "filters": {
        "category": "Footwear",
        "price": {"min": 3, "max": 10},
        "brand": "Nike",
        "rating": 2
    }
}

AI.IF:

{
  "question": "Show me kurta sets similar to the ethnic summer ones but avoid anything too bright",
  "filters": {
        "category": "Apparel",
        "price": {"min": 3, "max": 50},
        "brand" : "Biba",
        "rating": 2
    }
}
