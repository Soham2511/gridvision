# Generated from the corresponding notebook's code cells.
# Review before execution; notebook cells were not all executed.
# Notebook shell commands are retained as comments, not run.
# ruff: noqa
from __future__ import annotations

# %% Notebook code cell 2
# [Cell 1: Dependencies & Environment Setup]
# Optional package installations (uncomment if running in a fresh environment)
# !pip install -q xgboost "lightgbm==4.6.0" optuna scikit-learn matplotlib seaborn

import os
import sys

# Critical OpenMP settings for Windows stability and DLL conflict prevention
os.environ['OMP_NUM_THREADS'] = '4'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

print('Environment configured for multi-threaded LightGBM training on Windows.')

# %% Notebook code cell 4
# [Cell 2: Imports & Global Configuration]
# Import LightGBM first to avoid Windows memory access violations
import lightgbm as lgb

import gc
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None

warnings.filterwarnings('ignore')
sns.set_theme(style='whitegrid')
plt.rcParams['figure.figsize'] = (14, 6)
plt.rcParams['font.size'] = 11

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
print(f'LightGBM Version: {lgb.__version__}')
print(f'Optuna Available: {optuna is not None}')

# %% Notebook code cell 6
# [Cell 3: Project Paths & Memory-Optimized Dataset Loading]
current_dir = Path('.').resolve()
if (current_dir / 'Data').is_dir():
    PROJECT_ROOT = current_dir
elif (current_dir.parent / 'Data').is_dir():
    PROJECT_ROOT = current_dir.parent
elif (current_dir.parent.parent / 'Data').is_dir():
    PROJECT_ROOT = current_dir.parent.parent
else:
    PROJECT_ROOT = current_dir

# Configurable row limit for fast development (set LOAD_SAMPLE_ROWS = None to load full dataset)
LOAD_SAMPLE_ROWS = 500000

# Select optimal storage engine based on partition mode
CSV_FILE = PROJECT_ROOT / 'Data' / 'Preprocessed' / 'CP-2' / 'building_demand.csv'
PARQUET_FILE = PROJECT_ROOT / 'Data' / 'Preprocessed' / 'CP-2' / 'building_demand.parquet'

if LOAD_SAMPLE_ROWS is not None and CSV_FILE.exists():
    DATA_FILE = CSV_FILE
elif PARQUET_FILE.exists():
    DATA_FILE = PARQUET_FILE
else:
    DATA_FILE = CSV_FILE

print(f'Loading building dataset from: {DATA_FILE}')
t0 = time.time()

# Memory-optimized dtype specification for fast loading
DTYPE_DICT = {
    'building_id': 'category',
    'site_id': 'category',
    'primaryspaceusage': 'category',
    'sub_primaryspaceusage': 'category',
    'sqm': 'float32',
    'numberoffloors': 'int16',
    'occupants': 'int16',
    'yearbuilt': 'int16',
    'chilledwater': 'int8',
    'gas': 'int8',
    'solar': 'int8',
    'airTemperature': 'float32',
    'relative_humidity_pct': 'float32',
    'cloudCoverage': 'float32',
    'windSpeed': 'float32',
    'is_weekend': 'int8',
    'is_business_hours': 'int8',
    'season': 'category',
    'hour_sin': 'float32',
    'hour_cos': 'float32',
    'dayofweek_sin': 'float32',
    'dayofweek_cos': 'float32',
    'month_sin': 'float32',
    'month_cos': 'float32',
    'cooling_degree_hours': 'float32',
    'heating_degree_hours': 'float32',
    'temp_lag_1h': 'float32',
    'temp_lag_24h': 'float32',
    'demand_lag_1h': 'float32',
    'demand_lag_2h': 'float32',
    'demand_lag_24h': 'float32',
    'demand_lag_48h': 'float32',
    'demand_lag_168h': 'float32',
    'demand_rolling_mean_6h': 'float32',
    'demand_rolling_std_6h': 'float32',
    'demand_rolling_mean_24h': 'float32',
    'demand_rolling_std_24h': 'float32',
    'demand_rolling_mean_168h': 'float32',
    'demand_rolling_std_168h': 'float32',
    'hourly_demand_kwh': 'float32',
    'timestamp': 'category',
    'split_set': 'category'
}

