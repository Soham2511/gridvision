# Generated from the corresponding notebook's code cells.
# Review before execution; notebook cells were not all executed.
# Notebook shell commands are retained as comments, not run.
# ruff: noqa
from __future__ import annotations

# %% Notebook code cell 2
# [Cell 1: Dependencies Installation]
# Pins stable lightgbm==4.6.0 to avoid the Windows 4.7.0 access violation regression
# Notebook-only command omitted: !pip install -q xgboost "lightgbm==4.6.0" catboost optuna torch statsmodels scikit-learn matplotlib seaborn

# %% Notebook code cell 4
# [Cell 2: Imports & Global Configuration]
import os
import sys

# Critical OpenMP settings for Windows stability and DLL conflict prevention
os.environ['OMP_NUM_THREADS'] = '4'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# Import LightGBM first before other C-extensions to prevent Windows memory access violations
import lightgbm as lgb
import xgboost as xgb
try:
    import catboost as cb
except ImportError:
    cb = None

import gc
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Sklearn utilities & metrics
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.ensemble import RandomForestRegressor

# Statistical time series
try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
except ImportError:
    SARIMAX = None

# Deep Learning (PyTorch)
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

# Hyperparameter Optimization
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None

warnings.filterwarnings('ignore')
sns.set_theme(style='whitegrid')
plt.rcParams['figure.figsize'] = (14, 6)
plt.rcParams['font.size'] = 11

# Reproducibility seed & device selection
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'Execution Device: {DEVICE}')
print(f'PyTorch Version:  {torch.__version__}')

# %% Notebook code cell 6
# [Cell 3: Project Paths & Dataset Loading]
current_dir = Path('.').resolve()
if (current_dir / 'Data').is_dir():
    PROJECT_ROOT = current_dir
elif (current_dir.parent / 'Data').is_dir():
    PROJECT_ROOT = current_dir.parent
elif (current_dir.parent.parent / 'Data').is_dir():
    PROJECT_ROOT = current_dir.parent.parent
else:
    PROJECT_ROOT = current_dir

DATA_FILE = PROJECT_ROOT / 'Data' / 'Preprocessed' / 'CP-2' / 'site_demand_cp2.parquet'
if not DATA_FILE.exists():
    DATA_FILE = PROJECT_ROOT / 'Data' / 'Preprocessed' / 'CP-2' / 'site_demand_cp2.csv'
if not DATA_FILE.exists():
    DATA_FILE = PROJECT_ROOT / 'Data' / 'Preprocessed' / 'site_demand_preprocessed.csv'

print(f'Loading preprocessed dataset from: {DATA_FILE}')
if str(DATA_FILE).endswith('.parquet'):
    df = pd.read_parquet(DATA_FILE)
else:
    df = pd.read_csv(DATA_FILE)
if 'timestamp' in df.columns:
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values(['site_id', 'timestamp']).reset_index(drop=True)

print(f'Dataset Loaded: {df.shape[0]:,} rows x {df.shape[1]} columns')
print(f'1st Column: {df.columns[0]}')

# %% Notebook code cell 8
# [Cell 4: Exploratory Data Details & Schema Overview]
print('=== 1. DATASET SHAPE & COLUMN TYPES ===')
display(pd.DataFrame({
    'Column': df.columns,
    'Data Type': df.dtypes,
    'Null Count': df.isnull().sum(),
    'Unique Values': df.nunique()
}).reset_index(drop=True))

print('\n=== 2. NUMERICAL FEATURE DESCRIPTIVE STATISTICS ===')
display(df.describe().T.round(2))

print('\n=== 3. SITE PORTFOLIO VALUE COUNTS ===')
site_counts = df['site_id'].value_counts()
print(site_counts)

# %% Notebook code cell 10
# [Cell 5: Target ($) Distribution & Feature Correlation]
TARGET_COL = 'total_demand_kwh'

# 1. Target distribution metrics
print(f'=== TARGET STATS: {TARGET_COL} ===')
print(f'Mean:   {df[TARGET_COL].mean():.2f} kWh')
print(f'Median: {df[TARGET_COL].median():.2f} kWh')
print(f'Std:    {df[TARGET_COL].std():.2f} kWh')
print(f'Min:    {df[TARGET_COL].min():.2f} kWh')
print(f'Max:    {df[TARGET_COL].max():.2f} kWh')

