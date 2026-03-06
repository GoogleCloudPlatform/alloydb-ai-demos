import pandas as pd
import numpy as np


class RandomSamplerModel:
    def __init__(self, horizon=30, random_seed=None):
        self.horizon = horizon
        self.random_seed = random_seed
        self.historical_series = None

    def fit(self, historical_series):
        """
        Fits the model with historical data.
        historical_series: pandas Series with DatetimeIndex representing historical quantities.
        """
        self.historical_series = historical_series

    def predict(self):
        """
        Generates a forecast by randomly sampling from historical values.
        """
        if self.historical_series is None:
            raise ValueError(
                "Model has not been fitted. Call .fit() with historical data first."
            )

        if self.random_seed is not None:
            np.random.seed(self.random_seed)

        # Get the pool of historical values to draw from
        # Convert to int to ensure quantities remain integers if they were originally
        history_pool = self.historical_series.values.astype(int)

        # Randomly select values from history with replacement for the horizon
        simulated_values = np.random.choice(
            history_pool, size=self.horizon, replace=True
        )

        # Create date index for future
        last_date = self.historical_series.index[-1]
        future_dates = pd.date_range(
            start=last_date + pd.Timedelta(days=1), periods=self.horizon, freq="D"
        )

        return pd.Series(simulated_values, index=future_dates)
