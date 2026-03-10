ALTER TABLE fashion_products
ADD COLUMN combined_description TEXT, 
ADD COLUMN combined_description_embedding VECTOR(768) using varbinary;

UPDATE fashion_products
SET combined_description = CONCAT(
    'Product ID is ', id,
    ', Product targeted to ', gender,
    ', Primary or master category is ', masterCategory,
    ', Secondary or sub-category is ', subCategory,
    ', Type of product is ', articleType,
    ', Descriptive color name or Base colour is ', baseColour,
    ', Fashion season this product is targeted to is ', season,
    ', Fashion year this product is from is ', year,
    ', This product meant to be used as  OR usage type is ', `usage`,
    ', Product name including the brand as the first word is ', productDisplayName,
    ', Brand name is ', brand,
    ', Unit price is ', unitPrice,
    ', Discount applied is ', discount,
    ', Final price or the actual price of the product is ', finalPrice,
    ', Customer rating is ', rating,
    ', Stock code or stock id is ', stockCode,
    ', and Stock status is ', stockStatus, '.'
);


UPDATE fashion_products
SET combined_description_embedding = mysql.ml_embedding('text-embedding-005', combined_description); 

CREATE VECTOR INDEX complaint_embed_idx ON fashion_products(combined_description_embedding)  USING SCANN DISTANCE_MEASURE=COSINE;