if str(DATA_FILE).endswith('.csv'):
    if LOAD_SAMPLE_ROWS is not None:
        print(f'Loading representative training partition ({LOAD_SAMPLE_ROWS:,} rows) via streaming CSV...')
        df = pd.read_csv(DATA_FILE, nrows=LOAD_SAMPLE_ROWS, dtype=DTYPE_DICT)
    else:
        print('Loading full 24.5M rows portfolio dataset from CSV...')
        df = pd.read_csv(DATA_FILE, dtype=DTYPE_DICT)
else:
    if LOAD_SAMPLE_ROWS is not None:
        print(f'Loading representative training partition ({LOAD_SAMPLE_ROWS:,} rows) from parquet...')
        df = pd.read_parquet(DATA_FILE)
        if len(df) > LOAD_SAMPLE_ROWS:
            df = df.iloc[:LOAD_SAMPLE_ROWS]
    else:
        print('Loading full portfolio parquet dataset...')
        df = pd.read_parquet(DATA_FILE)
    df = df.astype({c: dt for c, dt in DTYPE_DICT.items() if c in df.columns})

print(f'Dataset Loaded: {df.shape[0]:,} rows x {df.shape[1]} columns in {time.time()-t0:.2f}s')
print(f'Memory usage:   {df.memory_usage().sum() / (1024**2):.2f} MB')

# %% Notebook code cell 8
# [Cell 4: Exploratory Data Analysis & Basic Data Details]
print('=== 1. DATASET PROFILE & NULL COUNTS ===')
display(pd.DataFrame({
    'Column': df.columns,
    'Data Type': df.dtypes,
    'Nulls': df.isnull().sum(),
    'Unique Count': df.nunique()
}).reset_index(drop=True))

print('\n=== 2. PRIMARY SPACE USAGE DISTRIBUTION ===')
print(df['primaryspaceusage'].value_counts())

print('\n=== 3. UTILITY SERVICE CARRIER AVAILABILITY ===')
print('Chilled Water Service: {:.1f}% of buildings'.format(df['chilledwater'].mean() * 100))
print('Natural Gas Service:    {:.1f}% of buildings'.format(df['gas'].mean() * 100))
print('Solar PV Generation:    {:.1f}% of buildings'.format(df['solar'].mean() * 100))

print('\n=== 4. NUMERICAL DESCRIPTIVE STATISTICS ===')
display(df.describe().T.round(2))

# %% Notebook code cell 10
# [Cell 5: Target Distribution & Pearson Correlation with Features]
TARGET_COL = 'hourly_demand_kwh'

print(f'=== TARGET SUMMARY: {TARGET_COL} ===')
print(f'Mean Demand:   {df[TARGET_COL].mean():.2f} kWh')
print(f'Median Demand: {df[TARGET_COL].median():.2f} kWh')
print(f'Peak Demand:   {df[TARGET_COL].max():.2f} kWh')
print(f'Std Deviation: {df[TARGET_COL].std():.2f} kWh')

# Numerical correlation with target
num_cols = df.select_dtypes(include=[np.number]).columns.drop(TARGET_COL, errors='ignore')
correlations = df[num_cols].apply(lambda s: s.corr(df[TARGET_COL])).sort_values(ascending=False)

print('\n=== TOP 10 CORRELATED PREDICTORS ===')
print(correlations.head(10).round(4))

# Visual Correlation Barplot
plt.figure(figsize=(14, 6))
correlations.plot(kind='bar', color='#0284c7')
plt.title('Predictor Pearson Correlation with Hourly Building Demand (hourly_demand_kwh)', fontsize=13, fontweight='bold')
plt.ylabel('Correlation Coefficient')
plt.xticks(rotation=60, ha='right')
plt.tight_layout()
plt.show()

# %% Notebook code cell 12
# [Cell 6: Chronological Train / Validation / Test Splitting]
TARGET_COL = 'hourly_demand_kwh'
EXCLUDE_COLS = [TARGET_COL, 'timestamp', 'split_set']
FEATURE_COLS = [c for c in df.columns if c not in EXCLUDE_COLS]

