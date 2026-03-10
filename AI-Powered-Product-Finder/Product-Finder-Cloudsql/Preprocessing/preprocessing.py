
"""
Source: https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset 
Fashion product preprocessing:
- Load styles & images from GCS
- Clean, merge, derive brand from productDisplayName
- Balanced sampling by masterCategory (target total = 2000)
- Add synthetic price, discount, rating, stock columns
- Save final dataset
"""

# ---------------------------
# Imports 
# ---------------------------
import os
import re
import random
import string
import logging
import config
from typing import List, Optional
from config import RANDOM_SEED, TARGET_SAMPLE_SIZE, GCS_STYLES_PATH, GCS_IMAGES_PATH, LOCAL_OUTPUT_CSV, GCS_OUTPUT_PATH

import numpy as np
import pandas as pd

# ---------------------------
# Utilities
# ---------------------------
def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize column names to camelCase expected by the pipeline.
    Handles common variants found in public fashion datasets.
    """
    rename_map = {
        # casing / underscore variants
        "mastercategory": "masterCategory",
        "subcategory": "subCategory",
        "articletype": "articleType",
        "basecolour": "baseColour",
        "productdisplayname": "productDisplayName",
        "unitprice": "unitPrice",
        "finalprice": "finalPrice",
        "stockcode": "stockCode",
        "stockstatus": "stockStatus",
        "combined_description": "combined_description",
        "image": "link",
        "image_url": "link",
        "imageurl": "link",
        # sometimes 'brandname'
        "brandname": "brand",
    }
    # canonicalize first (strip, lower, remove spaces/underscores)
    canonical = {c: re.sub(r"[ _]+", "", c.strip().lower()) for c in df.columns}
    inv = {v: k for k, v in canonical.items()}
    # build final renames
    final_map = {}
    for raw_col in df.columns:
        canon = canonical[raw_col]
        if canon in rename_map:
            final_map[raw_col] = rename_map[canon]
        else:
            # attempt partial matches for common fields
            if canon == "id":
                final_map[raw_col] = "id"
            elif canon == "gender":
                final_map[raw_col] = "gender"
            elif canon == "season":
                final_map[raw_col] = "season"
            elif canon == "year":
                final_map[raw_col] = "year"
            elif canon == "usage":
                final_map[raw_col] = "usage"
            elif canon == "brand":
                final_map[raw_col] = "brand"
            elif canon == "link":
                final_map[raw_col] = "link"
            else:
                # keep original if no mapping
                final_map[raw_col] = raw_col
    return df.rename(columns=final_map)


def clean_images_df(images_df: pd.DataFrame) -> pd.DataFrame:
    """
    - Ensure 'id' exists by extracting digits from filename (robust to extension)
    - Filter out rows where 'link' is null/empty/'undefined'
    """
    if "id" not in images_df.columns:
        if "filename" not in images_df.columns:
            raise KeyError("images.csv must contain 'id' or 'filename' column.")
        # Extract first numeric group from filename, e.g. '12345.jpg' -> 12345
        images_df["id"] = images_df["filename"].astype(str).str.extract(r"(\d+)").astype(int)

    # from link drop nulls, undefined and empty strings, case-insensitively)
    if "link" not in images_df.columns:
        raise KeyError("images.csv must contain a 'link' (image URL) column.")

    images_df["link"] = images_df["link"].astype(str)
    mask_valid_link = (
        images_df["link"].notna()   # keep rows where link is not NaN
        & images_df["link"].str.strip().ne("")    # keep rows where link is not empty string
        & images_df["link"].str.strip().str.lower().ne("undefined")   # keep rows where link is not "undefined"
        & images_df["link"].str.contains(r"https?://", case=False, na=False)    # keep rows where link is a URL
    )
    images_df = images_df.loc[mask_valid_link, ["id", "link"]].drop_duplicates("id")

    return images_df


# ---------------------------
# Brand inference
# ---------------------------
AUDIENCE_TOKENS = [
    "Men", "Women", "Girls", "Boys", "Unisex", "Kids", "Adults", "Adult", "Kid"
]

FALLBACK_BRANDS: List[str] = [
    # Common multi-word brands observed in retail datasets
    "United Colors Of Benetton",
    "Undercolors of Benetton",
    "2go Active Gear USA",
    "SDL by Sweet Dreams",
    "Gini and Jony",
    "Scullers For Her",
    "Classic Polo",
    "American Tourister",
    "Global Desi",
    "Warner Bros",
    "Biba Outlet",
    "Jockey Modern Classic",
    "Jockey COMFORT PLUS",
    "Jockey SPORT",
    "Jockey GOLDEDN",
    "Chromozome",
    "Timberland",
    "United Colors of Benetton",  # case variant
    "Myntra",
    "Hanes",
    "Nike",
    "Fila",
    "Clarks",
    "Wrangler",
    "Spykar",
    "SPYKAR",
    "Proline",
    "Basics",
    "Marvel Comics",
    "Mickey",
    "Disney",
    "Femella",
    "Vishudh",
    "Beyouty",
    "Shree",
    "109F",
    "Asics",
    "Mark Taylor",
    "Indigo Nation",
    "Jealous 21",
    "Garfield",
    "AyAany",  # typos sometimes appear
    "Ayaany",
    "Xoxo",
    "Doodle",
    "Pink Floyd",
    "Gini & Jony",  # alt name for Gini and Jony
    "UCB"  # alt name for United Colors of Benetton
]

def build_brand_regex(known_brands: List[str]) -> re.Pattern:
    """
    Build a regex that matches any known brand at the beginning of the productDisplayName.
    Sort by length (desc) to prefer longest multi-word matches.
    """
    cleaned = sorted({b.strip() for b in known_brands if isinstance(b, str) and b.strip()}, key=len, reverse=True)
    # Escape regex meta chars and allow flexible spacing/casing
    parts = [re.sub(r"\s+", r"\\s+", re.escape(b)) for b in cleaned]
    if not parts:
        # match nothing
        return re.compile(r"^\b$a", re.I)
    pattern = r"^(?P<brand>(" + "|".join(parts) + r"))\b"
    return re.compile(pattern, flags=re.IGNORECASE)


def infer_brand_from_product_name(name: str, brand_start_regex: re.Pattern) -> Optional[str]:
    """
    Try to infer brand from productDisplayName:
    1) Use known brand regex at the start
    2) Else extract leading tokens up to first audience word (Men|Women|Kids|...)
       and normalize casing.
    """
    if not isinstance(name, str) or not name.strip():
        return None

    # 1) Try known brands at the start
    m = brand_start_regex.search(name.strip())
    if m:
        # Preserve original casing as matched
        return m.group("brand").strip()

    # 2) Fallback: take leading tokens until audience term appears
    tokens = name.strip().split()
    collected: List[str] = []
    for tok in tokens:
        # stop if we hit an audience marker (case-insensitive)
        if tok.capitalize() in AUDIENCE_TOKENS:
            break
        collected.append(tok)
        # heuristic: limit runaway long prefixes
        if len(collected) >= 6:
            break

    brand_guess = " ".join(collected).strip(",&-/")
    # Reasonable guard: require at least 2 characters
    return brand_guess if len(brand_guess) >= 2 else None


def add_brand_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create/repair 'brand' from 'productDisplayName' when missing or empty.
    Uses known brand list from the dataset if available; otherwise falls back
    to a curated list + audience-based prefix heuristic.
    """
    if "productDisplayName" not in df.columns:
        raise KeyError("Expected 'productDisplayName' column to infer brand.")

    # Build known brand lexicon from existing data if present
    known = []
    if "brand" in df.columns:
        known = df["brand"].dropna().astype(str).str.strip().tolist()

    # merge with fallbacks and deduplicate
    lexicon = list(set(known + FALLBACK_BRANDS))
    brand_regex = build_brand_regex(lexicon)

    # compute inferred brand
    inferred = df["productDisplayName"].apply(lambda s: infer_brand_from_product_name(s, brand_regex))

    # Create/patch brand
    if "brand" not in df.columns:
        df["brand"] = inferred
    else:
        # fill where current brand is null/empty
        is_missing = df["brand"].isna() | (df["brand"].astype(str).str.strip() == "")
        df.loc[is_missing, "brand"] = inferred.loc[is_missing]

    # Final cleanup: strip
    df["brand"] = df["brand"].astype(str).str.strip().replace({"None": np.nan})
    return df