# 2. Correlation of numerical features with Target
num_cols = df.select_dtypes(include=[np.number]).columns.drop(TARGET_COL, errors='ignore')
correlations = df[num_cols].apply(lambda s: s.corr(df[TARGET_COL])).sort_values(ascending=False)

print('\n=== TOP 10 CORRELATED FEATURES WITH DEMAND ===')
print(correlations.head(10).round(4))

# Correlation Barplot
plt.figure(figsize=(12, 6))
correlations.plot(kind='bar', color='#3b82f6')
plt.title('Feature Pearson Correlation with Target (total_demand_kwh)')
plt.ylabel('Correlation Coefficient')
plt.xticks(rotation=60, ha='right')
plt.tight_layout()
plt.show()

# %% Notebook code cell 12
# [Cell 6: Chronological Train / Validation / Test Splitting]
# Use existing split_set column or partition chronologically
if 'split_set' in df.columns:
    train_mask = df['split_set'] == 'train'
    val_mask = df['split_set'] == 'val'
    test_mask = df['split_set'] == 'test'
else:
    TRAIN_END = pd.to_datetime('2017-06-30 23:00:00')
    VAL_END = pd.to_datetime('2017-09-30 23:00:00')
    train_mask = df['timestamp'] <= TRAIN_END
    val_mask = (df['timestamp'] > TRAIN_END) & (df['timestamp'] <= VAL_END)
    test_mask = df['timestamp'] > VAL_END

# Feature column selection (excluding metadata and target)
EXCLUDE_COLS = ['timestamp', 'split_set', TARGET_COL]
FEATURE_COLS = [c for c in df.columns if c not in EXCLUDE_COLS]

# Categorical encoding for season if needed
df_encoded = df.copy()
if 'season' in df_encoded.columns and df_encoded['season'].dtype == 'object':
    df_encoded['season'] = df_encoded['season'].astype('category').cat.codes
if 'site_id' in df_encoded.columns and df_encoded['site_id'].dtype == 'object':
    df_encoded['site_id_code'] = df_encoded['site_id'].astype('category').cat.codes

MODEL_FEATURES = [c for c in FEATURE_COLS if c != 'site_id'] + (['site_id_code'] if 'site_id' in FEATURE_COLS else [])

X_train, y_train = df_encoded.loc[train_mask, MODEL_FEATURES], df_encoded.loc[train_mask, TARGET_COL]
X_val, y_val = df_encoded.loc[val_mask, MODEL_FEATURES], df_encoded.loc[val_mask, TARGET_COL]
X_test, y_test = df_encoded.loc[test_mask, MODEL_FEATURES], df_encoded.loc[test_mask, TARGET_COL]

print(f'Train Set: {X_train.shape[0]:,} rows ({X_train.shape[0]/len(df)*100:.1f}%)')
print(f'Val Set:   {X_val.shape[0]:,} rows ({X_val.shape[0]/len(df)*100:.1f}%)')
print(f'Test Set:  {X_test.shape[0]:,} rows ({X_test.shape[0]/len(df)*100:.1f}%)')
print(f'Feature Count: {len(MODEL_FEATURES)} features')

# %% Notebook code cell 14
# [Cell 7: Model Evaluation Helper & Comprehensive Metrics Engine]
results_registry = {}

def calculate_metrics(y_true, y_pred, model_name='Model'):
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    # 1. Root Mean Squared Error (RMSE)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    
    # 2. Mean Absolute Error (MAE)
    mae = mean_absolute_error(y_true, y_pred)
    
    # 3. Mean Absolute Percentage Error (MAPE)
    epsilon = 1e-6
    mape = np.mean(np.abs((y_true - y_pred) / (y_true + epsilon))) * 100
    
    # 4. R-squared Score
    r2 = r2_score(y_true, y_pred)
    
    # 5. Weighted Absolute Percentage Error (WAPE)
    wape = (np.sum(np.abs(y_true - y_pred)) / (np.sum(y_true) + epsilon)) * 100
    
    # 6. Peak Period Error (Accuracy during top 10% highest load hours)
    peak_threshold = np.quantile(y_true, 0.90)
    peak_idx = y_true >= peak_threshold
    peak_mae = mean_absolute_error(y_true[peak_idx], y_pred[peak_idx]) if np.any(peak_idx) else np.nan
    
    metrics = {
        'RMSE': round(rmse, 2),
        'MAE': round(mae, 2),
        'MAPE (%)': round(mape, 2),
        'R2': round(r2, 4),
        'WAPE (%)': round(wape, 2),
        'Peak MAE': round(peak_mae, 2)
    }
    
    print(f'=== {model_name} EVALUATION ===')
    for k, v in metrics.items():
        print(f'  {k:<10}: {v}')
    
    return metrics