CATEGORICAL_COLS = [c for c in FEATURE_COLS if df[c].dtype.name == 'category']
print(f'Categorical Features ({len(CATEGORICAL_COLS)}): {CATEGORICAL_COLS}')

# Use predefined split_set if available and complete, otherwise chronological partition
if 'split_set' in df.columns and set(df['split_set'].unique()).issuperset({'train', 'val', 'test'}):
    X_train = df[df['split_set'] == 'train'][FEATURE_COLS].copy()
    y_train = df[df['split_set'] == 'train'][TARGET_COL].copy()
    X_val   = df[df['split_set'] == 'val'][FEATURE_COLS].copy()
    y_val   = df[df['split_set'] == 'val'][TARGET_COL].copy()
    X_test  = df[df['split_set'] == 'test'][FEATURE_COLS].copy()
    y_test  = df[df['split_set'] == 'test'][TARGET_COL].copy()
else:
    n_rows = len(df)
    train_end_idx = int(n_rows * 0.75)
    val_end_idx = int(n_rows * 0.875)
    X_train = df.iloc[:train_end_idx][FEATURE_COLS].copy()
    y_train = df.iloc[:train_end_idx][TARGET_COL].copy()
    X_val = df.iloc[train_end_idx:val_end_idx][FEATURE_COLS].copy()
    y_val = df.iloc[train_end_idx:val_end_idx][TARGET_COL].copy()
    X_test = df.iloc[val_end_idx:][FEATURE_COLS].copy()
    y_test = df.iloc[val_end_idx:][TARGET_COL].copy()

print(f'Train Partition: {X_train.shape[0]:,} rows')
print(f'Val Partition:   {X_val.shape[0]:,} rows')
print(f'Test Partition:  {X_test.shape[0]:,} rows')
print(f'Feature Count:   {len(FEATURE_COLS)} predictors')

# %% Notebook code cell 14
# [Cell 7: Model Evaluation Helper & Metrics Engine]
results_registry = {}

def evaluate_predictions(y_true, y_pred, model_name='Model'):
    y_true = np.array(y_true, dtype=np.float64)
    y_pred = np.array(y_pred, dtype=np.float64)
    
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mae = mean_absolute_error(y_true, y_pred)
    
    epsilon = 1e-4
    mape = np.mean(np.abs((y_true - y_pred) / (y_true + epsilon))) * 100
    r2 = r2_score(y_true, y_pred)
    wape = (np.sum(np.abs(y_true - y_pred)) / (np.sum(y_true) + epsilon)) * 100
    
    peak_threshold = np.quantile(y_true, 0.90)
    peak_idx = y_true >= peak_threshold
    peak_mae = mean_absolute_error(y_true[peak_idx], y_pred[peak_idx]) if np.any(peak_idx) else np.nan
    
    metrics = {
        'RMSE (kWh)': round(rmse, 2),
        'MAE (kWh)': round(mae, 2),
        'MAPE (%)': round(min(mape, 100.0), 2),
        'R2 Score': round(r2, 4),
        'WAPE (%)': round(wape, 2),
        'Peak MAE (kWh)': round(peak_mae, 2)
    }
    
    print(f'=== {model_name} EVALUATION METRICS ===')
    for k, v in metrics.items():
        print(f'  {k:<16}: {v}')
    
    results_registry[model_name] = metrics
    return metrics

# %% Notebook code cell 16
# [Cell 8: LightGBM Regressor Baseline Training]
# Ensure non-feature metadata columns are cleanly stripped
drop_meta = [c for c in ['timestamp', 'split_set', TARGET_COL] if c in X_train.columns]
if drop_meta:
    X_train = X_train.drop(columns=drop_meta)
    X_val   = X_val.drop(columns=drop_meta)
    X_test  = X_test.drop(columns=drop_meta)

print('=== TRAINING BASELINE LIGHTGBM REGRESSOR ===')
print(f'Training Matrix Shape: {X_train.shape}')
t_start = time.time()

lgb_baseline = lgb.LGBMRegressor(
    n_estimators=1000,
    learning_rate=0.04,
    num_leaves=63,
    max_depth=8,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=RANDOM_SEED,
    n_jobs=4,
    force_row_wise=True
)

lgb_baseline.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
)

