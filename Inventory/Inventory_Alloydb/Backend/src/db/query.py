import pandas as pd
from sqlalchemy import text
import base64

from src.utils.logger import logger
from src.utils.config import ALLOYDB_TABLESCHEMA


async def inventory_overview(engine):
    """
    Produces a store–SKU inventory overview DataFrame enriched with a status
    classification and base64-encoded image data.

    Workflow:
        1) Query stock levels joined with products and stores.
        2) Attach the most recent product image (per SKU) or a default image via
           LATERAL joins.
        3) Classify inventory status per row (Critical/Low/Optimal/Over).
        4) Base64-encode binary image payloads for downstream UI/JSON transport.

    Args:
        engine: SQLAlchemy engine used to execute the inventory query.

    Returns:
        pandas.DataFrame | str:
            - A DataFrame with columns:
              [product_name, image_data, sku, category, location, store_id,
               on_hand, in_transit, safety_stock, reorder_point, image_url, Status]
              where `image_data` is base64-encoded and `Status` is a string label.
            - On error, returns a string describing the failure.
    """
    # -------------------------------------------------------------------------
    # 1. Fetch data from the database by joining stock, product, and store tables.
    #    LATERAL joins:
    #      - `pi`: most recent product-specific image for the SKU.
    #      - `dpi`: default image (prefers is_default=TRUE) when SKU image missing.
    # -------------------------------------------------------------------------
    try:
        inventory_query = text(
            f"""
        SELECT
            p.title AS product_name,
            COALESCE(pi.image_data, dpi.image_data) AS image_data,
            p.sku,
            p.category,
            s.name AS location,
            s.store_id AS store_id,
            sl.on_hand,
            sl.in_transit,
            sl.safety_stock,
            sl.reorder_point,
            COALESCE(pi.image_url, dpi.image_url) AS image_url
        FROM {ALLOYDB_TABLESCHEMA}.stock_levels sl
        JOIN {ALLOYDB_TABLESCHEMA}.products p ON sl.sku = p.sku
        JOIN {ALLOYDB_TABLESCHEMA}.stores s   ON sl.store_id = s.store_id

        -- Per-product image: take the most recent mapping for this SKU
        LEFT JOIN LATERAL (
            SELECT image_url, image_data
            FROM {ALLOYDB_TABLESCHEMA}.product_images
            WHERE sku = p.sku
            ORDER BY created_at DESC
            LIMIT 1
        ) pi ON TRUE

        -- Default image: prefer is_default = TRUE; else fall back to a "default" SKU
        LEFT JOIN LATERAL (
            SELECT image_url, image_data
            FROM {ALLOYDB_TABLESCHEMA}.product_images
            WHERE is_default = TRUE
            ORDER BY is_default DESC, created_at DESC
            LIMIT 1
        ) dpi ON TRUE
        """
        )

        inventory_df = []

        # Execute the query and convert results into a DataFrame.
        try:
            with engine.connect() as connection:
                results = connection.execute(inventory_query).fetchall()
                if not results:

                    # Return an empty DataFrame to avoid downstream errors
                    logger.info("No results found")
                    return pd.DataFrame()
                else:
                    inventory_df = pd.DataFrame(results)
                    logger.info("Results generated for inventory overview")

        except Exception as e:
            print("Exception occured!!", e)

        # ---------------------------------------------------------------------
        # Status classifier:
        #   - Critical Stock: on_hand < safety_stock
        #   - Low Stock:      on_hand < reorder_point
        #   - Over Stock:     on_hand > 2 * reorder_point
        #   - Optimal Stock:  otherwise
        # ---------------------------------------------------------------------
        def classify(row):
            if row["on_hand"] < row["safety_stock"]:
                return "Critical Stock"
            elif row["on_hand"] < row["reorder_point"]:
                return "Low Stock"
            elif row["on_hand"] > 2 * row["reorder_point"]:
                return "Over Stock"
            else:
                return "Optimal Stock"

        # Apply status when data exists; otherwise create an empty Status column.
        if not inventory_df.empty:
            inventory_df["Status"] = inventory_df.apply(classify, axis=1)
        else:
            # ensure status column exists even for empty dataframe
            inventory_df["Status"] = pd.Series(dtype="str")

        # ---------------------------------------------------------------------
        # Encode binary image payloads to base64 for safe JSON transport.
        # (Assumes `image_data` is bytes-like; downstream UI can decode it.)
        # ---------------------------------------------------------------------
        inventory_df["image_data"] = inventory_df["image_data"].apply(
            lambda x: base64.b64encode(x).decode("utf-8")
        )
        return inventory_df
    except Exception as e:
        logger.error("Error occured in inventory overview :", e)
        return f"Failed to get inventory overview: {e}"


