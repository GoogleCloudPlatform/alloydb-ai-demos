Hybrid Search
Sample questions:
"Smart casual shirts for men with ratings above 3",
"Grey color apparel for winter with discount more than 20%",
"Find tops for women under Rs.2000",
"Show me ethnic clothing in pink color",
"Looking for winter jackets for women in black color",
"Show me products that are leggings and have a discount greater than 30%",
"Show me black casual shoes for men under ₹2000.",
"I need a summer kurta set for women in blue color.",
"Find sports shoes for men with discount above 40%",
"Looking for sunglasses for women under ₹1500",
"Find me a black rain jacket",
"casual shirt for men in lavender",
"handbags for women in coffee brown color",
"Find handbags for women under ₹2000 with high ratings",
"Show me U.S. Polo Assn. shirts for men"

AI.IF
"Is this product exhibit any major anomalies or irregularities in its attributes or data profile? Note that irregularity also includes rating greater than 5."
'Is the rating unusually low or high for a product?'
"Is the product's usage tag inconsistent with its article type?"

Sample input Payload:

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