print(f'Training completed in {time.time()-t_start:.2f} seconds!')
print(f'Best Iteration: {lgb_baseline.best_iteration_}')

preds_baseline = lgb_baseline.predict(X_test)
metrics_baseline = evaluate_predictions(y_test, preds_baseline, model_name='LightGBM (Baseline)')

# %% Notebook code cell 18
# [Cell 9: Feature Importance Diagnostics]
importance_df = pd.DataFrame({
    'Feature': X_train.columns,
    'Importance': lgb_baseline.feature_importances_
}).sort_values('Importance', ascending=False)

print('=== TOP 10 MOST INFLUENTIAL FEATURES ===')
display(importance_df.head(10))

# Plot Feature Importance
plt.figure(figsize=(12, 7))
top20 = importance_df.head(20)
sns.barplot(data=top20, x='Importance', y='Feature', palette='viridis')
plt.title('Top 20 Feature Importances (LightGBM Split Gain)', fontsize=13, fontweight='bold')
plt.xlabel('Importance Score')
plt.tight_layout()
plt.show()

# %% Notebook code cell 20
# [Cell 10: Bayesian Hyperparameter Fine-Tuning with Optuna]
if optuna is not None:
    def objective(trial):
        params = {
            'n_estimators': 300,
            'learning_rate': trial.suggest_float('learning_rate', 0.02, 0.12, log=True),
            'num_leaves': trial.suggest_int('num_leaves', 31, 127),
            'max_depth': trial.suggest_int('max_depth', 5, 12),
            'subsample': trial.suggest_float('subsample', 0.65, 0.95),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.65, 0.95),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 5.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 5.0, log=True),
            'random_state': RANDOM_SEED,
            'n_jobs': 4,
            'force_row_wise': True,
            'verbose': -1
        }
        
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)]
        )
        val_preds = model.predict(X_val)
        return np.sqrt(mean_squared_error(y_val, val_preds))
    
    print('Starting 15 trials of Bayesian Hyperparameter Optimization...')
    t_optuna = time.time()
    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=15)
    
    print(f'\nOptuna optimization finished in {time.time()-t_optuna:.2f}s!')
    print(f'Best Validation RMSE: {study.best_value:.2f} kWh')
    print('Optimal Hyperparameters:', study.best_params)
    
    # Retrain champion model with optimal hyperparameters
    best_params = study.best_params
    best_params['n_estimators'] = 1200
    best_params['random_state'] = RANDOM_SEED
    best_params['n_jobs'] = 4
    best_params['force_row_wise'] = True
    
    print('\nTraining Final Champion Model with Best Parameters...')
    lgb_tuned = lgb.LGBMRegressor(**best_params)
    lgb_tuned.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
    )
    
    preds_tuned = lgb_tuned.predict(X_test)
    metrics_tuned = evaluate_predictions(y_test, preds_tuned, model_name='LightGBM (Tuned Champion)')
else:
    print('Optuna not installed. Run !pip install optuna to enable automated Bayesian tuning.')
    lgb_tuned = lgb_baseline
    preds_tuned = preds_baseline

# %% Notebook code cell 22
# [Cell 11: Performance Comparison Table & Leaderboard]
df_leaderboard = pd.DataFrame(results_registry).T
df_leaderboard = df_leaderboard.sort_values('RMSE (kWh)', ascending=True)

print('=== MODEL PERFORMANCE COMPARISON ===')
display(df_leaderboard.style.highlight_min(subset=['RMSE (kWh)', 'MAE (kWh)', 'MAPE (%)', 'WAPE (%)', 'Peak MAE (kWh)'], color='#dcfce7')
                           .highlight_max(subset=['R2 Score'], color='#dcfce7'))

# %% Notebook code cell 24
# [Cell 12: Visual Benchmark - Actual vs Predicted Test Curves]
PLOT_HOURS = 168 # 7 days continuous timeline

plt.figure(figsize=(16, 6))
actual_sample = y_test.values[:PLOT_HOURS]
plt.plot(actual_sample, label='Ground Truth (Actual Demand)', color='black', linewidth=2.2, alpha=0.9)

if 'preds_baseline' in locals():
    plt.plot(preds_baseline[:PLOT_HOURS], label='LightGBM (Baseline)', linestyle='--', alpha=0.8, color='#3b82f6')
