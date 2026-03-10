--this table hold the data for fahsion beauty products
CREATE SCHEMA IF NOT EXISTS :"schema_name";
CREATE TABLE IF NOT EXISTS :"schema_name".fashion_products(
    id INT PRIMARY KEY,
    gender TEXT,
    masterCategory TEXT,
    subCategory TEXT,
    articleType TEXT,
    baseColour TEXT,
    season TEXT,
    year INT,
    usage TEXT,
    productDisplayName TEXT,
    brand TEXT,
    link TEXT,
    unitPrice NUMERIC(10,2),
    discount INT,
    finalPrice NUMERIC(10,2),
    rating NUMERIC(3,1),
    stockCode VARCHAR(20),
    stockStatus TEXT
);