# %% Notebook code cell 16
# [Cell 8: Model 1 - Seasonal ARIMA (SARIMA)]
print('=== TRAINING SEASONAL ARIMA (SARIMA) ===')
sample_site = 'Bear'
site_train = df[train_mask & (df['site_id'] == sample_site)][TARGET_COL].values
site_test = df[test_mask & (df['site_id'] == sample_site)][TARGET_COL].values

if SARIMAX is not None and len(site_train) > 48:
    # Subsampled benchmark window for tractable execution
    sarima_train_slice = site_train[-720:] # Last 30 days of training
    sarima_test_slice = site_test[:168]    # 7-day test horizon
    
    sarima_model = SARIMAX(
        sarima_train_slice,
        order=(1, 1, 1),
        seasonal_order=(1, 0, 1, 24),
        enforce_stationarity=False,
        enforce_invertibility=False
    ).fit(disp=False)
    
    sarima_preds = sarima_model.forecast(steps=len(sarima_test_slice))
    sarima_metrics = calculate_metrics(sarima_test_slice, sarima_preds, model_name='SARIMA (7d Horizon)')
    results_registry['SARIMA'] = sarima_metrics
else:
    print('Statsmodels SARIMAX not available. Skipped.')

# %% Notebook code cell 18
# [Cell 9: Model 2 - LightGBM Regressor Baseline]
print('=== TRAINING LIGHTGBM REGRESSOR ===')
lgb_model = lgb.LGBMRegressor(
    n_estimators=1000,
    learning_rate=0.03,
    num_leaves=31,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=RANDOM_SEED,
    n_jobs=4,
    force_row_wise=True
)

lgb_model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
)

lgb_preds = lgb_model.predict(X_test)
lgb_metrics = calculate_metrics(y_test, lgb_preds, model_name='LightGBM Baseline')
results_registry['LightGBM (Baseline)'] = lgb_metrics


# %% Notebook code cell 20
# [Cell 10: Model 3 - XGBoost Regressor Baseline]
print('=== TRAINING XGBOOST REGRESSOR ===')
xgb_model = xgb.XGBRegressor(
    n_estimators=1000,
    learning_rate=0.03,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=RANDOM_SEED,
    n_jobs=-1,
    early_stopping_rounds=50,
    eval_metric='rmse'
)

xgb_model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    verbose=False
)

xgb_preds = xgb_model.predict(X_test)
xgb_metrics = calculate_metrics(y_test, xgb_preds, model_name='XGBoost Baseline')
results_registry['XGBoost (Baseline)'] = xgb_metrics

# %% Notebook code cell 22
# [Cell 11: Model 4 - CatBoost Regressor Baseline]
print('=== TRAINING CATBOOST REGRESSOR ===')
if cb is not None:
    cat_model = cb.CatBoostRegressor(
        iterations=1000,
        learning_rate=0.03,
        depth=6,
        random_seed=RANDOM_SEED,
        verbose=False,
        early_stopping_rounds=50
    )
    
    cat_model.fit(
        X_train, y_train,
        eval_set=(X_val, y_val),
        use_best_model=True
    )
    
    cat_preds = cat_model.predict(X_test)
    cat_metrics = calculate_metrics(y_test, cat_preds, model_name='CatBoost Baseline')
    results_registry['CatBoost (Baseline)'] = cat_metrics
else:
    print('CatBoost not installed. Skipping CatBoost execution.')

# %% Notebook code cell 24
# [Cell 12: Model 5 - Random Forest Benchmark]
print('=== TRAINING RANDOM FOREST BENCHMARK ===')
# Train on a stratified subset or 100 trees for efficient baseline
rf_model = RandomForestRegressor(
    n_estimators=100,
    max_depth=16,
    min_samples_split=5,
    random_state=RANDOM_SEED,
    n_jobs=-1
)