if 'preds_tuned' in locals():
    plt.plot(preds_tuned[:PLOT_HOURS], label='LightGBM (Tuned Champion)', color='#10b981', linewidth=2.0)

plt.title('7-Day (168-Hour) Test Horizon: Building Demand Forecast vs Actual Usage', fontsize=14, fontweight='bold')
plt.xlabel('Hours in Test Horizon')
plt.ylabel('Hourly Demand (kWh)')
plt.legend(loc='upper right', frameon=True)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# %% Notebook code cell 26
# [Cell 13: Error Distribution & Peak Period Diagnostics]
fig, axes = plt.subplots(1, 2, figsize=(16, 5))

# 1. Residual KDE plot
residuals = y_test.values - preds_tuned
sns.kdeplot(residuals, ax=axes[0], fill=True, color='#0284c7', alpha=0.4)
axes[0].axvline(0, color='red', linestyle='--', alpha=0.8)
axes[0].set_title('Prediction Residual Distribution (Actual - Predicted)')
axes[0].set_xlabel('Residual Error (kWh)')
axes[0].set_ylabel('Density')

# 2. Peak vs Overall MAE
overall_mae = mean_absolute_error(y_test, preds_tuned)
peak_threshold = np.quantile(y_test, 0.90)
peak_mask = y_test.values >= peak_threshold
peak_mae = mean_absolute_error(y_test.values[peak_mask], preds_tuned[peak_mask])

axes[1].bar(['Overall MAE', 'Peak Period MAE (Top 10% Load)'], [overall_mae, peak_mae], color=['#3b82f6', '#ef4444'])
axes[1].set_title('Overall Accuracy vs Peak Period Accuracy')
axes[1].set_ylabel('Mean Absolute Error (kWh)')
for i, v in enumerate([overall_mae, peak_mae]):
    axes[1].text(i, v + 0.5, f'{v:.2f} kWh', ha='center', fontweight='bold')

plt.tight_layout()
plt.show()

# %% Notebook code cell 28
# [Cell 14: Full-Dataset Retraining of Champion Model for Production Deployment]
print('=== RETRAINING BUILDING FORECASTING MODEL ON ENTIRE DATASET ===')

# 1. Assemble complete feature matrix and target across train, val, and test
X_full = df[FEATURE_COLS].copy()
y_full = df[TARGET_COL].copy()

# Ensure non-feature metadata columns are cleanly stripped
drop_meta = [c for c in ['timestamp', 'split_set', TARGET_COL] if c in X_full.columns]
if drop_meta:
    X_full = X_full.drop(columns=drop_meta)

print(f'Full Dataset Matrix: {X_full.shape[0]:,} rows x {X_full.shape[1]} features (100% of dataset)')

# 2. Configure production model using optimal hyperparameters and locked iteration count
production_params = lgb_tuned.get_params()
optimal_trees = getattr(lgb_tuned, 'best_iteration_', 144) or 144
production_params['n_estimators'] = optimal_trees
production_params.pop('early_stopping_round', None)

print(f'Fitting production LightGBM with locked n_estimators={optimal_trees} on all {len(X_full):,} rows...')
t_retrain = time.time()
lgb_production = lgb.LGBMRegressor(**production_params)
lgb_production.fit(X_full, y_full)
print(f'Production building model successfully trained in {time.time()-t_retrain:.2f}s!')

# %% Notebook code cell 30
# [Cell 15: Model Serialization & Production Champion Export]
import pickle

MODELS_DIR = PROJECT_ROOT / 'Models' / 'CP-2'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILE = MODELS_DIR / 'building_model.pkl'
with open(MODEL_FILE, 'wb') as f:
    pickle.dump(lgb_production, f)

print('Production building forecasting model successfully saved!')
print(f'-> Destination:      {MODEL_FILE}')
print(f'-> Model Class:      {type(lgb_production).__name__}')
print(f'-> Training Records: {len(X_full):,} rows (100% full dataset)')
print(f'-> File Size:        {MODEL_FILE.stat().st_size / (1024**2):.2f} MB')
print(f'-> Features:         {lgb_production.n_features_in_} predictors')

