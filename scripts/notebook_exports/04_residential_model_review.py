# Generated from the corresponding notebook's code cells.
# Review before execution; notebook cells were not all executed.
# Notebook shell commands are retained as comments, not run.
# ruff: noqa
from __future__ import annotations

# %% Notebook code cell 2
from pathlib import Path
import json, pickle, warnings, itertools, math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 100)
pd.set_option("display.width", 160)

# %% Notebook code cell 3
df = pd.read_csv(
"Data/Demo.txt",
sep=";",
decimal=",",
parse_dates=[0],
index_col=0
)

# %% Notebook code cell 4
df.sample(10)

# %% Notebook code cell 5
print(f"Shape: {df.shape[0]:,} timestamps x {df.shape[1]} meters")
print(f"Time range: {df.index.min()} to {df.index.max()}")
print(f"Index is sorted: {df.index.is_monotonic_increasing}")
print(f"Duplicate timestamps: {df.index.duplicated().sum():,}")
print(f"Missing values: {df.isna().sum().sum():,} ({df.isna().sum().sum() / df.size:.2%})")

# %% Notebook code cell 6
df.head()

# %% Notebook code cell 7
# Reset the index to make the timestamps a regular column
df = df.reset_index()

# If the index column got named something generic like 'index' or 'level_0', rename it:
df = df.rename(columns={'index': 'timestamp'}) # (or whatever default name it received)

# Verify
print(df.head())

# %% Notebook code cell 8
# Notebook-only command omitted: !pip install pyarrow fastparquet

# %% Notebook code cell 9
from pathlib import Path

df = df.rename(columns={df.columns[0]: "timestamp"})

parquet_path = Path("Data/customerwise_data.parquet")
df.to_parquet(parquet_path, index=False)

size_bytes = parquet_path.stat().st_size
print(f"Parquet size: {size_bytes:,} bytes ({size_bytes / 1024**2:.2f} MiB)")

# %% Notebook code cell 10
print("\nColumn dtypes:")
print(df.dtypes.value_counts())

# %% Notebook code cell 11
import matplotlib.pyplot as plt
import pandas as pd

# Ensure 'timestamp' is in datetime format and set it as the index for resampling
df["timestamp"] = pd.to_datetime(df["timestamp"])
daily_average = df.set_index("timestamp").resample("D").mean().mean(axis=1)

# Plotting
ax = daily_average.plot(figsize=(12, 4), title="Daily Average Load Across Meters")
ax.set_xlabel("Date")
ax.set_ylabel("Average load")
plt.tight_layout()
plt.show()

# %% Notebook code cell 14
from pathlib import Path
import json, pickle, warnings, itertools, math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 100)
pd.set_option("display.width", 160)

# ---- EDIT THESE ----
DATA_PATH = Path("Data/Customerwise_data.parquet")  # supports .csv, .parquet, .pq
TIMESTAMP_COL = "timestamp"               # change to your actual timestamp column
TARIFF_INR_PER_KWH = 10.0
MIN_COVERAGE_PER_DAY = 0.90                # 90% of expected 96 readings
MIN_TRAIN_ORIGIN_DAY = 7                   # only predict after 7 complete elapsed days
TEST_FRACTION_OF_DATES = 0.15
VALIDATION_FRACTION_OF_REMAINING_DATES = 0.15
RANDOM_STATE = 42
OUTPUT_DIR = Path("gridvision_artifacts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Output directory:", OUTPUT_DIR.resolve())
print("Data path:", DATA_PATH.resolve())

# %% Notebook code cell 16
if not DATA_PATH.exists():
    raise FileNotFoundError(
        f"Could not find {DATA_PATH.resolve()}. Set DATA_PATH to your CSV or Parquet file."
    )

suffix = DATA_PATH.suffix.lower()
if suffix == ".csv":
    raw = pd.read_csv(DATA_PATH)
elif suffix in {".parquet", ".pq"}:
    raw = pd.read_parquet(DATA_PATH)
else:
    raise ValueError("Supported formats are CSV and Parquet.")

print("Raw shape:", raw.shape)
display(raw.head())
print("\nColumns:", raw.columns.tolist()[:25], "..." if raw.shape[1] > 25 else "")

# %% Notebook code cell 18
if TIMESTAMP_COL not in raw.columns:
    raise KeyError(f"TIMESTAMP_COL={TIMESTAMP_COL!r} not found. Available columns: {raw.columns.tolist()}")

raw = raw.copy()
raw[TIMESTAMP_COL] = pd.to_datetime(raw[TIMESTAMP_COL], errors="coerce")
bad_timestamp_rows = int(raw[TIMESTAMP_COL].isna().sum())
raw = raw.dropna(subset=[TIMESTAMP_COL]).sort_values(TIMESTAMP_COL)

print("Rows with invalid timestamps dropped:", bad_timestamp_rows)
print("Timestamp range:", raw[TIMESTAMP_COL].min(), "to", raw[TIMESTAMP_COL].max())
print("Duplicate timestamps:", int(raw[TIMESTAMP_COL].duplicated().sum()))

# Duplicate timestamp policy: stop rather than silently summing or keeping arbitrary rows.
if raw[TIMESTAMP_COL].duplicated().any():
    display(raw.loc[raw[TIMESTAMP_COL].duplicated(keep=False)].head(10))
    raise ValueError(
        "Duplicate timestamps found. Investigate whether they are duplicate records or separate readings "
        "before proceeding; do not silently aggregate them."
    )

meter_cols = [c for c in raw.columns if c != TIMESTAMP_COL]
if not meter_cols:
    raise ValueError("No meter columns found.")

