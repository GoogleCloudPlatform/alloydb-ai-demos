from __future__ import annotations
from typing import Dict, Any
import pandas as pd
from sqlalchemy import text
from prophet import Prophet
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import CLOUDSQL_TABLESCHEMA


@status_broadcast("Demand agent is working")
async def forecast_sku_store(
    broadcast, engine, store_id: int, sku: str, horizon_days: int = 14
) -> Dict[str, Any]:
    """
    Forecasts short-term demand for a given store–SKU using Prophet, with a
    moving-average fallback when model fitting fails or data is insufficient.

    Workflow:
        1) Query daily aggregated demand from `{CLOUDSQL_TABLESCHEMA}.transactions` (last 180 days).
        2) Prepare a DataFrame with Prophet-required columns (`ds`, `y`).
        3) Fit Prophet with daily seasonality and predict `horizon_days`.
        4) If Prophet fails, compute a 14-day moving average and simple CI.

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        engine: SQLAlchemy engine used to query transaction history.
        store_id (int): Store identifier for which demand is forecasted.
        sku (str): Product SKU under consideration.
        horizon_days (int, optional): Forecast horizon in days. Defaults to 14.

    Returns:
        Dict[str, Any]: Payload including:
            - method (str): 'prophet', 'moving-average', or 'none' (no data).
            - mean (float): Mean demand estimate over the horizon.
            - ci (Tuple[float, float]): Confidence interval (low, high).
            - series (List[Dict[str, Any]]): Historical series records.
            - forecast (List[Dict[str, Any]]): Horizon forecast points (date, yhat).
    """
    # -------------------------------------------------------------------------
    # Fetch daily aggregated demand for the store–SKU (up to 180 most recent days).
    # -------------------------------------------------------------------------
    query = text(
        f"""
        SELECT DATE(order_ts) AS day, SUM(quantity)::float AS qty
        FROM {CLOUDSQL_TABLESCHEMA}.transactions
        WHERE store_id = :store_id AND sku = :sku
        GROUP BY DATE(order_ts)
        ORDER BY day DESC
        LIMIT 180
    """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"store_id": store_id, "sku": sku}).fetchall()

    # Guard: no transactions for this store–SKU → return neutral payload.
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
    # Prepare DataFrame for Prophet (rename to `ds` and `y`).
    # -------------------------------------------------------------------------
    df = pd.DataFrame(rows)
    df.rename(columns={"day": "ds", "qty": "y"}, inplace=True)

    # -------------------------------------------------------------------------
    # Attempt Prophet fit and prediction for the specified horizon.
    # -------------------------------------------------------------------------
    try:
        model = Prophet(daily_seasonality=True)
        model.fit(df)

        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)

        # Extract only the horizon window and compute mean + CI bounds.
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
        # Fallback: Prophet may fail due to insufficient data or convergence issues.
        # Use a recent 14-day moving average with ~80% CI (±1.28 * std).
        # ---------------------------------------------------------------------
        print(f"⚠️ Prophet model failed: {e}. Falling back to moving average.")

        # Fallback: Moving Average
        ma = df["y"].tail(14).mean() if len(df) >= 14 else df["y"].mean()
        std = df["y"].tail(14).std() if len(df) >= 14 else df["y"].std()
        ma = float(ma) if pd.notna(ma) else 0.0
        std = float(std) if pd.notna(std) else 0.0

        return {
            "method": "moving-average",
            "mean": ma,
            "ci": (ma - 1.28 * std, ma + 1.28 * std),
            "series": df.to_dict(orient="records"),
            "forecast": [
                {"ds": str(df["ds"].iloc[-1] + pd.Timedelta(days=i + 1)), "yhat": ma}
                for i in range(horizon_days)
            ],
        }