# Fit on representative training sample (50,000 rows for rapid benchmarking)
sample_idx = np.random.choice(len(X_train), size=min(50000, len(X_train)), replace=False)
rf_model.fit(X_train.iloc[sample_idx], y_train.iloc[sample_idx])

rf_preds = rf_model.predict(X_test)
rf_metrics = calculate_metrics(y_test, rf_preds, model_name='Random Forest')
results_registry['Random Forest'] = rf_metrics

# %% Notebook code cell 26
# [Cell 13: Model 6 - Deep Learning: PyTorch LSTM Sequence Model]
print('=== TRAINING PYTORCH LSTM SEQUENCE MODEL ===')

# Standardize features for gradient descent
scaler_x = StandardScaler()
X_tr_scaled = scaler_x.fit_transform(X_train.fillna(0))
X_val_scaled = scaler_x.transform(X_val.fillna(0))
X_te_scaled = scaler_x.transform(X_test.fillna(0))

scaler_y = StandardScaler()
y_tr_scaled = scaler_y.fit_transform(y_train.values.reshape(-1, 1)).flatten()
y_val_scaled = scaler_y.transform(y_val.values.reshape(-1, 1)).flatten()

# Dataset generator for sequence windows
class TimeSeriesSequenceDataset(Dataset):
    def __init__(self, X, y, seq_len=24):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)
        self.seq_len = seq_len
        
    def __len__(self):
        return len(self.X) - self.seq_len
        
    def __getitem__(self, idx):
        return (
            self.X[idx:idx+self.seq_len],
            self.y[idx+self.seq_len]
        )

# LSTM Architecture Definition
class LSTMForecaster(nn.Module):
    def __init__(self, input_dim, hidden_dim=64, num_layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=num_layers, 
                            batch_first=True, dropout=dropout)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
        
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :]).squeeze(-1)

# Initialize PyTorch objects
SEQ_LEN = 24
input_dim = X_tr_scaled.shape[1]
lstm_net = LSTMForecaster(input_dim=input_dim).to(DEVICE)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(lstm_net.parameters(), lr=0.001)

train_loader = DataLoader(TimeSeriesSequenceDataset(X_tr_scaled[:30000], y_tr_scaled[:30000], seq_len=SEQ_LEN), batch_size=128, shuffle=False)