async def recent_purchase_order(engine):
    """
    Retrieves the 50 most recently created purchase orders with supplier names,
    statuses, totals, and timestamps.

    Args:
        engine: SQLAlchemy engine used to execute the query.

    Returns:
        pandas.DataFrame | list:
            - A DataFrame containing columns:
              [po_id, supplier, status, total_amount, expected_at, created_at].
            - An empty list `[]` when no results are found (preserves original behavior).
    """
    # -------------------------------------------------------------------------
    # Query top 50 recent POs ordered by creation time (descending).
    # -------------------------------------------------------------------------
    po_query = text(
        f"""
        SELECT po.po_id, s.name AS supplier, po.status, po.total_amount, po.expected_at, po.created_at
        FROM {ALLOYDB_TABLESCHEMA}.purchase_orders po
        JOIN {ALLOYDB_TABLESCHEMA}.suppliers s ON po.supplier_id = s.supplier_id
        ORDER BY po.created_at DESC
        LIMIT 50
    """
    )

    po_df = []
    with engine.connect() as connection:
        results = connection.execute(po_query).fetchall()

        # Preserve original sentinel behavior: return [] if no rows found.
        if not results:
            return []
        else:
            po_df = pd.DataFrame(results)
            return po_df


async def add_product(
    engine,
    sku,
    name,
    category,
    store_id,
    on_hand,
    safety_stock,
    reorder_point,
    in_transit,
    location,
):
    """
    Adds a new product (if not existing) and upserts stock levels for a store–SKU.

    Workflow:
        1) Attempt to insert into `{ALLOYDB_TABLESCHEMA}.products` with an image payload:
           - Prefer product-specific image for the SKU.
           - Fall back to 'DEFAULT' image when missing.
           - Do nothing on conflict (SKU already exists).
        2) Upsert into `{ALLOYDB_TABLESCHEMA}.stock_levels` for the provided store:
           - Insert or update on_hand, in_transit, safety_stock, reorder_point.
        3) Commit changes and return a success message.

    Args:
        engine: SQLAlchemy engine used to execute DB operations.
        sku: SKU identifier string.
        name: Product display/title.
        category: Product category label.
        store_id: Store identifier (int or str as provided upstream).
        on_hand: Current stock on hand (numeric/coercible).
        safety_stock: Desired buffer stock (numeric/coercible).
        reorder_point: Trigger level for replenishment (numeric/coercible).
        in_transit: Quantity currently in transit (numeric/coercible).
        location: Store location (not persisted here; present for upstream context).

    Returns:
        str | Dict[str, str]:
            - Success string when insert/upsert succeeds.
            - Error dictionary when SKU duplication is detected or any failure occurs.
    """
    try:
        with engine.connect() as connection:
            # -----------------------------------------------------------------
            # Insert into products table; `ON CONFLICT (sku) DO NOTHING` ensures
            # idempotency for product creation attempts.
            # Image selection:
            #   - First try product_images for the specific SKU.
            #   - Then fall back to the 'DEFAULT' image.
            # -----------------------------------------------------------------
            result = connection.execute(
                text(
                    f"""
                    INSERT INTO {ALLOYDB_TABLESCHEMA}.products (sku, title, category, image_data)
                    VALUES (:sku, :title, :category,
                        (
                            SELECT image_data
                            FROM {ALLOYDB_TABLESCHEMA}.product_images
                            WHERE sku = :sku
                            UNION ALL
                            SELECT image_data
                            FROM {ALLOYDB_TABLESCHEMA}.product_images
                            WHERE sku = 'DEFAULT'
                            LIMIT 1
                        )
                    )
                    ON CONFLICT (sku) DO NOTHING;
                """
                ),
                {"sku": sku, "title": name.strip(), "category": category.strip()},
            )

            if result.rowcount == 0:
                # Product already exists -> warn user; don't modify product fields
                logger.info(
                    f"⚠️ Duplicate detected: Product with SKU '{sku}' already exists. "
                    "No changes were made to the existing product."
                )
                logger.info(f"Duplicate SKU '{sku}' detected. Skipping product insert.")
                return {"error": f"Duplicate detected for the sku {sku}"}
            else:
                logger.info(
                    f"Data inserted into table {ALLOYDB_TABLESCHEMA}.products!!"
                )

            # -----------------------------------------------------------------
            # Upsert stock levels regardless of product insert outcome.
            #   - Update on_hand, in_transit, safety_stock, reorder_point.
            #   - Composite key (sku, store_id) drives conflict resolution.
            # -----------------------------------------------------------------
            connection.execute(
                text(
                    f"""
                    INSERT INTO {ALLOYDB_TABLESCHEMA}.stock_levels (sku, store_id, on_hand, in_transit, safety_stock, reorder_point)
                    VALUES (:sku, :store_id, :on_hand, :in_transit, :safety_stock, :reorder_point)
                    ON CONFLICT (sku, store_id) DO UPDATE SET
                        on_hand = EXCLUDED.on_hand,
                        in_transit = EXCLUDED.in_transit,
                        safety_stock = EXCLUDED.safety_stock,
                        reorder_point = EXCLUDED.reorder_point
                """
                ),
                {
                    "sku": sku,
                    "store_id": store_id,
                    "on_hand": on_hand,
                    "in_transit": in_transit,
                    "safety_stock": safety_stock,
                    "reorder_point": reorder_point,
                },
            )
            logger.info(
                f"Data inserted/updated in table {ALLOYDB_TABLESCHEMA}.stock_levels!!"
            )

            # Persist both product insert and stock upsert.
            connection.commit()
            return "Product added/updated successfully!!"
    except Exception as e:
        logger.error(f"Failed to add product:{e}")
        return f"Failed to add product: {e}"


