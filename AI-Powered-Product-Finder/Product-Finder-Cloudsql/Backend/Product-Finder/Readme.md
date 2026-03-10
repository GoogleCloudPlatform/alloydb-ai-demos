Sample input Payload:

Vector:
daily wear for women for winter
comfortable wear for ladies
Floral pattern tops
moisturising makeup products
Black formal shoes for men

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

striped polo t-shirts
Nike Air Max sports shoes and t-shirts to go with it
shoes similiar to Nike air max and in white

{
  "question": "black sports shoes",
  "filters": {
        "category": "Footwear",
        "price": {"min": 3, "max": 50},
        "brand": "Nike",
        "rating": 2
    }
}