# Train loop (3 epochs demo)
lstm_net.train()
for epoch in range(3):
    total_loss = 0
    for batch_x, batch_y in train_loader:
        batch_x, batch_y = batch_x.to(DEVICE), batch_y.to(DEVICE)
        optimizer.zero_grad()
        preds = lstm_net(batch_x)
        loss = criterion(preds, batch_y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    print(f'  LSTM Epoch {epoch+1}/3 - Loss: {total_loss / len(train_loader):.4f}')

# Inference on Test Set
lstm_net.eval()
test_dataset = TimeSeriesSequenceDataset(X_te_scaled, np.zeros(len(X_te_scaled)), seq_len=SEQ_LEN)
test_loader = DataLoader(test_dataset, batch_size=256, shuffle=False)
lstm_preds_scaled = []

with torch.no_grad():
    for batch_x, _ in test_loader:
        batch_x = batch_x.to(DEVICE)
        out = lstm_net(batch_x)
        lstm_preds_scaled.extend(out.cpu().numpy())

# Invert scaling
lstm_preds = scaler_y.inverse_transform(np.array(lstm_preds_scaled).reshape(-1, 1)).flatten()
lstm_true = y_test.values[SEQ_LEN:]

lstm_metrics = calculate_metrics(lstm_true, lstm_preds, model_name='PyTorch LSTM')
results_registry['PyTorch LSTM'] = lstm_metrics

# %% Notebook code cell 28
# [Cell 14: Model 7 - Temporal Self-Attention / Transformer Network (TFT Inspired)]
print('=== TRAINING TEMPORAL SELF-ATTENTION TRANSFORMER ===')

class TemporalAttentionForecaster(nn.Module):
    def __init__(self, input_dim, d_model=64, nhead=4, num_layers=2, dropout=0.1):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=128, dropout=dropout, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.head = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
        
    def forward(self, x):
        proj = self.input_proj(x)
        trans_out = self.transformer_encoder(proj)
        # Global pooling over sequence length
        pooled = torch.mean(trans_out, dim=1)
        return self.head(pooled).squeeze(-1)

tft_net = TemporalAttentionForecaster(input_dim=input_dim).to(DEVICE)
tft_optimizer = torch.optim.AdamW(tft_net.parameters(), lr=0.001, weight_decay=1e-4)

# Train loop (3 epochs demo)
tft_net.train()
for epoch in range(3):
    total_loss = 0
    for batch_x, batch_y in train_loader:
        batch_x, batch_y = batch_x.to(DEVICE), batch_y.to(DEVICE)
        tft_optimizer.zero_grad()
        preds = tft_net(batch_x)
        loss = criterion(preds, batch_y)
        loss.backward()
        tft_optimizer.step()
        total_loss += loss.item()
    print(f'  Transformer Epoch {epoch+1}/3 - Loss: {total_loss / len(train_loader):.4f}')

# Inference
tft_net.eval()
tft_preds_scaled = []
with torch.no_grad():
    for batch_x, _ in test_loader:
        batch_x = batch_x.to(DEVICE)
        out = tft_net(batch_x)
        tft_preds_scaled.extend(out.cpu().numpy())

tft_preds = scaler_y.inverse_transform(np.array(tft_preds_scaled).reshape(-1, 1)).flatten()
tft_metrics = calculate_metrics(lstm_true, tft_preds, model_name='Temporal Transformer (TFT Inspired)')
results_registry['Temporal Transformer'] = tft_metrics

# %% Notebook code cell 30
# [Cell 15: Bayesian Hyperparameter Optimization Framework (Optuna)]
print('=== HYPERPARAMETER OPTIMIZATION SETUP ===')
if optuna is None:
    print('Optuna is not installed. To run tuning, run: pip install optuna')
else:
    print(f'Optuna Version: {optuna.__version__}')
    print('Search strategies enabled: Tree-structured Parzen Estimator (TPE) with temporal validation.')

# %% Notebook code cell 32
# [Cell 16: Fine-Tuning Top Performer - LightGBM with Optuna]
if optuna is not None:
    def lgb_objective(trial):
        params = {
            'n_estimators': 300,
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15, log=True),
            'num_leaves': trial.suggest_int('num_leaves', 20, 128),
            'max_depth': trial.suggest_int('max_depth', 4, 12),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 10.0, log=True),
            'random_state': RANDOM_SEED,
            'n_jobs': 4,
            'force_row_wise': True
        }
        
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)]
        )
        val_preds = model.predict(X_val)
        return np.sqrt(mean_squared_error(y_val, val_preds))
    
    print('Running 20 trials of Bayesian optimization for LightGBM...')
    study_lgb = optuna.create_study(direction='minimize')
    study_lgb.optimize(lgb_objective, n_trials=20)
    
    print(f'Best LightGBM Trial RMSE: {study_lgb.best_value:.2f}')
    print('Best Hyperparameters:', study_lgb.best_params)
    
    # Train Best Model
    best_lgb = lgb.LGBMRegressor(**study_lgb.best_params, n_estimators=1000, random_state=RANDOM_SEED, n_jobs=4, force_row_wise=True)
    best_lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(50, verbose=False)])
    
    tuned_lgb_preds = best_lgb.predict(X_test)
    tuned_lgb_metrics = calculate_metrics(y_test, tuned_lgb_preds, model_name='LightGBM (Tuned)')
    results_registry['LightGBM (Tuned)'] = tuned_lgb_metrics
else:
    print('Skipping Optuna tuning cell.')


# %% Notebook code cell 34
# [Cell 17: Fine-Tuning Top Performer - XGBoost with Optuna]
if optuna is not None:
    def xgb_objective(trial):
        params = {
            'n_estimators': 300,
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15, log=True),
            'max_depth': trial.suggest_int('max_depth', 4, 10),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'gamma': trial.suggest_float('gamma', 1e-3, 5.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 10.0, log=True),
            'random_state': RANDOM_SEED,
            'n_jobs': -1,
            'eval_metric': 'rmse'
        }
        
        model = xgb.XGBRegressor(**params, early_stopping_rounds=30)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        val_preds = model.predict(X_val)
        return np.sqrt(mean_squared_error(y_val, val_preds))
    
    print('Running 20 trials of Bayesian optimization for XGBoost...')
    study_xgb = optuna.create_study(direction='minimize')
    study_xgb.optimize(xgb_objective, n_trials=20)
    
    print(f'Best XGBoost Trial RMSE: {study_xgb.best_value:.2f}')
    print('Best Hyperparameters:', study_xgb.best_params)
    
    # Train Best Model
    best_xgb = xgb.XGBRegressor(**study_xgb.best_params, n_estimators=1000, random_state=RANDOM_SEED, n_jobs=-1, early_stopping_rounds=50, eval_metric='rmse')
    best_xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    
    tuned_xgb_preds = best_xgb.predict(X_test)
    tuned_xgb_metrics = calculate_metrics(y_test, tuned_xgb_preds, model_name='XGBoost (Tuned)')
    results_registry['XGBoost (Tuned)'] = tuned_xgb_metrics