# ---------------------------
# Main pipeline
# ---------------------------
def main() -> None:
    setup_logging()
    np.random.seed(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    logging.info("Reading styles.csv from GCS...")
    styles_df = pd.read_csv(GCS_STYLES_PATH, on_bad_lines="skip")
    styles_df = standardize_column_names(styles_df)

    logging.info("Reading images.csv from GCS...")
    images_df = pd.read_csv(GCS_IMAGES_PATH, on_bad_lines="skip")
    images_df = standardize_column_names(images_df)
    images_df = clean_images_df(images_df)

    # Ensure id is int
    if "id" not in styles_df.columns:
        raise KeyError("styles.csv must contain 'id' column.")
    styles_df["id"] = pd.to_numeric(styles_df["id"], errors="coerce").astype("Int64")
    styles_df = styles_df.dropna(subset=["id"]).copy()
    styles_df["id"] = styles_df["id"].astype(int)

    logging.info("Merging styles and images on 'id'...")
    merged_df = pd.merge(styles_df, images_df, on="id", how="inner")

    # Keep a working df
    df = merged_df.copy()

    # Required columns to proceed
    required_cols = ["masterCategory", "productDisplayName", "usage", "baseColour"]
    # If your source has lower-case variants, standardize_column_names() should have fixed them.
    present_required = [c for c in required_cols if c in df.columns]
    if len(present_required) != len(required_cols):
        missing = set(required_cols) - set(present_required)
        raise KeyError(f"Missing required columns after normalization: {missing}")

    # Drop rows with missing key fields
    before = len(df)
    df = df.dropna(subset=required_cols)
    logging.info("Dropped %d rows with missing required fields.", before - len(df))

    # ---------------------------
    # Brand creation/repair
    # ---------------------------
    logging.info("Inferring 'brand' from 'productDisplayName' where needed...")
    df = add_brand_column(df)

    # ---------------------------
    # Balanced sampling by masterCategory with length bias
    # ---------------------------
    logging.info("Preparing balanced sampling (target=%d)...", TARGET_SAMPLE_SIZE)
    df["desc_length"] = df["productDisplayName"].astype(str).str.len()
    categories = df["masterCategory"].dropna().unique()

    if len(categories) == 0:
        logging.warning("No categories found; skipping category-balanced sampling.")
        sampled_df = df.copy()
    else:
        samples_per_category = max(TARGET_SAMPLE_SIZE // len(categories), 0)

        sampled_parts = []
        for cat in categories:
            cat_df = df.loc[df["masterCategory"] == cat].sort_values("desc_length", ascending=False)
            take_n = min(samples_per_category, len(cat_df)) if samples_per_category > 0 else 0
            sampled_parts.append(cat_df.head(take_n))

        sampled_df = pd.concat(sampled_parts, axis=0) if sampled_parts else df.head(0)

        # Fill remainder with globally longest descriptions
        if len(sampled_df) < TARGET_SAMPLE_SIZE:
            remaining_needed = TARGET_SAMPLE_SIZE - len(sampled_df)
            remainder_pool = df.drop(index=sampled_df.index, errors="ignore").sort_values("desc_length", ascending=False)
            sampled_df = pd.concat([sampled_df, remainder_pool.head(max(remaining_needed, 0))], axis=0)

        # If too many categories made per-category=0, ensure we still get a sample
        if len(sampled_df) == 0:
            sampled_df = df.sort_values("desc_length", ascending=False).head(TARGET_SAMPLE_SIZE)

    # Cleanup helper
    if "desc_length" in sampled_df.columns:
        sampled_df = sampled_df.drop(columns=["desc_length"])

    # ---------------------------
    # Synthetic attributes
    # ---------------------------
    logging.info("Adding synthetic price/discount/rating and stock columns...")
    n = len(sampled_df)
    # unitPrice: uniform integers [3, 50) then to float with 2 decimals
    sampled_df["unitPrice"] = np.round(np.random.randint(3, 50, size=n).astype(float), 2)
    sampled_df["discount"] = np.random.randint(5, 51, size=n)  # 5..50
    sampled_df["finalPrice"] = np.round(sampled_df["unitPrice"] * (1 - sampled_df["discount"] / 100.0), 2)
    sampled_df["rating"] = np.round(np.random.uniform(1.0, 5.0, size=n), 1)

    # Stock code (alphanumeric) like "<id><AAA>"
    def gen_stock_code(row) -> str:
        return f"{int(row['id'])}{''.join(random.choices(string.ascii_uppercase, k=3))}"
    sampled_df["stockCode"] = sampled_df.apply(gen_stock_code, axis=1)

    # 80/20 availability split
    sampled_df["stockStatus"] = np.random.choice(["In Stock", "Out of Stock"], size=n, p=[0.8, 0.2])

    # ---------------------------
    # Save outputs
    # ---------------------------
    logging.info("Writing local CSV: %s", LOCAL_OUTPUT_CSV)
    sampled_df.to_csv(LOCAL_OUTPUT_CSV, index=False)

    if GCS_OUTPUT_PATH:
        logging.info("Writing to GCS: %s", GCS_OUTPUT_PATH)
        sampled_df.to_csv(GCS_OUTPUT_PATH, index=False)

    logging.info("Done. Final shape: %s", sampled_df.shape)


# ---------------------------
# Entrypoint
# ---------------------------
if __name__ == "__main__":
    main()
