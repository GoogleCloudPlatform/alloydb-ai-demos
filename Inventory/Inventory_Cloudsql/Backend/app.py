from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Depends,
)
from sqlalchemy.engine import Engine
from pydantic import BaseModel
from src.agents.coordinator import recommend_replenishment
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn
from src.db.query import (
    inventory_overview,
    recent_purchase_order,
    add_product,
    edit_product,
    edit_purchase_order_recommedation,
    approve_po_recommendation,
)
import asyncio
import pandas as pd
from src.db.cloudsql_connect import cloudsql_client
from src.utils.logger import log_execution


def get_engine():
    """Return the configured SQLAlchemy Engine from the AlloyDB client.

    Returns:
        Engine: A SQLAlchemy Engine instance configured for AlloyDB.
    """
    return cloudsql_client.engine


app = FastAPI(
    title="Inventory Management CloudSQL API",
    description="An API for Agentic inventory management using Cloudsql database.",
)

clients = []


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint used to broadcast status/progress messages.

    Accepts connections from frontend clients and keeps them alive. Messages
    are broadcasted via `broadcast_status`.

    Args:
        websocket (WebSocket): The WebSocket connection object.

    Behavior:
        - Accepts the connection and stores the client in `clients`.
        - Keeps the connection alive with a sleep loop.
        - Removes disconnected clients to avoid stale references.
    """
    await websocket.accept()
    clients.append(websocket)
    print(f"✅ Client connected. Total clients: {len(clients)}", flush=True)

    try:
        while True:
            await asyncio.sleep(1)  # Keep alive
    except WebSocketDisconnect:
        print("❌ Client disconnected", flush=True)
        if websocket in clients:
            clients.remove(websocket)
    except Exception as e:
        # Defensive cleanup on unexpected errors.
        print(f"⚠️ Error in WebSocket loop: {e}", flush=True)
        if websocket in clients:
            clients.remove(websocket)


async def broadcast_status(message: str):
    """Broadcast a status message to all connected WebSocket clients.

    Iterates over a *copy* of the `clients` list to avoid mutation issues while
    sending, and removes any client that raises a send error.

    Args:
        message (str): Human-readable status or progress message.

    Returns:
        None
    """
    for client in clients[:]:  # ✅ Iterate over a copy
        try:
            await client.send_json({"status": message})
        except (WebSocketDisconnect, RuntimeError) as e:
            print(f"⚠️ Error sending to client: {e}. Removing client.", flush=True)
            if client in clients:
                clients.remove(client)


# Enable CORS for all origins/methods/headers to simplify frontend integration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


class EngineSelection(BaseModel):
    """Model representing an engine selector (reserved for future use).

    Attributes:
        engine (str): The engine name/alias to select.
    """

    engine: str


class ProductStock(BaseModel):
    """Model describing a product's stock and contextual attributes.

    Attributes:
        sku (str): Unique product identifier.
        name (str): Human-readable product name.
        category (str): Product category or department.
        store_id (int): Store identifier where stock is tracked.
        on_hand (int): Units currently available on shelves/warehouse.
        safety_stock (int): Minimum buffer stock to prevent stockouts.
        reorder_point (int): Level at which replenishment should be triggered.
        in_transit (int): Units currently in shipment to the store.
        location (str): Location descriptor (e.g., city/region/aisle).
    """

    sku: str
    name: str
    category: str
    store_id: int
    on_hand: int
    safety_stock: int
    reorder_point: int
    in_transit: int
    location: str


class ReplenishmentRecommendation(BaseModel):
    """Request model for generating replenishment recommendations.

    Attributes:
        sku (str): Target SKU for recommendation.
        store_id (int): Store for which recommendation is requested.
        horizon_days (int): Forecast horizon in days.
    """

    sku: str
    store_id: int
    horizon_days: int


class EditPORecommendation(BaseModel):
    """Request model for editing an existing PO recommendation.

    Attributes:
        po_id (int): Purchase order identifier to edit.
        sku (str): SKU associated with the PO line.
        new_supplier_id (int): Supplier ID to assign to the PO line.
        new_quantity (int): Updated recommended quantity.
    """

    po_id: int
    sku: str
    new_supplier_id: int
    new_quantity: int


class ApprovePORecommendation(BaseModel):
    """Request model for approving a PO recommendation.

    Attributes:
        po_id (int): Purchase order identifier to approve.
    """

    po_id: int


@app.get(
    "/",
    summary="Root Endpoint",
    description="Returns a welcome message and a link to the API documentation.",
    response_class=HTMLResponse,
)
def root(request: Request):
    """Return a simple HTML welcome page with a Docs link.

    Args:
        request (Request): FastAPI request object used to obtain base URL.

    Returns:
        str: HTML string including a link to `/docs`.
    """
    base_url = str(request.base_url).rstrip("/")
    docs_url = f"{base_url}/docs"
    return f"""
    <!DOCTYPE html>
    <html>
        <head><title>Welcome</title></head>
        <body>
            <h2>Welcome to the Inventory Management CloudSQL FastAPI Service!!</h2>
            <p>Explore the API documentation: <a href="{docs_url}">{docs_url}</a></p>
        </body>
    </html>
    """


@app.get(
    "/dashboard/inventory/overview",
    summary="To provide the high level metrics of inventory overview",
    description="Returns the JSON which has the data total_skus, low_stock_items, overstock_items, critical_items ",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_inventory_overview(engine: Engine = Depends(get_engine)):
    """Compute and return high-level inventory metrics.

    Retrieves inventory from the data layer and computes:
        - total_skus: Count of unique SKUs
        - low_stock_items: Count of items flagged as Low Stock
        - overstock_items: Count of items flagged as Over Stock
        - critical_items: Count of items flagged as Critical Stock

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: A dictionary with a single key `"metrics"` containing the values.
              If data is missing or invalid, metrics default to zeros.
    """
    inventory_df = await inventory_overview(engine)

    # Validate type and emptiness before using DataFrame-specific attributes.
    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

        return {
            "metrics": {
                "total_skus": 0,
                "low_stock_items": 0,
                "overstock_items": 0,
                "critical_items": 0,
            }
        }

    # Calculate high-level metrics (ensure int conversion for JSON compatibility).
    metrics = {
        "total_skus": int(inventory_df["sku"].nunique()),
        "low_stock_items": int((inventory_df["Status"] == "Low Stock").sum()),
        "overstock_items": int((inventory_df["Status"] == "Over Stock").sum()),
        "critical_items": int((inventory_df["Status"] == "Critical Stock").sum()),
    }

    # Return the data in a JSON format for the Angular frontend
    return {"metrics": metrics}


@app.get(
    "/dashboard/inventory/overview/low_stock",
    summary="To provide the data for low stock",
    description="Returns the JSON which has the data for low_stock_items",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_low_stock(engine: Engine = Depends(get_engine)):
    """Return records of items flagged as Low Stock.

    Filters the inventory for items whose `Status` is `'Low Stock'` and returns
    curated display columns used by the UI.

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        list[dict]: List of product dictionaries for low stock items.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    # Display columns expected by the frontend grid/table component.
    display_cols = [
        "product_name",
        "image_data",
        "sku",
        "category",
        "store_id",
        "location",
        "on_hand",
        "in_transit",
        "safety_stock",
    ]

    low_stock = inventory_df[inventory_df["Status"] == "Low Stock"][display_cols]
    return low_stock.to_dict(orient="records")


