"""Autoregressive multi-step forward forecasting engine for GridVision time-series models."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from dashboard.utils.config import PROJECT_ROOT
from dashboard.utils.data import get_api_client, load_model_metadata


def forecast_commercial_next_10h(
    building_id: str,
    building_history_df: pd.DataFrame,
    latest_row: pd.Series | dict[str, Any],
) -> pd.DataFrame:
    """
    Predict the next 10 hours beyond the dataset using autoregressive lag feature updates.
    
    Each hour's prediction updates demand_lag_1h, demand_lag_2h, and rolling statistics
    for subsequent prediction steps.
    """
    bldg_hist = building_history_df.loc[
        building_history_df["building_id"].astype(str).eq(str(building_id))
    ].sort_values("timestamp")

    if bldg_hist.empty:
        return pd.DataFrame(columns=["timestamp", "forecast_kwh"])

    demands = [float(v) for v in bldg_hist["hourly_demand_kwh"].values]
    temps = [float(v) for v in bldg_hist["airTemperature"].values]
    last_ts = pd.Timestamp(bldg_hist["timestamp"].max())

    api_client = get_api_client()
    metadata = load_model_metadata("commercial")
    features_list = list(metadata["features"])

    future_records: list[dict[str, Any]] = []

    for step in range(1, 11):
        next_ts = last_ts + pd.Timedelta(hours=step)
        hour = next_ts.hour
        dayofweek = next_ts.dayofweek
        month = next_ts.month

        # Seasonal mapping for Commercial (categorical string)
        if month in [12, 1, 2]:
            season_name = "Winter"
        elif month in [3, 4, 5]:
            season_name = "Spring"
        elif month in [6, 7, 8]:
            season_name = "Summer"
        else:
            season_name = "Fall"

        curr_temp = temps[-1]

        feat_dict: dict[str, Any] = {
            "building_id": str(latest_row["building_id"]),
            "site_id": str(latest_row.get("site_id", "Panther")),
            "primaryspaceusage": str(latest_row.get("primaryspaceusage", "Commercial")),
            "sub_primaryspaceusage": str(latest_row.get("sub_primaryspaceusage", "General")),
            "sqm": float(latest_row.get("sqm", 1000.0)),
            "numberoffloors": float(latest_row.get("numberoffloors", 1.0)),
            "occupants": float(latest_row.get("occupants", 50.0)),
            "yearbuilt": float(latest_row.get("yearbuilt", 2000.0)),
            "chilledwater": float(latest_row.get("chilledwater", 0.0)),
            "gas": float(latest_row.get("gas", 0.0)),
            "solar": float(latest_row.get("solar", 0.0)),
            "airTemperature": curr_temp,
            "relative_humidity_pct": float(latest_row.get("relative_humidity_pct", 50.0)),
            "cloudCoverage": float(latest_row.get("cloudCoverage", 2.0)),
            "windSpeed": float(latest_row.get("windSpeed", 2.5)),
            "is_weekend": int(dayofweek >= 5),
            "is_business_hours": int(8 <= hour <= 18 and dayofweek < 5),
            "season": season_name,
            "hour_sin": float(np.sin(2 * np.pi * hour / 24.0)),
            "hour_cos": float(np.cos(2 * np.pi * hour / 24.0)),
            "dayofweek_sin": float(np.sin(2 * np.pi * dayofweek / 7.0)),
            "dayofweek_cos": float(np.cos(2 * np.pi * dayofweek / 7.0)),
            "month_sin": float(np.sin(2 * np.pi * month / 12.0)),
            "month_cos": float(np.cos(2 * np.pi * month / 12.0)),
            "cooling_degree_hours": float(max(0.0, curr_temp - 18.0)),
            "heating_degree_hours": float(max(0.0, 18.0 - curr_temp)),
            "temp_lag_1h": float(temps[-1]),
            "temp_lag_24h": float(temps[-24] if len(temps) >= 24 else temps[-1]),
            # Dynamic autoregressive demand lags
            "demand_lag_1h": float(demands[-1]),
            "demand_lag_2h": float(demands[-2] if len(demands) >= 2 else demands[-1]),
            "demand_lag_24h": float(demands[-24] if len(demands) >= 24 else demands[-1]),
            "demand_lag_48h": float(demands[-48] if len(demands) >= 48 else demands[-1]),
            "demand_lag_168h": float(demands[-168] if len(demands) >= 168 else demands[-1]),
            "demand_rolling_mean_6h": float(np.mean(demands[-6:])),
            "demand_rolling_std_6h": float(np.std(demands[-6:], ddof=0)),
            "demand_rolling_mean_24h": float(np.mean(demands[-24:])),
            "demand_rolling_std_24h": float(np.std(demands[-24:], ddof=0)),
            "demand_rolling_mean_168h": float(np.mean(demands[-168:])),
            "demand_rolling_std_168h": float(np.std(demands[-168:], ddof=0)),
        }

        # Keep only required model features
        ordered_features = {k: feat_dict[k] for k in features_list if k in feat_dict}

        payload = {
            "entity_id": str(building_id),
            "forecast_timestamp": next_ts.isoformat(),
            "features": ordered_features,
            "context": "future_forecast",
        }

        try:
            res = api_client.predict("commercial", payload)
            pred = float(res.get("prediction", 0.0))
        except Exception:
            # Direct estimator fallback if API unreachable
            from app.models.registry import ModelRegistry
            bundle = ModelRegistry(PROJECT_ROOT).get("commercial")
            frame = pd.DataFrame([ordered_features], columns=bundle.features)
            for cat_feat, palette in zip(
                bundle.metadata["categorical_features"],
                bundle.estimator.booster_.pandas_categorical,
                strict=True,
            ):
                frame[cat_feat] = pd.Categorical(frame[cat_feat], categories=palette)
            pred = float(bundle.estimator.predict(frame)[0])

        pred = max(0.0, pred)
        demands.append(pred)
        temps.append(curr_temp)
        future_records.append({"timestamp": next_ts, "forecast_kwh": pred})

    return pd.DataFrame(future_records)


def forecast_government_next_10h(
    site_id: str,
    site_history_df: pd.DataFrame,
    latest_row: pd.Series | dict[str, Any],
) -> pd.DataFrame:
    """
    Predict the next 10 hours for a regional grid zone using autoregressive lag updates.
    """
    s_hist = site_history_df.loc[
        site_history_df["site_id"].astype(str).eq(str(site_id))
    ].sort_values("timestamp")

    if s_hist.empty:
        return pd.DataFrame(columns=["timestamp", "forecast_kwh"])

    demands = [float(v) for v in s_hist["total_demand_kwh"].values]
    temps = [float(v) for v in s_hist["airTemperature"].values]
    last_ts = pd.Timestamp(s_hist["timestamp"].max())

    api_client = get_api_client()
    metadata = load_model_metadata("government")
    features_list = list(metadata["features"])

    site_code_map = metadata.get("categorical_encodings", {}).get("site_id_code", {})
    season_code_map = metadata.get("categorical_encodings", {}).get("season", {})

    site_code = site_code_map.get(str(site_id), 0)

    future_records: list[dict[str, Any]] = []

    for step in range(1, 11):
        next_ts = last_ts + pd.Timedelta(hours=step)
        hour = next_ts.hour
        dayofweek = next_ts.dayofweek
        month = next_ts.month

        if month in [12, 1, 2]:
            season_name = "Winter"
        elif month in [3, 4, 5]:
            season_name = "Spring"
        elif month in [6, 7, 8]:
            season_name = "Summer"
        else:
            season_name = "Fall"

        curr_temp = temps[-1]

        feat_dict: dict[str, Any] = {
            "building_count": float(latest_row.get("building_count", 50.0)),
            "airTemperature": curr_temp,
            "relative_humidity_pct": float(latest_row.get("relative_humidity_pct", 50.0)),
            "cloudCoverage": float(latest_row.get("cloudCoverage", 2.0)),
            "windSpeed": float(latest_row.get("windSpeed", 2.5)),
            "is_weekend": int(dayofweek >= 5),
            "season": season_code_map.get(season_name, 3),
            "hour_sin": float(np.sin(2 * np.pi * hour / 24.0)),
            "hour_cos": float(np.cos(2 * np.pi * hour / 24.0)),
            "dayofweek_sin": float(np.sin(2 * np.pi * dayofweek / 7.0)),
            "dayofweek_cos": float(np.cos(2 * np.pi * dayofweek / 7.0)),
            "month_sin": float(np.sin(2 * np.pi * month / 12.0)),
            "month_cos": float(np.cos(2 * np.pi * month / 12.0)),
            "is_business_hours": int(8 <= hour <= 18 and dayofweek < 5),
            "cooling_degree_hours": float(max(0.0, curr_temp - 18.0)),
            "heating_degree_hours": float(max(0.0, 18.0 - curr_temp)),
            # Dynamic autoregressive demand lags
            "demand_lag_1h": float(demands[-1]),
            "demand_lag_24h": float(demands[-24] if len(demands) >= 24 else demands[-1]),
            "demand_lag_48h": float(demands[-48] if len(demands) >= 48 else demands[-1]),
            "demand_lag_168h": float(demands[-168] if len(demands) >= 168 else demands[-1]),
            "demand_rolling_mean_6h": float(np.mean(demands[-6:])),
            "demand_rolling_std_6h": float(np.std(demands[-6:], ddof=0)),
            "demand_rolling_mean_24h": float(np.mean(demands[-24:])),
            "demand_rolling_std_24h": float(np.std(demands[-24:], ddof=0)),
            "demand_rolling_mean_168h": float(np.mean(demands[-168:])),
            "demand_rolling_std_168h": float(np.std(demands[-168:], ddof=0)),
            "site_id_code": site_code,
        }

        ordered_features = {k: feat_dict[k] for k in features_list if k in feat_dict}

        payload = {
            "entity_id": str(site_id),
            "forecast_timestamp": next_ts.isoformat(),
            "features": ordered_features,
            "context": "future_forecast",
        }

        try:
            res = api_client.predict("government", payload)
            pred = float(res.get("prediction", 0.0))
        except Exception:
            from app.models.registry import ModelRegistry
            bundle = ModelRegistry(PROJECT_ROOT).get("government")
            frame = pd.DataFrame([ordered_features], columns=bundle.features)
            pred = float(bundle.estimator.predict(frame)[0])

        pred = max(0.0, pred)
        demands.append(pred)
        temps.append(curr_temp)
        future_records.append({"timestamp": next_ts, "forecast_kwh": pred})

    return pd.DataFrame(future_records)


def forecast_government_aggregate_next_10h(
    gov_history_df: pd.DataFrame,
    gov_latest_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute system-wide aggregate forecast for the next 10 hours by summing
    individual autoregressive 10-hour forecasts across all 17 regional grid zones.
    """
    sites = sorted(gov_latest_df["site_id"].astype(str).unique())
    if not sites:
        return pd.DataFrame(columns=["timestamp", "total_aggregate_demand_kwh"])

    agg_forecast: dict[pd.Timestamp, float] = {}

    for site in sites:
        latest_match = gov_latest_df.loc[gov_latest_df["site_id"].astype(str).eq(site)]
        if latest_match.empty:
            continue
        row = latest_match.iloc[0]
        site_fc = forecast_government_next_10h(site, gov_history_df, row)
        for _, fc_row in site_fc.iterrows():
            ts = fc_row["timestamp"]
            val = fc_row["forecast_kwh"]
            agg_forecast[ts] = agg_forecast.get(ts, 0.0) + val

    rows = [{"timestamp": ts, "total_aggregate_demand_kwh": val} for ts, val in sorted(agg_forecast.items())]
    return pd.DataFrame(rows)