else:
    print('Skipping Optuna tuning cell.')

# %% Notebook code cell 36
# [Cell 18: Comprehensive Model Leaderboard & Metrics Comparison]
print('=== COMPREHENSIVE MODEL LEADERBOARD ===')
df_leaderboard = pd.DataFrame(results_registry).T
df_leaderboard = df_leaderboard.sort_values('RMSE', ascending=True)

# Format and display
display(df_leaderboard.style.highlight_min(subset=['RMSE', 'MAE', 'MAPE (%)', 'WAPE (%)', 'Peak MAE'], color='#dcfce7')
                           .highlight_max(subset=['R2'], color='#dcfce7'))

# Visual Comparison Bar Charts
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# RMSE
df_leaderboard['RMSE'].plot(kind='bar', ax=axes[0], color='#2563eb')
axes[0].set_title('Root Mean Squared Error (RMSE) - Lower is Better')
axes[0].set_ylabel('kWh')
axes[0].tick_params(axis='x', rotation=45)

# MAE
df_leaderboard['MAE'].plot(kind='bar', ax=axes[1], color='#059669')
axes[1].set_title('Mean Absolute Error (MAE) - Lower is Better')
axes[1].set_ylabel('kWh')
axes[1].tick_params(axis='x', rotation=45)

# R2 Score
df_leaderboard['R2'].plot(kind='bar', ax=axes[2], color='#7c3aed')
axes[2].set_title('R-Squared (R2) - Higher is Better')
axes[2].set_ylabel('Score')
axes[2].tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.show()

# %% Notebook code cell 38
# [Cell 19: Visual Benchmark - Actual vs Predicted Test Curves]
PLOT_WINDOW = 168 # 7 days (168 hours)

plt.figure(figsize=(16, 7))
actual_sample = y_test.values[:PLOT_WINDOW]
plt.plot(actual_sample, label='Ground Truth (Actual Demand)', color='black', linewidth=2.5, alpha=0.9)

if 'lgb_preds' in locals():
    plt.plot(lgb_preds[:PLOT_WINDOW], label='LightGBM', linestyle='--', alpha=0.85)
if 'xgb_preds' in locals():
    plt.plot(xgb_preds[:PLOT_WINDOW], label='XGBoost', linestyle='-.', alpha=0.85)
if 'tuned_lgb_preds' in locals():
    plt.plot(tuned_lgb_preds[:PLOT_WINDOW], label='Tuned LightGBM', color='#16a34a', linewidth=2.0)
if 'lstm_preds' in locals():
    plt.plot(lstm_preds[:PLOT_WINDOW], label='PyTorch LSTM', linestyle=':', alpha=0.85)
if 'tft_preds' in locals():
    plt.plot(tft_preds[:PLOT_WINDOW], label='Temporal Transformer', linestyle=':', alpha=0.85)

plt.title('7-Day (168-Hour) Forecasting Horizon: Model Predictions vs Ground Truth', fontsize=14, fontweight='bold')
plt.xlabel('Hours in Test Horizon')
plt.ylabel('Total Demand (kWh)')
plt.legend(loc='upper right', frameon=True)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# %% Notebook code cell 40
# [Cell 20: Peak Period Diagnostics & Residual Error Analysis]
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# 1. Residuals Distribution
residuals_lgb = y_test.values - lgb_preds
residuals_xgb = y_test.values - xgb_preds