@app.get(
    "/dashboard/inventory/overview/over_stock",
    summary="To provide the data for over stock",
    description="Returns the JSON which has the data for Over Stock items",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_over_stock(engine: Engine = Depends(get_engine)):
    """Return records of items flagged as Over Stock.

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        list[dict]: List of product dictionaries for over stock items.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    display_cols = [
        "product_name",
        "image_data",
        "sku",
        "category",
        "store_id",
        "location",
        "on_hand",
        "in_transit",
        "safety_stock",
    ]
    over_stock = inventory_df[inventory_df["Status"] == "Over Stock"][display_cols]
    return over_stock.to_dict(orient="records")


@app.get(
    "/dashboard/inventory/overview/critical_stock",
    summary="To provide the data for critical stock",
    description="Returns the JSON which has the data for Critical Stock items",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_critical_stock(engine: Engine = Depends(get_engine)):
    """Return records of items flagged as Critical Stock.

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        list[dict]: List of product dictionaries for critical stock items.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    display_cols = [
        "product_name",
        "image_data",
        "sku",
        "category",
        "store_id",
        "location",
        "on_hand",
        "in_transit",
        "safety_stock",
    ]
    critical_stock = inventory_df[inventory_df["Status"] == "Critical Stock"][
        display_cols
    ]
    return critical_stock.to_dict(orient="records")


@app.get(
    "/dashboard/inventory/status_distribution",
    description="Provides data for inventory status distribution",
    summary="Provides data to create the donut chart for on the status distribution",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_inventory_status_dist(engine: Engine = Depends(get_engine)):
    """Return percentage distribution of inventory statuses.

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Mapping of status label → percentage (integer).
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    # Normalize counts to percentages; cast to int for cleaner chart labels.
    status_percentage = (
        inventory_df["Status"].value_counts(normalize=True) * 100
    ).astype(int)
    return status_percentage.to_dict()


@app.get(
    "/dashboard/inventory/by_location",
    description="Provides data for inventory by location",
    summary="Provides data to create the bar chart for on the status distribution based on location",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_inventory_by_loc(engine: Engine = Depends(get_engine)):
    """Return inventory status counts grouped by location.

    The response is a dictionary keyed by location, with a list of objects:
        {"Status": <status_label>, "Count": <count_int>}

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Mapping of location → list of {Status, Count} dicts.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    df_by_loc = (
        inventory_df.groupby(["location", "Status"]).size().reset_index(name="Count")
    )

    # Group by location and convert to desired format
    inv_by_loc = (
        df_by_loc.groupby("location")
        .apply(lambda x: x[["Status", "Count"]].to_dict(orient="records"))
        .to_dict()
    )
    return inv_by_loc


@app.get(
    "/dashboard/inventory/all_sku_inventory",
    description="Provides data for all sku inventory details",
    summary="Provides data on all sku inventory to show the data entries in the tabular format",
    responses={500: {"description": "Internal server error"}},
)
@log_execution(is_api=True)
async def get_po_recomm(engine: Engine = Depends(get_engine)):
    """Return full inventory records for all SKUs.

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        list[dict]: List of inventory records suitable for tabular display.
    """
    inventory_df = await inventory_overview(engine)

    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        if "error" in inventory_df:
            raise HTTPException(status_code=500, detail=inventory_df["error"])

    return inventory_df.to_dict(orient="records")


@app.post(
    "/dashboard/inventory/po_recommendation/add_product",
    description="To add products for PO Recommendation",
    summary="Adds data on PO recommendation for the post request sent by the add product button",
    responses={
        200: {"description": "Recommendation generated successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def add_product_data(request: ProductStock, engine: Engine = Depends(get_engine)):
    """Add (or stage) a product for PO recommendation workflows.

    Validates the request via Pydantic, and delegates persistence to the
    data-access function `add_product`.

    Args:
        request (ProductStock): Product stock payload.
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Result from `add_product` on success.

    Raises:
        HTTPException:
            - 400 on known input errors returned from the data layer
            - 500 on unexpected exceptions
    """
    try:
        result = await add_product(
            engine,
            sku=request.sku,
            name=request.name,
            category=request.category,
            store_id=request.store_id,
            on_hand=request.on_hand,
            safety_stock=request.safety_stock,
            reorder_point=request.reorder_point,
            in_transit=request.in_transit,
            location=request.location,
        )
        # Propagate controlled 400 errors returned by the data-access layer.
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        else:
            return result
    except HTTPException:
        # Re-raise to preserve intended HTTP status codes.
        raise
    except Exception as e:
        # Wrap unexpected errors in a 500 response.
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.put(
    "/dashboard/inventory/po_recommendation/edit_product",
    description="To add products for PO Recommendation",
    summary="Adds data on PO recommendation for the post request sent by the add product button",
)
@log_execution(is_api=True)
async def edit_product_data(
    request: ProductStock, engine: Engine = Depends(get_engine)
):
    """Edit product stock details used in PO recommendation.

    Args:
        request (ProductStock): Product stock payload (updated values).
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Status/result of the edit operation.
    """
    status = await edit_product(
        engine,
        sku=request.sku,
        name=request.name,
        category=request.category,
        store_id=request.store_id,
        on_hand=request.on_hand,
        safety_stock=request.safety_stock,
        reorder_point=request.reorder_point,
        in_transit=request.in_transit,
        location=request.location,
    )
    return status


@app.post(
    "/dashboard/replrecommendation/create_recommendations",
    description="To get the recommendation for replenishment",
    summary="Generates recommendations based on SKU and store_id",
    responses={
        200: {"description": "Recommendation generated successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def retrive_recommendation(
    request: ReplenishmentRecommendation, engine: Engine = Depends(get_engine)
):
    """Generate replenishment recommendations and return a compact summary.

    Delegates forecasting and recommendation logic to `recommend_replenishment`,
    and normalizes the result into a JSON-friendly structure.

    Args:
        request (ReplenishmentRecommendation): Payload containing sku, store_id, horizon_days.
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Recommendation summary including forecast mean/CI, supplier choice,
              recommended quantity, PO ID, and status.

    Raises:
        HTTPException:
            - 400 if the result indicates no replenishment is required
            - 500 for other errors reported by the agent/data layer
    """
    try:
        result = await recommend_replenishment(
            broadcast_status,
            engine,
            request.store_id,
            request.sku,
            request.horizon_days,
        )

        # Handle structured error flows from the agent layer.
        if "error" in result:
            if result["error"].get("status") == "no_replenishment":
                raise HTTPException(status_code=400, detail=result["error"])
            else:
                raise HTTPException(status_code=500, detail=result["error"])
        # Defensive parsing of forecast confidence interval.
        forecast_ci = result.get("forecast_ci", (0, 0))
        ci_values = (
            forecast_ci
            if isinstance(forecast_ci, tuple) and len(forecast_ci) == 2
            else (0, 0)
        )

        return {
            "Store ID": result.get("store_id"),
            "SKU": result.get("sku"),
            "Horizon (Days)": result.get("horizon_days"),
            "Forecast Mean": round(result.get("forecast_mean", 0), 2),
            "Forecast CI": f"[{round(ci_values[0], 2)}, {round(ci_values[1], 2)}]",
            "Method": result.get("method"),
            "Net Position": result.get("net_position"),
            "Safety Stock": result.get("safety_stock"),
            "Recommended Qty": result.get("recommended_qty"),
            "Supplier": result.get("supplier_choice", {}).get("supplier"),
            "Unit Cost": result.get("supplier_choice", {}).get("unit_cost"),
            "Status": result.get("status"),
            "PO ID": result.get("po_id"),
        }
    except HTTPException:
        # Preserve the intended HTTP status (e.g., 400) instead of converting to 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post(
    "/dashboard/replrecommendation/editpo",
    description="To edit the recommendation for replenishment",
    summary="Editable fields: Recommended quantity and supplier",
    responses={
        200: {"description": "Purchase order updated successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def edit_purchase_order(
    request: EditPORecommendation, engine: Engine = Depends(get_engine)
):
    """Edit a purchase order recommendation (supplier and quantity).

    Args:
        request (EditPORecommendation): PO edit payload.
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Result of the update operation, or error description.

    Raises:
        HTTPException:
            - 400 when a controlled error is returned from the data layer
            - 500 on unexpected exceptions
    """
    try:
        result = await edit_purchase_order_recommedation(
            engine,
            request.po_id,
            request.sku,
            request.new_supplier_id,
            request.new_quantity,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.post(
    "/dashboard/replrecommendation/approvepo",
    description="To approve the recommendation for replenishment",
    summary="Approves purchase orders and changes status from draft to approved",
    responses={
        200: {"description": "Purchase order approved successfully"},
        400: {"description": "Invalid input"},
        500: {"description": "Internal server error"},
    },
)
@log_execution(is_api=True)
async def approve_purchase_order(
    request: ApprovePORecommendation, engine: Engine = Depends(get_engine)
):
    """Approve a purchase order recommendation.

    Args:
        request (ApprovePORecommendation): PO approval payload.
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        dict: Result of the approval operation, or error description.

    Raises:
        HTTPException:
            - 400 when a controlled error is returned from the data layer
            - 500 on unexpected exceptions
    """
    try:
        result = await approve_po_recommendation(engine, request.po_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get(
    "/dashboard/replrecommendation/recent_po",
    description="Provides data for recent po",
    summary="Provides data on recent PO to show the data entries in the tabular format",
)
@log_execution(is_api=True)
async def get_recent_po(engine: Engine = Depends(get_engine)):
    """Return the most recent purchase orders for display.

    Args:
        engine (Engine): Injected SQLAlchemy Engine for DB access.

    Returns:
        list[dict]: Recent purchase orders as a list of records.
    """
    df = await recent_purchase_order(engine)
    return df.to_dict(orient="records")


# Entrypoint for local execution (e.g., uvicorn development server).
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