def forecast_household_next_10_days(
    household_id: str,
    household_history_df: pd.DataFrame,
    latest_row: pd.Series | dict[str, Any],
) -> pd.DataFrame:
    """
    Project future daily consumption steps for a household using historical baseline and month-end target.
    """
    h_hist = household_history_df.loc[
        household_history_df["household_id"].astype(str).eq(str(household_id))
    ].sort_values("date")

    if h_hist.empty:
        return pd.DataFrame(columns=["date", "forecast_kwh"])

    daily_vals = [float(v) for v in h_hist["daily_kwh"].dropna().values]
    last_date = pd.Timestamp(h_hist["date"].max())
    
    # Baseline recent rolling mean daily consumption
    recent_mean = float(np.mean(daily_vals[-7:])) if len(daily_vals) >= 7 else (daily_vals[-1] if daily_vals else 10.0)

    future_records: list[dict[str, Any]] = []
    
    # Project next 10 days
    for step in range(1, 11):
        next_date = last_date + pd.Timedelta(days=step)
        # Apply slight weekend seasonality modulation if weekend
        day_factor = 1.05 if next_date.dayofweek >= 5 else 0.98
        # Autoregressive smoothing incorporating prior simulated daily consumption
        simulated_daily = max(0.0, (0.7 * recent_mean + 0.3 * daily_vals[-1]) * day_factor)
        daily_vals.append(simulated_daily)
        recent_mean = float(np.mean(daily_vals[-7:]))
        future_records.append({"date": next_date, "forecast_kwh": simulated_daily})

    return pd.DataFrame(future_records)