# Convert meter columns to numeric; unparseable values become missing and are reported.
for c in meter_cols:
    raw[c] = pd.to_numeric(raw[c], errors="coerce")

print("Number of meter/customer columns:", len(meter_cols))
display(raw[meter_cols].describe(percentiles=[.5, .9, .95, .99]).T.head(15))

# %% Notebook code cell 20
# For 15-minute interval-energy readings, expected cadence is 15 minutes.
time_diffs = raw[TIMESTAMP_COL].diff().dropna()
print("Most common timestamp gaps:")
display(time_diffs.value_counts().head(10).rename_axis("time_gap").to_frame("count"))

numeric = raw[meter_cols]
quality_summary = pd.DataFrame({
    "missing_count": numeric.isna().sum(),
    "missing_pct": numeric.isna().mean() * 100,
    "zero_count": numeric.eq(0).sum(),
    "negative_count": numeric.lt(0).sum(),
    "max_value": numeric.max(),
    "p99_value": numeric.quantile(.99),
}).sort_values("missing_pct", ascending=False)

display(quality_summary.head(20))
print("Negative meter values:", int(numeric.lt(0).sum().sum()))

# Do not automatically convert zeros to missing: zero can be real consumption.
# Negative values are marked invalid and excluded from consumption sums.
# Extreme spikes are flagged for investigation, not automatically deleted.

# %% Notebook code cell 22
fig, axes = plt.subplots(1, 2, figsize=(14, 4))
quality_summary["missing_pct"].sort_values(ascending=False).head(25).sort_values().plot(
    kind="barh", ax=axes[0], title="Meters with highest missingness (%)"
)
numeric.stack().sample(min(100_000, int(numeric.notna().sum().sum())), random_state=RANDOM_STATE).clip(lower=0).plot(
    kind="hist", bins=80, ax=axes[1], title="Interval consumption distribution (sample)"
)
axes[1].set_xlabel("kWh per 15-minute interval")
plt.tight_layout()
plt.show()

# A compact aggregate series is useful for understanding overall data shape.
wide_plot = raw.set_index(TIMESTAMP_COL)[meter_cols]
overall_interval_kwh = wide_plot.clip(lower=0).sum(axis=1, min_count=1)
overall_daily_kwh = overall_interval_kwh.resample("D").sum(min_count=1)
overall_daily_kwh.plot(figsize=(14, 4), title="Aggregate daily consumption across all meter columns")
plt.ylabel("kWh/day across all columns")
plt.show()

# %% Notebook code cell 24
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.ensemble import IsolationForest
from xgboost import XGBRegressor

# 1. Ensure index is a datetime object for time-series operations
df.index = pd.to_datetime(df.index)

# 2. Create the primary target variable: Total Grid Load (sum of all 370 clients)
df['Total_Grid_Load'] = df.sum(axis=1)

# 3. Resample to Hourly intervals to smooth 15-min volatility for the baseline model
df_hourly = df[['Total_Grid_Load']].resample('H').sum()

# 4. Handle any missing data created during resampling
df_hourly = df_hourly.ffill()

# %% Notebook code cell 25
# Set visualization style
sns.set_theme(style="whitegrid")

# 1. Macro Trend: Plot a one-month slice of total load
plt.figure(figsize=(16, 5))
plt.plot(df_hourly['Total_Grid_Load'].loc['2012-01-01':'2012-01-31'], label='Total Hourly Load')
plt.title("Total Grid Load - January 2012")
plt.ylabel("Load (kW)")
plt.legend()
plt.show()

# %% Notebook code cell 26
# 2. Micro Trends: Extract temporal features for EDA
df_eda = df_hourly.copy()
df_eda['Hour'] = df_eda.index.hour
df_eda['DayOfWeek'] = df_eda.index.dayofweek

# 3. Hourly Seasonality Boxplot (identifying peak daily hours)
plt.figure(figsize=(12, 5))
sns.boxplot(data=df_eda, x='Hour', y='Total_Grid_Load')
plt.title("Load Distribution by Hour of Day")
plt.show()

# %% Notebook code cell 27
# 4. Weekly Seasonality Boxplot (identifying weekend drops)
plt.figure(figsize=(10, 5))
sns.boxplot(data=df_eda, x='DayOfWeek', y='Total_Grid_Load')
plt.title("Load Distribution by Day of Week (0=Monday, 6=Sunday)")
plt.show()

# %% Notebook code cell 28
# ---------------------------------------------------------
# A. PRE-PROCESSING FOR EXTENDED EDA
# ---------------------------------------------------------
df_eda = df.copy()
df_eda['Year'] = df_eda.index.year
df_eda['Month'] = df_eda.index.month
df_eda['Hour'] = df_eda.index.hour
df_eda['DayOfWeek'] = df_eda.index.dayofweek
df_eda['Total_Grid_Load'] = df.sum(axis=1)

# ---------------------------------------------------------
# B. CUSTOMER-WISE ANALYSIS
# ---------------------------------------------------------
# 1. Top 10 vs Bottom 10 Consuming Clients
customer_totals = df.sum(axis=0).sort_values(ascending=False)
top_10 = customer_totals.head(10)
bottom_10 = customer_totals.tail(10)

fig, axes = plt.subplots(1, 2, figsize=(16, 5))
sns.barplot(x=top_10.index, y=top_10.values, ax=axes[0], palette='Reds_r')
axes[0].set_title('Top 10 Highest Consuming Clients')
axes[0].set_ylabel('Total kW Consumed')
axes[0].tick_params(axis='x', rotation=45)

sns.barplot(x=bottom_10.index, y=bottom_10.values, ax=axes[1], palette='Blues')
axes[1].set_title('Bottom 10 Lowest Consuming Clients')
axes[1].set_ylabel('Total kW Consumed')
axes[1].tick_params(axis='x', rotation=45)
plt.tight_layout()
plt.show()

