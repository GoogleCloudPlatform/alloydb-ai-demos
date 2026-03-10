# AI‑Powered Product Finder in AlloyDB
## Data Preprocessing 

## Purpose of This Script
This script prepares product data for the AI-powered Product Finder Demo Application in AlloyDB.

- Loads styles.csv and images.csv from Google Cloud Storage (GCS)
- Cleans the raw dataset
- Merges styles with image URLs using product id
- Filters invalid image links
- Performs balanced sampling (default: 2000 rows)
- Enriches data with price, discount, rating, stock info(stock id and stock status), brand name
- Outputs the final dataset as fashion_products.csv

## Input Files (Required)
- gs://<SCHEMA_NAME>/<BUCKET_NAME>/styles.csv
- gs://<SCHEMA_NAME>/<BUCKET_NAME>/images.csv

## Output Files
- fashion_products.csv

## Prerequisites
- Python 3.10+
- Install required packages (pandas, numpy, gcfs- if already installed, Skip this step):
```
pip install -r requirements.txt
```
- Authenticate to GCP:
```
gcloud auth application-default login
```

## Running the Script
```
python -m preprocessing
```
