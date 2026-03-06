from __future__ import annotations
from typing import Dict, Any
import pandas as pd
from sqlalchemy import text
from prophet import Prophet
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import ALLOYDB_TABLESCHEMA


@status_broadcast("Demand agent is working")
async def forecast_sku_store(
    broadcast, engine, store_id: int, sku: str, horizon_days: int = 14
) -> Dict[str, Any]:
    """
    Forecasts short-term demand for a given store–SKU using Prophet, with a
    moving-average fallback when model fitting fails or data is insufficient.

    The function orchestrates:
      1) Historical demand retrieval (SQL).
      2) Data preparation for Prophet (`ds`, `y` schema).
      3) Prophet-based forecast generation for `horizon_days`.
      4) Fallback to a recent moving average with a simple CI when Prophet errors.

    Args:
        broadcast: Orchestration or messaging object used by the status decorator.
        engine: SQLAlchemy engine used to query transaction history.
        store_id (int): Store identifier for which demand is forecasted.
        sku (str): Product SKU under consideration.
        horizon_days (int, optional): Forecast horizon (in days). Defaults to 14.

    Returns:
        Dict[str, Any]: A result payload that includes:
            - method (str): 'prophet', 'moving-average', or 'none'.
            - mean (float): Mean demand estimate over the horizon.
            - ci (Tuple[float, float]): Confidence interval (low, high) estimate.
            - series (List[Dict[str, Any]]): Historical series records.
            - forecast (List[Dict[str, Any]]): Horizon forecast points (date, yhat).
        If no data exists, returns zeros with an empty series and forecast list.
    """

    # -------------------------------------------------------------------------
    # Fetch historical demand data (up to ~6 months) aggregated by day.
    # Query fields:
    #   - day: DATE(order_ts)
    #   - qty: SUM(quantity)::float
    # Ordering by the most recent days ensures Prophet sees latest trends first.
    # -------------------------------------------------------------------------
    query = text(
        f"""
        SELECT DATE(order_ts) AS day, SUM(quantity)::float AS qty
        FROM {ALLOYDB_TABLESCHEMA}.transactions
        WHERE store_id = :store_id AND sku = :sku
        GROUP BY DATE(order_ts)
        ORDER BY day DESC
        LIMIT 180
    """
    )

    # Execute the query and retrieve daily aggregates.
    with engine.connect() as connection:
        rows = connection.execute(query, {"store_id": store_id, "sku": sku}).fetchall()

    # Guard: if there are no transactions for this store–SKU, return a neutral payload.
    if not rows:
        print(f"⚠️ No transaction data found for SKU {sku} at store {store_id}")
        return {
            "method": "none",
            "mean": 0.0,
            "ci": (0.0, 0.0),
            "series": [],
            "forecast": [],
        }

    # -------------------------------------------------------------------------
    # Prepare DataFrame for Prophet:
    # Prophet expects columns:
    #   - ds: datetime stamp
    #   - y : target numeric value
    # We rename the query outputs accordingly.
    # -------------------------------------------------------------------------
    df = pd.DataFrame(rows)
    df.rename(columns={"day": "ds", "qty": "y"}, inplace=True)

    # -------------------------------------------------------------------------
    # Attempt Prophet model fit and forecasting.
    #   - Enable daily seasonality to capture day-level patterns.
    #   - Extend the timeline by `horizon_days`.
    #   - Compute mean prediction and CI bounds across the horizon window.
    # -------------------------------------------------------------------------
    try:
        model = Prophet(daily_seasonality=True)
        model.fit(df)

        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)

        # Extract forecast for horizon
        horizon_forecast = forecast.tail(horizon_days)
        mean_forecast = float(horizon_forecast["yhat"].mean())
        ci_low = float(horizon_forecast["yhat_lower"].mean())
        ci_high = float(horizon_forecast["yhat_upper"].mean())

        return {
            "method": "prophet",
            "mean": mean_forecast,
            "ci": (ci_low, ci_high),
            "series": df.to_dict(orient="records"),
            "forecast": horizon_forecast[["ds", "yhat"]].to_dict(orient="records"),
        }

    except Exception as e:
        # ---------------------------------------------------------------------
        # Fallback path: Prophet can fail due to limited data, convergence issues,
        # or unexpected time-series anomalies. In such cases, we use a moving
        # average computed over the last 14 observations (or fewer if not available)
        # and derive a simple CI using ±1.28 * std (approx. 80% CI).
        # ---------------------------------------------------------------------
        print(f"⚠️ Prophet model failed: {e}. Falling back to moving average.")

        # Compute moving average and standard deviation on the most recent slice.
        ma = df["y"].tail(14).mean() if len(df) >= 14 else df["y"].mean()
        std = df["y"].tail(14).std() if len(df) >= 14 else df["y"].std()

        # Normalize NaN outcomes to zeros for robustness.
        ma = float(ma) if pd.notna(ma) else 0.0
        std = float(std) if pd.notna(std) else 0.0

        return {
            "method": "moving-average",
            "mean": ma,
            "ci": (ma - 1.28 * std, ma + 1.28 * std),
            "series": df.to_dict(orient="records"),
            # Generate a flat horizon forecast using the MA as yhat.
            "forecast": [
                {"ds": str(df["ds"].iloc[-1] + pd.Timedelta(days=i + 1)), "yhat": ma}
                for i in range(horizon_days)
            ],
        }