# %% Notebook code cell 29
# 2. Volatility Analysis (Coefficient of Variation)
# High CV = Erratic/volatile usage; Low CV = Stable baseline usage
customer_cv = (df.std(axis=0) / df.mean(axis=0)).sort_values(ascending=False)

plt.figure(figsize=(10, 5))
sns.histplot(customer_cv, bins=50, kde=True, color='teal')
plt.title('Distribution of Customer Volatility (Coefficient of Variation)')
plt.xlabel('Coefficient of Variation')
plt.ylabel('Number of Customers')
plt.show()

# %% Notebook code cell 30
# ---------------------------------------------------------
# C. TIME-WISE & YEAR-WISE ANALYSIS
# ---------------------------------------------------------
# 1. Yearly Macro Trends
yearly_load = df_eda.groupby('Year')['Total_Grid_Load'].sum()

plt.figure(figsize=(8, 5))
sns.barplot(x=yearly_load.index, y=yearly_load.values, palette='viridis')
plt.title('Total Grid Consumption by Year')
plt.ylabel('Total Load (kW)')
plt.show()

# %% Notebook code cell 31
# 2. Hourly Load Profiles by Season
df_eda['Season'] = df_eda['Month'].apply(lambda x: 'Winter' if x in [12,1,2] else
                                         ('Spring' if x in [3,4,5] else
                                          ('Summer' if x in [6,7,8] else 'Fall')))

plt.figure(figsize=(12, 6))
sns.lineplot(data=df_eda, x='Hour', y='Total_Grid_Load', hue='Season', errorbar=None, lw=2)
plt.title('Average Hourly Grid Load by Season')
plt.xticks(range(0, 24))
plt.grid(True, alpha=0.3)
plt.show()

# %% Notebook code cell 32
# 3. Heatmap: Hour of Day vs Day of Week
heatmap_data = df_eda.pivot_table(index='DayOfWeek', columns='Hour', values='Total_Grid_Load', aggfunc='mean')
heatmap_data.index = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

plt.figure(figsize=(12, 5))
sns.heatmap(heatmap_data, cmap='coolwarm', linewidths=.5)
plt.title('Heatmap of Average Load: Hour vs Day of Week')
plt.xlabel('Hour of Day')
plt.ylabel('Day of Week')
plt.show()

# %% Notebook code cell 33
# ---------------------------------------------------------
# D. ADVANCED GRID ANALYTICS
# ---------------------------------------------------------
# Load Duration Curve (Understanding base load vs peak load)
sorted_load = np.sort(df_eda['Total_Grid_Load'].dropna())[::-1]
percentiles = np.arange(1, len(sorted_load) + 1) / len(sorted_load) * 100

plt.figure(figsize=(10, 5))
plt.plot(percentiles, sorted_load, color='darkred', lw=2)
plt.fill_between(percentiles, sorted_load, color='darkred', alpha=0.1)
plt.title('Grid Load Duration Curve')
plt.xlabel('Percentage of Time Load Exceeds Value (%)')
plt.ylabel('Load (kW)')
plt.axhline(sorted_load[int(len(sorted_load)*0.05)], color='black', linestyle='--', label='Top 5% Peak Load')
plt.legend()
plt.show()

# %% Notebook code cell 35
# Keep a clean copy of raw source separate from transformations.
raw.to_parquet(OUTPUT_DIR / "raw_source_snapshot.parquet", index=False)

long_df = raw.melt(
    id_vars=[TIMESTAMP_COL],
    value_vars=meter_cols,
    var_name="household_id",
    value_name="interval_kwh"
).rename(columns={TIMESTAMP_COL: "timestamp"})

long_df["interval_kwh_original"] = long_df["interval_kwh"]
long_df["is_missing"] = long_df["interval_kwh"].isna()
long_df["is_negative"] = long_df["interval_kwh"].lt(0)
long_df["is_extreme_global_p99_9"] = (
    long_df["interval_kwh"] > long_df["interval_kwh"].quantile(0.999)
)
# Exclude negative readings from consumption sums, preserving flags for audit.
long_df.loc[long_df["is_negative"], "interval_kwh"] = np.nan
long_df["date"] = long_df["timestamp"].dt.floor("D")

print("Long table shape:", long_df.shape)
display(long_df.head())
display(long_df.groupby("household_id").agg(
    readings=("interval_kwh", "size"),
    valid_readings=("interval_kwh", "count"),
    missing_rate=("interval_kwh", lambda s: s.isna().mean()),
    negative_flag_count=("is_negative", "sum"),
).describe())

# %% Notebook code cell 37
# Because each interval is already kWh, sum the readings. No 0.25 multiplier.
daily = (
    long_df.groupby(["household_id", "date"], observed=True)
    .agg(
        daily_kwh=("interval_kwh", lambda s: s.sum(min_count=1)),
        valid_intervals=("interval_kwh", "count"),
        rows_seen=("interval_kwh", "size"),
        negative_flags=("is_negative", "sum"),
        extreme_flags=("is_extreme_global_p99_9", "sum"),
    )
    .reset_index()
)
daily["coverage_ratio"] = daily["valid_intervals"] / 96.0
daily["is_complete_day"] = daily["coverage_ratio"] >= MIN_COVERAGE_PER_DAY
daily["daily_kwh"] = daily["daily_kwh"].where(daily["daily_kwh"] >= 0)

# Important: incomplete days are not treated as fully observed days.
# For training, only use rows whose recent/current-cycle aggregates have acceptable coverage.
display(daily.head())
print("Daily rows:", len(daily))
print("Complete-day rate:", round(daily["is_complete_day"].mean(), 4))
print("Daily coverage distribution:")
display(daily["coverage_ratio"].describe())

