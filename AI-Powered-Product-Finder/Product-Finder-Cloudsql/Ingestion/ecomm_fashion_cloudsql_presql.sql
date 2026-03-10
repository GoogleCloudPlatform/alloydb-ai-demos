-- Enable vector operations and similarity search
CREATE EXTENSION IF NOT EXISTS vector CASCADE;

-- CREATE A NEW COLUMN WITH COMBINED DESCRIPTION & EMBEDDINGS FOR COMBINED DATA ---


ALTER TABLE :"schema".fashion_products 
ADD COLUMN combined_description TEXT, 
ADD COLUMN combined_description_embedding VECTOR(768); 


-- USED https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset AS REFERENCE TO ADD DESCRIPTION OF EACH FIELD ---
UPDATE :"schema".fashion_products
SET combined_description = CONCAT(
    'Product ID is ', id,
    ', Product targeted to ', gender,
    ', Primary or master category is ', masterCategory,
    ', Secondary or sub-category is ', subCategory,
    ', Type of product is ', articleType,
    ', Descriptive color name or Base colour is ', baseColour,
    ', Fashion season this product is targeted to is ', season,
    ', Fashion year this product is from is ', year,
    ', This product meant to be used as  OR usage type is ', usage,
    ', Product name including the brand as the first word is ', productDisplayName,
    ', Brand name is ', brand,
    ', Unit price is ', unitPrice,
    ', Discount applied is ', discount,
    ', Final price or the actual price of the product is ', finalPrice,
    ', Customer rating is ', rating,
    ', Stock code or stock id is ', stockCode,
    ', and Stock status is ', stockStatus, '.'
);

-- EMBEDDINGS CREATED USING text-embedding-005 ---
UPDATE :"schema".fashion_products
SET combined_description_embedding = google_ml.embedding('text-embedding-005', combined_description) 
WHERE combined_description IS NOT NULL;

-- CREATE INDICES ---
-- GIN INDEX FOR TEXT SEARCH
CREATE INDEX ON :"schema".fashion_products USING gin(to_tsvector('english', combined_description));
-- HNSW ANN index creation (using cosine distance):
CREATE INDEX fashionprod_embedding_hnsw_idx
ON :"schema".fashion_products
USING hnsw (combined_description_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

ANALYZE :"schema".fashion_products;