sns.kdeplot(residuals_lgb, ax=axes[0], label='LightGBM Residuals', fill=True, color='#2563eb', alpha=0.3)
sns.kdeplot(residuals_xgb, ax=axes[0], label='XGBoost Residuals', fill=True, color='#ea580c', alpha=0.3)
axes[0].axvline(0, color='red', linestyle='--', alpha=0.7)
axes[0].set_title('Prediction Error / Residual Distribution (y_true - y_pred)')
axes[0].set_xlabel('Residual Error (kWh)')
axes[0].legend()

# 2. Peak Period Accuracy Comparison
peak_mae_series = df_leaderboard['Peak MAE'].dropna()
peak_mae_series.plot(kind='bar', ax=axes[1], color='#dc2626')
axes[1].set_title('Peak Demand Period MAE (Top 10% Load Hours)')
axes[1].set_ylabel('Peak MAE (kWh)')
axes[1].tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.show()

# %% Notebook code cell 42
# [Cell 21: Full-Dataset Retraining of Champion Model for Production Deployment]
print('=== RETRAINING CHAMPION MODEL ON ENTIRE DATASET (TRAIN + VAL + TEST) ===')

# 1. Assemble complete feature matrix and target across all splits
X_full = df_encoded[MODEL_FEATURES].copy()
y_full = df_encoded[TARGET_COL].copy()
print(f'Full Dataset Shape: {X_full.shape[0]:,} rows x {X_full.shape[1]} features (100% of historical data)')

# 2. Identify champion model architecture from leaderboard
champion_name = df_leaderboard.index[0]
print(f'Leaderboard Champion Model: {champion_name}')

# 3. Retrain champion model with optimal hyperparameters and locked iteration count
if 'best_lgb' in locals() and 'LightGBM' in champion_name:
    full_params = best_lgb.get_params()
    optimal_trees = getattr(best_lgb, 'best_iteration_', 300) or 300
    full_params['n_estimators'] = optimal_trees
    full_params.pop('early_stopping_round', None)
    
    print(f'Fitting production LightGBM with optimal n_estimators={optimal_trees} on all {len(X_full):,} rows...')
    t_retrain = time.time()
    champion_production = lgb.LGBMRegressor(**full_params)
    champion_production.fit(X_full, y_full)
    print(f'Production LightGBM champion retrained in {time.time()-t_retrain:.2f}s!')

elif 'best_xgb' in locals() and 'XGBoost' in champion_name:
    full_params = best_xgb.get_params()
    optimal_trees = getattr(best_xgb, 'best_iteration', 300) or 300
    full_params['n_estimators'] = optimal_trees
    full_params.pop('early_stopping_rounds', None)
    
    print(f'Fitting production XGBoost with optimal n_estimators={optimal_trees} on all {len(X_full):,} rows...')
    t_retrain = time.time()
    champion_production = xgb.XGBRegressor(**full_params)
    champion_production.fit(X_full, y_full, verbose=False)
    print(f'Production XGBoost champion retrained in {time.time()-t_retrain:.2f}s!')

elif 'lgb_model' in locals():
    full_params = lgb_model.get_params()
    optimal_trees = getattr(lgb_model, 'best_iteration_', 300) or 300
    full_params['n_estimators'] = optimal_trees
    champion_production = lgb.LGBMRegressor(**full_params)
    champion_production.fit(X_full, y_full)
    print(f'Production LightGBM baseline retrained on all {len(X_full):,} rows!')

else:
    raise ValueError('No champion model found to retrain.')

# %% Notebook code cell 44
# [Cell 22: Best Model Serialization & Artifact Export]
import pickle

MODELS_DIR = PROJECT_ROOT / 'Models' / 'CP-2'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Save leaderboard metrics summary
leaderboard_path = MODELS_DIR / 'model_leaderboard_metrics.csv'
df_leaderboard.to_csv(leaderboard_path)
print(f'Leaderboard saved to: {leaderboard_path}')

# 2. Save production champion model trained on entire dataset
regional_model_file = MODELS_DIR / 'regional_model.pkl'
with open(regional_model_file, 'wb') as f:
    pickle.dump(champion_production, f)

print(f'\nChampion regional model successfully serialized!')
print(f'-> Destination:      {regional_model_file}')
print(f'-> Model Class:      {type(champion_production).__name__}')
print(f'-> Training Records: {len(X_full):,} rows (100% full dataset)')
print(f'-> Features:         {champion_production.n_features_in_} predictors')
print(f'-> File Size:        {regional_model_file.stat().st_size / (1024**2):.2f} MB')