# %% Notebook code cell 39
sample_households = daily["household_id"].drop_duplicates().head(min(6, daily["household_id"].nunique())).tolist()
fig, ax = plt.subplots(figsize=(14, 5))
for hid in sample_households:
    tmp = daily[daily["household_id"] == hid].sort_values("date")
    ax.plot(tmp["date"], tmp["daily_kwh"], alpha=.75, linewidth=1, label=str(hid))
ax.set_title("Daily consumption for sample meters")
ax.set_ylabel("kWh/day")
ax.legend(ncol=3)
plt.tight_layout()
plt.show()

eda = daily.dropna(subset=["daily_kwh"]).copy()
eda["weekday"] = eda["date"].dt.day_name()
eda["month"] = eda["date"].dt.month
weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
eda.groupby("weekday")["daily_kwh"].median().reindex(weekday_order).plot(
    kind="bar", figsize=(10, 4), title="Median daily kWh by weekday"
)
plt.ylabel("Median kWh/day")
plt.show()

eda.groupby(eda["date"].dt.month)["daily_kwh"].median().plot(
    kind="bar", figsize=(10, 4), title="Median daily kWh by calendar month (all years pooled)"
)
plt.xlabel("Month")
plt.ylabel("Median kWh/day")
plt.show()

# %% Notebook code cell 41
daily = daily.sort_values(["household_id", "date"]).reset_index(drop=True)
daily["month_start"] = daily["date"].dt.to_period("M").dt.start_time
daily["month_end"] = daily["date"].dt.to_period("M").dt.end_time.dt.floor("D")
daily["day_of_month"] = daily["date"].dt.day
daily["day_of_week"] = daily["date"].dt.dayofweek
daily["month_num"] = daily["date"].dt.month
daily["is_weekend"] = daily["day_of_week"].isin([5, 6]).astype(int)

# Missing days are made explicit per household, which makes lag/rolling windows calendar-day based.
all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
households = daily["household_id"].drop_duplicates().tolist()
full_index = pd.MultiIndex.from_product([households, all_dates], names=["household_id", "date"])
daily_full = daily.set_index(["household_id", "date"]).reindex(full_index).reset_index()

# Restore calendar and coverage columns after reindex.
daily_full["month_start"] = daily_full["date"].dt.to_period("M").dt.start_time
daily_full["month_end"] = daily_full["date"].dt.to_period("M").dt.end_time.dt.floor("D")
daily_full["day_of_month"] = daily_full["date"].dt.day
daily_full["day_of_week"] = daily_full["date"].dt.dayofweek
daily_full["month_num"] = daily_full["date"].dt.month
daily_full["is_weekend"] = daily_full["day_of_week"].isin([5, 6]).astype(int)
daily_full["coverage_ratio"] = daily_full["coverage_ratio"].fillna(0.0)
daily_full["valid_intervals"] = daily_full["valid_intervals"].fillna(0)
daily_full["is_complete_day"] = daily_full["is_complete_day"].fillna(False)

def build_origin_features(g):
    g = g.sort_values("date").copy()
    s = g["daily_kwh"]
    # Shifted windows avoid using the current day's consumption for prior-day lag features;
    # current day's consumption is allowed because the forecast is made at end of that day.
    g["lag_1d"] = s.shift(1)
    g["lag_7d"] = s.shift(7)
    g["lag_14d"] = s.shift(14)
    g["rolling_mean_3d"] = s.rolling(3, min_periods=2).mean()
    g["rolling_mean_7d"] = s.rolling(7, min_periods=5).mean()
    g["rolling_mean_14d"] = s.rolling(14, min_periods=8).mean()
    g["rolling_std_7d"] = s.rolling(7, min_periods=5).std()
    g["rolling_mean_30d"] = s.rolling(30, min_periods=10).mean()
    g["rolling_std_30d"] = s.rolling(30, min_periods=10).std()
    g["recent_vs_month_mean"] = g["rolling_mean_7d"] - g["rolling_mean_30d"]
    g["recent_vs_prior_week"] = g["rolling_mean_7d"] - s.shift(7).rolling(7, min_periods=4).mean()

    # Household profile features computed only from history through the origin date.
    g["history_mean"] = s.expanding(min_periods=7).mean()
    g["history_median"] = s.expanding(min_periods=7).median()
    g["history_p90"] = s.expanding(min_periods=7).quantile(.90)

    # Current calendar-cycle consumption through the origin, not the whole month.
    g["actual_cycle_kwh_so_far"] = s.where(g["month_start"].eq(g["month_start"].shift(1)), 0).groupby(g["month_start"]).cumsum()
    # The groupby cumsum above needs the first day of each month included; recompute robustly.
    g["actual_cycle_kwh_so_far"] = s.groupby(g["month_start"]).cumsum()

    g["elapsed_days"] = g["day_of_month"]
    g["days_remaining"] = (g["month_end"] - g["date"]).dt.days
    g["day_of_year"] = g["date"].dt.dayofyear
    g["year"] = g["date"].dt.year
    g["sin_doy"] = np.sin(2 * np.pi * g["day_of_year"] / 365.25)
    g["cos_doy"] = np.cos(2 * np.pi * g["day_of_year"] / 365.25)
    g["coverage_today"] = g["coverage_ratio"]
    g["coverage_7d_mean"] = g["coverage_ratio"].rolling(7, min_periods=1).mean()
    g["valid_intervals_7d"] = g["valid_intervals"].rolling(7, min_periods=1).sum()
    return g