async def edit_product(
    engine,
    sku,
    name,
    category,
    store_id,
    on_hand,
    safety_stock,
    reorder_point,
    in_transit,
    location,
):
    """
    Edits stock-level details for a given SKU (and optionally store_id), applying
    partial updates via COALESCE to preserve existing values when inputs are None.

    Args:
        engine: SQLAlchemy engine used for the update.
        sku: Product SKU to update.
        name: (Unused here) product title; retained for API consistency.
        category: (Unused here) product category; retained for API consistency.
        store_id: Store identifier; required to target stock records.
        on_hand: Optional new on-hand stock (None retains existing value).
        safety_stock: Optional new safety stock (None retains existing value).
        reorder_point: Optional new reorder point (None retains existing value).
        in_transit: Optional new in-transit quantity (None retains existing value).
        location: (Unused here) store location; retained for API consistency.

    Returns:
        str: Success message, or a failure message if the SKU has no stock record.
    """
    try:
        with engine.begin() as connection:
            # ✅ Update stock levels if details provided
            if store_id and any(
                v is not None
                for v in [on_hand, in_transit, safety_stock, reorder_point]
            ):
                stock_result = connection.execute(
                    text(
                        f"""
                    UPDATE {ALLOYDB_TABLESCHEMA}.stock_levels
                    SET on_hand = COALESCE(:on_hand, on_hand),
                        in_transit = COALESCE(:in_transit, in_transit),
                        safety_stock = COALESCE(:safety_stock, safety_stock),
                        reorder_point = COALESCE(:reorder_point, reorder_point),
                        store_id = COALESCE(:store_id,store_id)
                    WHERE sku = :sku
                """
                    ),
                    {
                        "on_hand": on_hand,
                        "in_transit": in_transit,
                        "safety_stock": safety_stock,
                        "reorder_point": reorder_point,
                        "sku": sku,
                        "store_id": store_id,
                    },
                )
            if stock_result.rowcount == 0:
                # No stock row matched the SKU; signal failure.
                logger.error(
                    f"Failed to update {ALLOYDB_TABLESCHEMA}.stock_levels. No stock record found for SKU {sku}"
                )
                return f"Failed to update {ALLOYDB_TABLESCHEMA}.stock_levels. No stock record found for SKU {sku}"

            logger.info(f"Data updated to {ALLOYDB_TABLESCHEMA}.stock_levels")
            return f"✅ Product {sku} and related details updated successfully!"

    except Exception as e:
        logger.error(f"Failed to update the product details:{e}")
        return f"❌ Failed to update product: {e}"


