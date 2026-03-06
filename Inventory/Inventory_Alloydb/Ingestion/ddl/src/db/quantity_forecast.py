from sqlalchemy import text
from fastapi import HTTPException
import pandas as pd

from src.utils.config import ALLOYDB_TABLESCHEMA
from datetime import timedelta
from src.db.random_sampler_model import RandomSamplerModel as RandomSampler

# from random_sampler_model import RandomSamplerModel as RandomSampler


def check_for_model_definition_in_db(engine, sku, store_id):
    """
    Checks if a model definition exists in the 'inventory_forecast_models' table
    for the given SKU and store_id, and returns the model name if found.
    """
    if not engine:
        print("No database engine available to check for model definition.")
        return False, None

    try:
        query = text(
            f"""
            SELECT model_name
            FROM {ALLOYDB_TABLESCHEMA}.inventory_forecast_models
            WHERE sku = :sku AND store_id = :store_id;
        """
        )
        with engine.connect() as conn:
            result = conn.execute(query, {"sku": sku, "store_id": store_id}).fetchone()

            if result:
                model_name = result[0]
                print(
                    f"Found model definition for SKU: {sku}, Store ID: {store_id} with name: {model_name}"
                )
                return True, model_name
            else:
                print(f"No model definition found for SKU: {sku}, Store ID: {store_id}")
                return False, None
    except Exception as e:
        print(f"Error checking for model definition in database: {e}")
        return False, None


def get_historical_data_from_db(engine, sku, store_id):
    if not engine:
        print("No database engine available to fetch historical data.")
        return pd.Series([])

    try:
        # Dynamically insert table_name into the query
        query = text(
            f"""
            SELECT order_ts, quantity
            FROM {ALLOYDB_TABLESCHEMA}.transactions
            WHERE sku = :sku AND store_id = :store_id
            ORDER BY order_ts;
        """
        )
        with engine.connect() as conn:
            rows = conn.execute(query, {"sku": sku, "store_id": store_id}).fetchall()
            # print(f"DEBUG: Query returned {len(rows)} rows for table '{table_name}'.") # DEBUG PRINT

            if not rows:
                print(
                    f"No historical data found for SKU: {sku}, Store ID: {store_id} in the database table: {ALLOYDB_TABLESCHEMA}.transactions."
                )
                return pd.Series([])

            df = pd.DataFrame(rows, columns=["order_ts", "quantity"])
            df["order_ts"] = pd.to_datetime(df["order_ts"])
            # Aggregate to daily sums before reindexing
            df_daily = df.groupby(df["order_ts"].dt.date)[
                "quantity"
            ].sum()  # Sum quantities for each day
            df_daily.index = pd.to_datetime(
                df_daily.index
            )  # Convert index back to DatetimeIndex

            # print(f"DEBUG: DataFrame min order_ts: {df_daily.index.min()}, max order_ts: {df_daily.index.max()}") # DEBUG PRINT

            # Ensure daily frequency and fill missing days with 0 (reindexing the already daily-aggregated data)
            if not df_daily.empty:
                all_dates = pd.date_range(
                    start=df_daily.index.min(), end=df_daily.index.max(), freq="D"
                )
                df_daily = df_daily.reindex(all_dates, fill_value=0)
            return df_daily
    except Exception as e:
        print(
            f"Error fetching historical data from database table '{ALLOYDB_TABLESCHEMA}.transactions': {e}"
        )
        return pd.Series([])
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"Error closing database connection: {e}")


def _get_fallback_forecast(
    engine,
    sku,
    store_id,
    forecast_horizon_arg,
    default_historical_data,
    default_forecast_output,
):
    """
    Encapsulates the logic for fetching historical data from the database, training a Random Sampler model,
    and handling default values if necessary.
    Returns model_used_info, historical_data_to_display, forecast_output, transactions_found (boolean).
    """
    model_used_info = "Default Generation (Fallback: Config not found)"
    historical_data_to_display = default_historical_data
    forecast_output = default_forecast_output
    transactions_found = False  # New flag to indicate if transactions were found

    db_historical_data = get_historical_data_from_db(
        engine,
        sku,
        store_id,
    )
    if not db_historical_data.empty:
        transactions_found = True
        print(
            "Generating forecast with RandomSampler using historical data from database."
        )
        historical_data_to_display = db_historical_data
        temp_model = RandomSampler(horizon=forecast_horizon_arg, random_seed=42)
        temp_model.fit(db_historical_data)
        db_forecast_series = temp_model.predict()
        model_used_info = "Random Sampler (No database Logic)"
        forecast_output = db_forecast_series
        if len(forecast_output) > forecast_horizon_arg:
            forecast_output = forecast_output.iloc[:forecast_horizon_arg]
        elif len(forecast_output) < forecast_horizon_arg:
            print(
                f"Warning: Database-driven model generated a forecast of {len(forecast_output)} days, which is shorter than the requested {forecast_horizon_arg} days. Displaying the generated forecast."
            )
        else:
            print(
                f"No usable historical data found for SKU: {sku}, Store ID: {store_id} in the database table: {ALLOYDB_TABLESCHEMA}.transactions. Generating default values."
            )
            model_used_info = "Default Generation"
    else:
        print(
            "Could not establish database connection for historical data. Generating default historical and forecast values."
        )
        model_used_info = "Default Generation (No transaction details found)"
    model_used_info = ""
    return (
        model_used_info,
        historical_data_to_display,
        forecast_output,
        transactions_found,
    )