features_daily = (
    daily_full.groupby("household_id", group_keys=False, observed=True)
    .apply(build_origin_features)
    .reset_index(drop=True)
)

FEATURE_COLS = [
    "lag_1d", "lag_7d", "lag_14d",
    "rolling_mean_3d", "rolling_mean_7d", "rolling_mean_14d",
    "rolling_std_7d", "rolling_mean_30d", "rolling_std_30d",
    "recent_vs_month_mean", "recent_vs_prior_week",
    "history_mean", "history_median", "history_p90",
    "actual_cycle_kwh_so_far", "elapsed_days", "days_remaining",
    "day_of_week", "is_weekend", "month_num", "day_of_year", "year",
    "sin_doy", "cos_doy", "coverage_today", "coverage_7d_mean", "valid_intervals_7d"
]
print("Feature count:", len(FEATURE_COLS))
display(features_daily[["household_id", "date"] + FEATURE_COLS].tail())

# %% Notebook code cell 43
# Fast, vectorized target generation
examples = features_daily.sort_values(
    ["household_id", "date"]
).copy()

group_cols = ["household_id", "month_start"]
groups = examples.groupby(group_cols, sort=False)

# Sum of consumption for the entire month
monthly_total = groups["daily_kwh"].transform("sum")

# Cumulative consumption up to and including the forecast date
cumulative = groups["daily_kwh"].cumsum()

# Target: consumption strictly after the forecast date
examples["target_remaining_kwh"] = monthly_total - cumulative

# Count incomplete/missing days in the future only
bad_day = (
    ~examples["is_complete_day"].fillna(False)
    | examples["daily_kwh"].isna()
).astype(int)

bad_days_so_far = (
    bad_day.groupby(
        [examples[c] for c in group_cols],
        sort=False
    ).cumsum()
)

total_bad_days = bad_day.groupby(
    [examples[c] for c in group_cols],
    sort=False
).transform("sum")

future_bad_days = total_bad_days - bad_days_so_far

examples["target_future_days"] = examples["days_remaining"]
examples["future_target_complete"] = future_bad_days.eq(0)

# Exclude invalid targets and apply the 7-day onboarding rule
first_seen = (
    daily.groupby("household_id")["date"]
    .min()
    .rename("first_seen_date")
)

examples = examples.join(first_seen, on="household_id")

examples["elapsed_since_first_seen"] = (
    examples["date"] - examples["first_seen_date"]
).dt.days + 1

examples = examples[
    (examples["day_of_month"] >= MIN_TRAIN_ORIGIN_DAY)
    & (examples["elapsed_since_first_seen"] >= MIN_TRAIN_ORIGIN_DAY)
    & examples["is_complete_day"].eq(True)
    & examples["future_target_complete"]
    & examples["target_remaining_kwh"].notna()
    & (examples["days_remaining"] > 0)
].copy()

examples = examples.replace([np.inf, -np.inf], np.nan)

print("Usable training examples:", len(examples))
print("Date range:", examples["date"].min(), "to", examples["date"].max())
print("Households represented:", examples["household_id"].nunique())

display(
    examples[
        [
            "household_id",
            "date",
            "actual_cycle_kwh_so_far",
            "target_remaining_kwh",
            "days_remaining",
        ]
    ].head()
)

# %% Notebook code cell 45
def safe_baseline_predictions(df):
    # Baseline A: average daily use observed so far × remaining days.
    elapsed = df["elapsed_days"].clip(lower=1)
    rate = df["actual_cycle_kwh_so_far"] / elapsed
    return np.maximum(0, rate * df["days_remaining"])

examples["baseline_recent_rate"] = safe_baseline_predictions(examples)
print("Baseline rows ready:", len(examples))

# %% Notebook code cell 47
examples = examples.sort_values(["date", "household_id"]).reset_index(drop=True)
unique_dates = np.array(sorted(examples["date"].dropna().unique()))
if len(unique_dates) < 10:
    raise ValueError("Not enough distinct forecast dates for chronological train/validation/test evaluation.")

n_dates = len(unique_dates)
test_n = max(1, int(round(n_dates * TEST_FRACTION_OF_DATES)))
val_n = max(1, int(round((n_dates - test_n) * VALIDATION_FRACTION_OF_REMAINING_DATES)))
train_end_idx = n_dates - test_n - val_n
if train_end_idx < 3:
    raise ValueError("Too few dates for train/validation/test split. Reduce validation/test fractions only if justified.")

train_dates = set(unique_dates[:train_end_idx])
val_dates = set(unique_dates[train_end_idx:n_dates-test_n])
test_dates = set(unique_dates[n_dates-test_n:])

train_df = examples[examples["date"].isin(train_dates)].copy()
val_df = examples[examples["date"].isin(val_dates)].copy()
test_df = examples[examples["date"].isin(test_dates)].copy()

print("Train:", train_df["date"].min(), "to", train_df["date"].max(), "| rows", len(train_df))
print("Validation:", val_df["date"].min(), "to", val_df["date"].max(), "| rows", len(val_df))
print("Test:", test_df["date"].min(), "to", test_df["date"].max(), "| rows", len(test_df))
assert train_df["date"].max() < val_df["date"].min() < test_df["date"].min()