async def edit_purchase_order_recommedation(
    engine, po_id, sku, new_supplier_id, new_quantity
):
    """
    Edits a purchase order recommendation by:
        - Changing the supplier linked to the PO.
        - Updating the product–supplier mapping for the SKU.
        - Adjusting the quantity on the PO line.
        - Recalculating the PO total_amount.

    Args:
        engine: SQLAlchemy engine used for transactional updates.
        po_id: Purchase order identifier to modify.
        sku: SKU for which the supplier/quantity is being updated.
        new_supplier_id: The supplier_id to assign to the PO and product mapping.
        new_quantity: The new quantity to set for the SKU on the PO line.

    Returns:
        Dict[str, Any]: A success payload with `status` and `po_id`,
        or an error dictionary containing a message on failure.
    """
    try:
        with engine.begin() as connection:
            # trans = connection.begin()
            # result = connection.execute(
            #     text(f"SELECT supplier_id, name FROM {ALLOYDB_TABLESCHEMA}.suppliers ORDER BY name")
            # )
            # suppliers = result.fetchall()
            # supplier_options = {name: sid for sid, name in suppliers}

            # Update PO to reflect new supplier and set status to approved.
            connection.execute(
                text(
                    f"""
                UPDATE {ALLOYDB_TABLESCHEMA}.purchase_orders
                SET supplier_id = :new_supplier_id, status = 'approved'
                WHERE po_id = :po_id
            """
                ),
                {"new_supplier_id": new_supplier_id, "po_id": po_id},
            )
            logger.info(f"Data updated to {ALLOYDB_TABLESCHEMA}.purchase_orders")

            # Update product-supplier mapping for the SKU.
            connection.execute(
                text(
                    f"""
                    UPDATE {ALLOYDB_TABLESCHEMA}.product_suppliers
                    SET supplier_id = :new_supplier_id
                    WHERE sku = :sku
                """
                ),
                {"new_supplier_id": new_supplier_id, "sku": sku},
            )
            logger.info(f"Data updated to {ALLOYDB_TABLESCHEMA}.product_supplier_id")

            # Update order line quantity for the given SKU within the PO.
            connection.execute(
                text(
                    f"""
                    UPDATE {ALLOYDB_TABLESCHEMA}.purchase_order_lines
                    SET qty = :new_quantity
                    WHERE po_id = :po_id AND sku = :sku
                """
                ),
                {"new_quantity": new_quantity, "po_id": po_id, "sku": sku},
            )
            logger.info(f"Data updated to {ALLOYDB_TABLESCHEMA}.purchase_order_lines")

            # Recalculate total_amount for the PO based on updated lines.
            connection.execute(
                text(
                    f"""
                UPDATE {ALLOYDB_TABLESCHEMA}.purchase_orders
                SET total_amount = (
                    SELECT SUM(qty * unit_cost)
                    FROM {ALLOYDB_TABLESCHEMA}.purchase_order_lines
                    WHERE po_id = :po_id
                )
                WHERE po_id = :po_id
            """
                ),
                {"po_id": po_id},
            )
            logger.info(f"Data updated to {ALLOYDB_TABLESCHEMA}.purchase_orders")
            # trans.commit()
            return {"status": "success", "po_id": po_id}
    except Exception as e:
        # trans.rollback()
        return {"error": f"Error Editing PO recommendation: {str(e)}"}


async def approve_po_recommendation(engine, po_id):
    """
    Approves a purchase order by setting its status to 'approved'.

    Args:
        engine: SQLAlchemy engine used to execute the update.
        po_id: Identifier of the purchase order to approve.

    Returns:
        Dict[str, Any]: Success payload containing the `po_id`, or an error dict
        when the update fails.
    """
    try:
        with engine.begin() as connection:
            # trans = connection.begin()
            connection.execute(
                text(
                    f"""
                UPDATE {ALLOYDB_TABLESCHEMA}.purchase_orders
                SET status = 'approved'
                WHERE po_id = :po_id
            """
                ),
                {"po_id": po_id},
            )
            logger.info(
                f"Data updated to {ALLOYDB_TABLESCHEMA}.purchase_orders, Approval sent!!"
            )
        return {"status": "success", "po_id": po_id}
    except Exception as e:
        # trans.rollback()
        return {"error": f"Approve PO failed: {str(e)}"}