def format_time_series(data, kind: str):
    """
    Switchable formatter.
    kind: "historical" -> [{date, quantity}]
          "forecast"   -> [{date, predicted_quantity}]
    Accepts dict or pandas Series.
    """
    key_map = {"historical": "quantity", "forecast": "predicted_quantity"}
    if kind not in key_map:
        raise ValueError("kind must be 'historical' or 'forecast'")

    items = data.items() if hasattr(data, "items") else data.to_dict().items()
    key = key_map[kind]

    out = [
        {"date": str(k)[:10], key: (int(v) if v is not None else 0)} for k, v in items
    ]
    out.sort(key=lambda x: x["date"])
    return out


def quantity_forecast(engine, sku: str, store_id: int, horizon_days: int):
    # VALID = {("22209", 1055), ("47556B", 1055)}
    check_model = check_for_model_definition_in_db(engine, sku, store_id)
    print("Checking the model definition in db", check_model)
    if not check_model[0]:
        print("Executing fallback generation logic")
        # raise HTTPException(status_code=400, detail="Invalid (sku, store_id) combination")
        today = pd.Timestamp.now().normalize()  # keep normalize() if you want midnight
        default_historical_days = 90
        default_historical_end_date = today - timedelta(days=1)
        default_historical_start_date = default_historical_end_date - timedelta(
            days=default_historical_days - 1
        )

        default_historical_data = pd.Series(
            0,  # fills zeros
            index=pd.date_range(
                default_historical_start_date, default_historical_end_date, freq="D"
            ),
            name="quantity",
        )
        default_forecast_start_date = default_historical_end_date + timedelta(days=1)
        default_forecast_end_date = default_forecast_start_date + timedelta(
            days=horizon_days - 1
        )
        default_forecast_output = pd.Series(
            0,
            index=pd.date_range(
                default_forecast_start_date, default_forecast_end_date, freq="D"
            ),
            name="quantity",
        )
        model_used_info = "Default Generation (Initial)"
        (
            model_used_info,
            historical_data_to_display,
            forecast_output,
            transactions_found,
        ) = _get_fallback_forecast(
            engine,
            sku,
            store_id,
            horizon_days,
            default_historical_data,
            default_forecast_output,
        )

        # Usage in your existing output:
        output = {
            "sku": sku,
            "store_id": store_id,
            "horizon": horizon_days,
            "model_name": model_used_info,
            "quantity_forecast": {
                "historical_data": format_time_series(
                    historical_data_to_display, "historical"
                ),
                "forecast_data": format_time_series(forecast_output, "forecast"),
            },
        }
        return {"status": "success", "result": output}
    else:
        # payload =   # matches your console
        print("Executing the model based forecast logic")
        request_body = (
            f'{{"sku": "{sku}", "store_id": {store_id}, "horizon": {horizon_days}}}'
        )

        try:
            stmt = text(
                """
                SELECT google_ml.predict_row(
                    model_id     => 'inventory-forecast-model',
                    request_body => :request_body
                ) AS prediction
            """
            )

            with engine.connect() as conn:
                rows = conn.execute(stmt, {"request_body": request_body}).fetchone()
                # print("Printing the rows",rows[0])
                json_output = rows[0]
                json_output["model_name"] = "Random Sampler model registered in AlloyDB"
            return {"status": "success", "result": json_output}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"quantity_forecast failed: {e}"
            )


# from src.db.alloydb_connect import alloydb_client
# if __name__ == "__main__":
#     print("One...............................")
#     engine = alloydb_client.engine
#     # result = check_for_model_definition_in_db(engine, "22209", 1055)
#     result = check_for_model_definition_in_db(engine, "21432", 1055)
#     print("check_for_model_definition_in_db Result : ",result)
#     print("One...............................")
#     # historical_data = get_historical_data_from_db(engine, "22209", 1055)
#     historical_data = get_historical_data_from_db(engine, "21439", 1055)
#     print("get_historical_data_from_db result is :",historical_data)
#     print("One...............................")
#     forecast = quantity_forecast(engine,"21439", 1055,10)
#     print("Forecast", forecast)
#     print("One...............................")