# %% Notebook code cell 49
def make_model(name, params=None):
    params = params or {}
    if name == "Ridge":
        estimator = Ridge(**params)
        steps = [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", estimator)]
    elif name == "RandomForest":
        estimator = RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1, **params)
        steps = [("imputer", SimpleImputer(strategy="median")), ("model", estimator)]
    elif name == "HistGradientBoosting":
        estimator = HistGradientBoostingRegressor(random_state=RANDOM_STATE, **params)
        steps = [("imputer", SimpleImputer(strategy="median")), ("model", estimator)]
    elif name == "LightGBM":
        from lightgbm import LGBMRegressor
        estimator = LGBMRegressor(random_state=RANDOM_STATE, n_jobs=-1, verbosity=-1, **params)
        steps = [("imputer", SimpleImputer(strategy="median")), ("model", estimator)]
    elif name == "XGBoost":
        from xgboost import XGBRegressor
        estimator = XGBRegressor(random_state=RANDOM_STATE, n_jobs=-1, objective="reg:squarederror", **params)
        steps = [("imputer", SimpleImputer(strategy="median")), ("model", estimator)]
    else:
        raise ValueError(name)
    return Pipeline(steps)

def evaluate_remaining_and_bill(df, pred_remaining, tariff=TARIFF_INR_PER_KWH):
    pred_remaining = np.clip(np.asarray(pred_remaining, dtype=float), 0, None)
    actual_remaining = df["target_remaining_kwh"].to_numpy(dtype=float)
    actual_so_far = df["actual_cycle_kwh_so_far"].to_numpy(dtype=float)
    actual_month_kwh = actual_so_far + actual_remaining
    pred_month_kwh = actual_so_far + pred_remaining
    actual_bill = actual_month_kwh * tariff
    pred_bill = pred_month_kwh * tariff
    return {
        "remaining_MAE_kWh": mean_absolute_error(actual_remaining, pred_remaining),
        "remaining_RMSE_kWh": mean_squared_error(actual_remaining, pred_remaining) ** 0.5,
        "month_end_MAE_kWh": mean_absolute_error(actual_month_kwh, pred_month_kwh),
        "month_end_MAE_INR": mean_absolute_error(actual_bill, pred_bill),
        "month_end_RMSE_INR": mean_squared_error(actual_bill, pred_bill) ** 0.5,
        "month_end_WAPE_pct": 100 * np.sum(np.abs(actual_month_kwh - pred_month_kwh)) / max(np.sum(np.abs(actual_month_kwh)), 1e-9),
    }

X_train, y_train = train_df[FEATURE_COLS], train_df["target_remaining_kwh"]
X_val, y_val = val_df[FEATURE_COLS], val_df["target_remaining_kwh"]
X_test, y_test = test_df[FEATURE_COLS], test_df["target_remaining_kwh"]

# %% Notebook code cell 51
# Notebook-only command omitted: !pip install tqdm

# %% Notebook code cell 52
from tqdm.auto import tqdm
import time

candidate_specs = {
    "Ridge": {},
    "RandomForest": {
        "n_estimators": 250,
        "min_samples_leaf": 3,
        "max_features": 0.8
    },
    "HistGradientBoosting": {
        "max_iter": 250,
        "learning_rate": 0.06,
        "max_leaf_nodes": 15,
        "l2_regularization": 1.0
    },
}

# Optional models
try:
    import lightgbm
    candidate_specs["LightGBM"] = {
        "n_estimators": 300, "learning_rate": 0.05,
        "num_leaves": 31, "max_depth": -1
    }
except ImportError:
    print("LightGBM unavailable; skipping.")

try:
    import xgboost
    candidate_specs["XGBoost"] = {
        "n_estimators": 300, "learning_rate": 0.05,
        "max_depth": 6, "subsample": 0.9,
        "colsample_bytree": 0.9
    }
except ImportError:
    print("XGBoost unavailable; skipping.")

comparison = []

# Step 1: Baseline
print("Evaluating baseline...")
comparison.append({
    "model": "Baseline_recent_rate",
    **evaluate_remaining_and_bill(
        val_df, val_df["baseline_recent_rate"]
    )
})

fitted_candidates = {}

# Step 2: Fit and evaluate models with progress bar
with tqdm(
    candidate_specs.items(),
    total=len(candidate_specs),
    desc="Training models",
    unit="model",
    dynamic_ncols=True
) as pbar:

    for name, params in pbar:
        pbar.set_postfix_str(f"Fitting {name}")
        start = time.time()

        try:
            pipe = make_model(name, params)

            pbar.set_postfix_str(f"{name}: training")
            pipe.fit(X_train, y_train)

            pbar.set_postfix_str(f"{name}: predicting")
            pred = pipe.predict(X_val)

            pbar.set_postfix_str(f"{name}: evaluating")
            metrics = evaluate_remaining_and_bill(val_df, pred)

            fitted_candidates[name] = pipe
            comparison.append({
                "model": name,
                **metrics
            })

            tqdm.write(
                f"✓ {name} completed in {time.time() - start:.1f}s"
            )

        except Exception as e:
            tqdm.write(f"✗ {name} failed: {e}")

# Step 3: Results
comparison_df = pd.DataFrame(comparison).sort_values(
    "month_end_MAE_INR"
)

display(comparison_df)

# %% Notebook code cell 54
# Notebook-only command omitted: !pip install torch

# %% Notebook code cell 55
from tqdm.auto import tqdm
import time
import itertools
import numpy as np
import pandas as pd

# Check GPU availability
import torch

USE_CUDA = torch.cuda.is_available()
print("CUDA available:", USE_CUDA)

if USE_CUDA:
    print("GPU:", torch.cuda.get_device_name(0))


