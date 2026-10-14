import numpy as np
import pandas as pd
from pathlib import Path
from app.models.registry import ModelRegistry
from dashboard.utils.data import (
    load_commercial_history,
    load_commercial_latest,
    load_government_history,
    load_government_latest,
)

PROJECT_ROOT = Path("d:/Projects/gridvision")
registry = ModelRegistry(PROJECT_ROOT)

def run_test():
    # 1. Test Commercial
    comm_bundle = registry.get("commercial")
    comm_latest = load_commercial_latest()
    bldg = comm_latest["building_id"].iloc[0]
    row = comm_latest.loc[comm_latest["building_id"] == bldg].iloc[0]
    
    comm_hist = load_commercial_history()
    bldg_hist = comm_hist[comm_hist["building_id"] == bldg].sort_values("timestamp")
    
    demands = list(bldg_hist["hourly_demand_kwh"].values)
    temps = list(bldg_hist["airTemperature"].values)
    last_ts = pd.Timestamp(bldg_hist["timestamp"].max())
    
    print(f"Commercial {bldg} last_ts: {last_ts}, last demand: {demands[-1]}")
    
    predictions = []
    future_timestamps = []
    
    # Iterate next 10 hours
    for step in range(1, 11):
        next_ts = last_ts + pd.Timedelta(hours=step)
        future_timestamps.append(next_ts)
        
        hour = next_ts.hour
        dayofweek = next_ts.dayofweek
        month = next_ts.month
        
        # Features
        feat = {
            "building_id": str(row["building_id"]),
            "site_id": str(row["site_id"]),
            "primaryspaceusage": str(row["primaryspaceusage"]),
            "sub_primaryspaceusage": str(row["sub_primaryspaceusage"]),
            "sqm": float(row["sqm"]),
            "numberoffloors": float(row["numberoffloors"]),
            "occupants": float(row["occupants"]),
            "yearbuilt": float(row["yearbuilt"]),
            "chilledwater": float(row["chilledwater"]),
            "gas": float(row["gas"]),
            "solar": float(row["solar"]),
            "airTemperature": float(temps[-1]),
            "relative_humidity_pct": float(row["relative_humidity_pct"]),
            "cloudCoverage": float(row["cloudCoverage"]),
            "windSpeed": float(row["windSpeed"]),
            "is_weekend": int(dayofweek >= 5),
            "is_business_hours": int(8 <= hour <= 18 and dayofweek < 5),
            "season": "Winter" if month in [12, 1, 2] else ("Spring" if month in [3, 4, 5] else ("Summer" if month in [6, 7, 8] else "Fall")),
            "hour_sin": float(np.sin(2 * np.pi * hour / 24.0)),
            "hour_cos": float(np.cos(2 * np.pi * hour / 24.0)),
            "dayofweek_sin": float(np.sin(2 * np.pi * dayofweek / 7.0)),
            "dayofweek_cos": float(np.cos(2 * np.pi * dayofweek / 7.0)),
            "month_sin": float(np.sin(2 * np.pi * month / 12.0)),
            "month_cos": float(np.cos(2 * np.pi * month / 12.0)),
            "cooling_degree_hours": float(max(0.0, temps[-1] - 18.0)),
            "heating_degree_hours": float(max(0.0, 18.0 - temps[-1])),
            "temp_lag_1h": float(temps[-1]),
            "temp_lag_24h": float(temps[-24] if len(temps) >= 24 else temps[-1]),
            "demand_lag_1h": float(demands[-1]),
            "demand_lag_2h": float(demands[-2]),
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
        
        # Predict using estimator
        frame = pd.DataFrame([feat], columns=comm_bundle.features)
        for cat_feat, palette in zip(
            comm_bundle.metadata["categorical_features"],
            comm_bundle.estimator.booster_.pandas_categorical,
            strict=True,
        ):
            frame[cat_feat] = pd.Categorical(frame[cat_feat], categories=palette)
            
        pred = float(comm_bundle.estimator.predict(frame)[0])
        pred = max(0.0, pred)
        predictions.append(pred)
        demands.append(pred)
        temps.append(temps[-1])
        print(f"  Step {step}: {next_ts} -> {pred:.2f} kWh (lag_1h={feat['demand_lag_1h']:.2f}, roll6={feat['demand_rolling_mean_6h']:.2f})")

    print("\nCommercial 10-step forecast success!")

    # 2. Test Government
    gov_bundle = registry.get("government")
    gov_latest = load_government_latest()
    site = gov_latest["site_id"].iloc[0]
    gov_row = gov_latest.loc[gov_latest["site_id"] == site].iloc[0]
    
    gov_hist = load_government_history()
    site_hist = gov_hist[gov_hist["site_id"] == site].sort_values("timestamp")
    
    g_demands = list(site_hist["total_demand_kwh"].values)
    g_temps = list(site_hist["airTemperature"].values)
    g_last_ts = pd.Timestamp(site_hist["timestamp"].max())
    
    print(f"\nGovernment {site} last_ts: {g_last_ts}, last demand: {g_demands[-1]}")
    
    site_code_map = gov_bundle.metadata["categorical_encodings"]["site_id_code"]
    season_code_map = gov_bundle.metadata["categorical_encodings"]["season"]
    
    for step in range(1, 11):
        next_ts = g_last_ts + pd.Timedelta(hours=step)
        hour = next_ts.hour
        dayofweek = next_ts.dayofweek
        month = next_ts.month
        season_name = "Winter" if month in [12, 1, 2] else ("Spring" if month in [3, 4, 5] else ("Summer" if month in [6, 7, 8] else "Fall"))
        
        feat = {
            "building_count": float(gov_row["building_count"]),
            "airTemperature": float(g_temps[-1]),
            "relative_humidity_pct": float(gov_row["relative_humidity_pct"]),
            "cloudCoverage": float(gov_row["cloudCoverage"]),
            "windSpeed": float(gov_row["windSpeed"]),
            "is_weekend": int(dayofweek >= 5),
            "season": season_code_map[season_name],
            "hour_sin": float(np.sin(2 * np.pi * hour / 24.0)),
            "hour_cos": float(np.cos(2 * np.pi * hour / 24.0)),
            "dayofweek_sin": float(np.sin(2 * np.pi * dayofweek / 7.0)),
            "dayofweek_cos": float(np.cos(2 * np.pi * dayofweek / 7.0)),
            "month_sin": float(np.sin(2 * np.pi * month / 12.0)),
            "month_cos": float(np.cos(2 * np.pi * month / 12.0)),
            "is_business_hours": int(8 <= hour <= 18 and dayofweek < 5),
            "cooling_degree_hours": float(max(0.0, g_temps[-1] - 18.0)),
            "heating_degree_hours": float(max(0.0, 18.0 - g_temps[-1])),
            "demand_lag_1h": float(g_demands[-1]),
            "demand_lag_24h": float(g_demands[-24] if len(g_demands) >= 24 else g_demands[-1]),
            "demand_lag_48h": float(g_demands[-48] if len(g_demands) >= 48 else g_demands[-1]),
            "demand_lag_168h": float(g_demands[-168] if len(g_demands) >= 168 else g_demands[-1]),
            "demand_rolling_mean_6h": float(np.mean(g_demands[-6:])),
            "demand_rolling_std_6h": float(np.std(g_demands[-6:], ddof=0)),
            "demand_rolling_mean_24h": float(np.mean(g_demands[-24:])),
            "demand_rolling_std_24h": float(np.std(g_demands[-24:], ddof=0)),
            "demand_rolling_mean_168h": float(np.mean(g_demands[-168:])),
            "demand_rolling_std_168h": float(np.std(g_demands[-168:], ddof=0)),
            "site_id_code": site_code_map[str(site)],
        }
        frame = pd.DataFrame([feat], columns=gov_bundle.features)
        pred = float(gov_bundle.estimator.predict(frame)[0])
        pred = max(0.0, pred)
        g_demands.append(pred)
        g_temps.append(g_temps[-1])
        print(f"  Gov Step {step}: {next_ts} -> {pred:.2f} kWh (lag_1h={feat['demand_lag_1h']:.2f})")
        
    print("\nGovernment 10-step forecast success!")

if __name__ == "__main__":
    run_test()