def chronological_date_folds(frame, n_splits=3, min_train_fraction=0.5):
    dates = np.array(sorted(frame["date"].dropna().unique()))

    if len(dates) < n_splits + 3:
        return []

    folds = []
    start_train_end = max(3, int(len(dates) * min_train_fraction))
    remaining = len(dates) - start_train_end
    block = max(1, remaining // n_splits)

    for i in range(n_splits):
        train_end = start_train_end + i * block
        val_end = len(dates) if i == n_splits - 1 else min(
            len(dates), train_end + block
        )

        tr_dates = set(dates[:train_end])
        va_dates = set(dates[train_end:val_end])

        if tr_dates and va_dates:
            folds.append((tr_dates, va_dates))

    return folds


def tune_candidates(trainval_df):
    available = trainval_df.attrs.get("available_models", [])

    grids = {
        # "RandomForest": [
        #     {
        #         "n_estimators": n,
        #         "max_depth": depth,
        #         "min_samples_leaf": leaf,
        #         "max_features": 0.8
        #     }
        #     for n, depth, leaf in itertools.product(
        #         [100, 200], [12, 24], [2, 5]
        #     )
        # ]
    }

    if "XGBoost" in available:
        grids["XGBoost"] = [
            {
                "n_estimators": n,
                "learning_rate": lr,
                "max_depth": depth,
                "subsample": 0.9,
                "colsample_bytree": 0.9,
                **(
                    {"tree_method": "hist", "device": "cuda"}
                    if USE_CUDA else {"tree_method": "hist"}
                )
            }
            for n, lr, depth in itertools.product(
                [100, 200], [0.03, 0.06], [4, 6]
            )
        ]

    if "LightGBM" in available:
        grids["LightGBM"] = [
            {
                "n_estimators": n,
                "learning_rate": lr,
                "num_leaves": leaves,
                "max_depth": -1,
                **({"device": "gpu"} if USE_CUDA else {})
            }
            for n, lr, leaves in itertools.product(
                [100, 200], [0.03, 0.06], [15, 31]
            )
        ]

    folds = chronological_date_folds(trainval_df, n_splits=3)

    if not folds:
        print("Not enough dates for chronological tuning.")
        return pd.DataFrame(), None, grids

    fold_data = []

    for tr_dates, va_dates in folds:
        tr = trainval_df[trainval_df["date"].isin(tr_dates)]
        va = trainval_df[trainval_df["date"].isin(va_dates)]

        if not tr.empty and not va.empty:
            fold_data.append((tr, va))

    if not fold_data:
        print("No valid training/validation folds.")
        return pd.DataFrame(), None, grids

    total_configs = sum(len(params) for params in grids.values())
    total_fits = total_configs * len(fold_data)

    print("Models:", list(grids.keys()))
    print("Parameter configurations:", total_configs)
    print("Total model fits:", total_fits)
    print("GPU acceleration applies to supported XGBoost/LightGBM models.")

    results = []
    start_all = time.time()

    with tqdm(
        total=total_fits,
        desc="Hyperparameter tuning",
        unit="fit",
        dynamic_ncols=True
    ) as pbar:

        for name, param_list in grids.items():
            for config_num, params in enumerate(param_list, start=1):
                fold_scores = []
                config_start = time.time()

                for fold_idx, (tr, va) in enumerate(fold_data, start=1):
                    pbar.set_postfix_str(
                        f"{name} | config {config_num}/{len(param_list)} "
                        f"| fold {fold_idx}/{len(fold_data)}"
                    )

                    try:
                        model = make_model(name, params)

                        model.fit(
                            tr[FEATURE_COLS],
                            tr["target_remaining_kwh"]
                        )

                        pred = np.clip(
                            model.predict(va[FEATURE_COLS]), 0, None
                        )

                        score = evaluate_remaining_and_bill(
                            va, pred
                        )["month_end_MAE_INR"]

                        fold_scores.append(score)

                    except Exception as e:
                        tqdm.write(
                            f"Failed: {name}, {params}, "
                            f"fold {fold_idx}: {e}"
                        )
                    finally:
                        pbar.update(1)

                if fold_scores:
                    results.append({
                        "model": name,
                        "params": params,
                        "cv_mean_month_end_MAE_INR": float(
                            np.mean(fold_scores)
                        ),
                        "cv_std_month_end_MAE_INR": float(
                            np.std(fold_scores)
                        ),
                        "folds_scored": len(fold_scores),
                        "config_time_sec": round(
                            time.time() - config_start, 1
                        )
                    })

    results_df = pd.DataFrame(results)

    if results_df.empty:
        print("No configurations completed successfully.")
        return results_df, None, grids

    results_df = results_df.sort_values(
        "cv_mean_month_end_MAE_INR"
    ).reset_index(drop=True)

    best = results_df.iloc[0]

    print(f"\nTuning completed in {(time.time() - start_all) / 60:.1f} minutes.")

    return results_df, best, grids


trainval_df = (
    pd.concat([train_df, val_df], ignore_index=True)
    .sort_values(["date", "household_id"])
)

trainval_df.attrs["available_models"] = list(candidate_specs.keys())

tuning_results, best_tuning_row, searched_grids = tune_candidates(trainval_df)

display(tuning_results.head(15))

if best_tuning_row is not None:
    print("\nBest model:", best_tuning_row["model"])
    print("Best parameters:", best_tuning_row["params"])
    print(
        "Best CV month-end MAE (₹):",
        round(best_tuning_row["cv_mean_month_end_MAE_INR"], 2)
    )

# %% Notebook code cell 57
if best_tuning_row is not None:
    best_name = best_tuning_row["model"]
    best_params = best_tuning_row["params"]
else:
    # Fallback when there are too few dates for multi-fold tuning:
    # select the best untuned validation model, excluding the test period.
    best_name = comparison_df.loc[comparison_df["model"] != "Baseline_recent_rate"].iloc[0]["model"]
    best_params = candidate_specs[best_name]

final_train_df = pd.concat([train_df, val_df], ignore_index=True).sort_values(["date", "household_id"])
final_model = make_model(best_name, best_params)
final_model.fit(final_train_df[FEATURE_COLS], final_train_df["target_remaining_kwh"])

test_pred = np.clip(final_model.predict(X_test), 0, None)
test_metrics = evaluate_remaining_and_bill(test_df, test_pred)
baseline_metrics = evaluate_remaining_and_bill(test_df, test_df["baseline_recent_rate"])
print("Selected model:", best_name)
print("Parameters:", best_params)
print("\nHeld-out test metrics:")
display(pd.DataFrame([
    {"model": "Selected_ML", **test_metrics},
    {"model": "Baseline_recent_rate", **baseline_metrics},
]))

# %% Notebook code cell 59
test_results = test_df[["household_id", "date", "month_start", "month_end", "day_of_month",
                        "actual_cycle_kwh_so_far", "target_remaining_kwh", "days_remaining"]].copy()
test_results["predicted_remaining_kwh"] = test_pred
test_results["actual_month_end_kwh"] = test_results["actual_cycle_kwh_so_far"] + test_results["target_remaining_kwh"]
test_results["predicted_month_end_kwh"] = test_results["actual_cycle_kwh_so_far"] + test_results["predicted_remaining_kwh"]
test_results["actual_bill_inr"] = test_results["actual_month_end_kwh"] * TARIFF_INR_PER_KWH
test_results["predicted_bill_inr"] = test_results["predicted_month_end_kwh"] * TARIFF_INR_PER_KWH
test_results["absolute_bill_error_inr"] = (test_results["actual_bill_inr"] - test_results["predicted_bill_inr"]).abs()

fig, axes = plt.subplots(1, 2, figsize=(13, 4))
axes[0].scatter(test_results["actual_month_end_kwh"], test_results["predicted_month_end_kwh"], alpha=.25)
lims = [
    min(test_results["actual_month_end_kwh"].min(), test_results["predicted_month_end_kwh"].min()),
    max(test_results["actual_month_end_kwh"].max(), test_results["predicted_month_end_kwh"].max())
]
axes[0].plot(lims, lims, linestyle="--")
axes[0].set_xlabel("Actual month-end kWh")
axes[0].set_ylabel("Predicted month-end kWh")
axes[0].set_title("Actual vs predicted month-end consumption")

test_results.groupby("day_of_month")["absolute_bill_error_inr"].mean().plot(ax=axes[1], marker="o")
axes[1].set_title("Mean absolute bill error by forecast day")
axes[1].set_xlabel("Forecast origin day of month")
axes[1].set_ylabel("MAE (₹)")
plt.tight_layout()
plt.show()

display(test_results.groupby("household_id")["absolute_bill_error_inr"].agg(["count", "mean", "median"]).sort_values("mean", ascending=False).head(15))

# %% Notebook code cell 61
# Bundle feature order and assumptions with the model so the API can validate inputs.
artifact = {
    "model": final_model,
    "model_name": best_name,
    "model_params": best_params,
    "feature_columns": FEATURE_COLS,
    "target_name": "target_remaining_kwh",
    "tariff_inr_per_kwh": TARIFF_INR_PER_KWH,
    "timestamp_col": TIMESTAMP_COL,
    "interval_minutes": 15,
    "interval_unit": "kWh per 15-minute interval",
    "daily_aggregation": "sum",
    "billing_cycle": "calendar_month",
    "minimum_elapsed_days_before_prediction": MIN_TRAIN_ORIGIN_DAY,
    "minimum_daily_coverage_ratio": MIN_COVERAGE_PER_DAY,
    "test_metrics": test_metrics,
    "baseline_test_metrics": baseline_metrics,
    "training_date_min": str(final_train_df["date"].min()),
    "training_date_max": str(final_train_df["date"].max()),
    "created_utc": pd.Timestamp.utcnow().isoformat(),
    "notes": [
        "Prediction target is future consumption after forecast-origin date through calendar month-end.",
        "Month-end bill is calculated outside the model from actual_cycle_kwh_so_far + predicted_remaining_kwh.",
        "₹10/kWh is a prototype tariff and excludes fixed charges, taxes, slabs and utility adjustments.",
        "The feature-generation logic must be versioned and reused by the API."
    ]
}

model_path = OUTPUT_DIR / "gridvision_month_end_model.pkl"
with open(model_path, "wb") as f:
    pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)

metadata_path = OUTPUT_DIR / "gridvision_model_metadata.json"
metadata = {k: v for k, v in artifact.items() if k not in {"model", "feature_columns"}}
metadata["feature_columns"] = FEATURE_COLS
# Convert NumPy scalar / non-JSON values safely.
def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return float(obj)
    if isinstance(obj, (pd.Timestamp,)): return obj.isoformat()
    if isinstance(obj, (np.ndarray,)): return obj.tolist()
    if isinstance(obj, (np.bool_,)): return bool(obj)
    if isinstance(obj, Path): return str(obj)
    if obj is None or isinstance(obj, (str, int, float, bool)): return obj
    return str(obj)

with open(metadata_path, "w", encoding="utf-8") as f:
    json.dump(json_safe(metadata), f, indent=2)

print("Saved model:", model_path.resolve())
print("Saved metadata:", metadata_path.resolve())

# %% Notebook code cell 63
with open(model_path, "rb") as f:
    loaded_artifact = pickle.load(f)

loaded_model = loaded_artifact["model"]
loaded_features = loaded_artifact["feature_columns"]
assert loaded_features == FEATURE_COLS

sample_X = test_df[loaded_features].head(10)
pred_before = final_model.predict(sample_X)
pred_after = loaded_model.predict(sample_X)
print("Maximum reload prediction difference:", float(np.max(np.abs(pred_before - pred_after))))
print("Sample predicted remaining kWh:", np.clip(pred_after, 0, None)[:5])

