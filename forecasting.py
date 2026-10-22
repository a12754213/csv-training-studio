"""Direct h-step forecasting from historical numeric windows; no future covariates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
import io
import math
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

from preprocessing import (DataPreparationError, TabularPreprocessor, _csv_bytes,
                           _dates, _numeric, _scores, clean_frame, json_text)
from version import __version__

MAX_WINDOW_CELLS = 5_000_000


@dataclass
class ForecastConfig:
    target: str
    time_column: str
    lookback: int = 14
    horizon: int = 1
    test_size: float = 0.2
    model: str = "ridge"
    feature_columns: tuple[str, ...] = ()
    excluded_columns: tuple[str, ...] = ()
    missing_tokens: tuple[str, ...] = ()
    seed: int = 42
    include_lstm: bool = False
    lstm_epochs: int = 30
    lstm_units: int = 32


def validate_config(frame, config):
    if config.target not in frame or config.time_column not in frame:
        raise DataPreparationError("請選擇存在的目標及時間欄。")
    if config.target == config.time_column:
        raise DataPreparationError("目標與時間欄必須不同。")
    if not isinstance(config.lookback, int) or not 1 <= config.lookback <= 365:
        raise DataPreparationError("歷史視窗必須為 1～365 筆。")
    if not isinstance(config.horizon, int) or not 1 <= config.horizon <= 90:
        raise DataPreparationError("預測跨度必須為 1～90 筆。")
    if not 0.1 <= config.test_size <= 0.4:
        raise DataPreparationError("測試集比例需介於 10% 到 40%。")
    if config.model not in {"ridge", "random_forest", "auto", "lstm"}:
        raise DataPreparationError("時間序列模型支援 ridge、random_forest、auto 或 lstm。")
    if not isinstance(config.lstm_epochs, int) or not 1 <= config.lstm_epochs <= 100:
        raise DataPreparationError("LSTM 訓練上限必須為 1～100 epochs。")
    if not isinstance(config.lstm_units, int) or not 8 <= config.lstm_units <= 128:
        raise DataPreparationError("LSTM 單元數必須為 8～128。")
    unknown = (set(config.feature_columns) | set(config.excluded_columns)) - set(frame.columns)
    if unknown:
        raise DataPreparationError(f"指定的欄位不存在：{sorted(unknown)}")
    if {config.target, config.time_column} & set(config.excluded_columns):
        raise DataPreparationError("目標及時間欄是時間序列必要欄位，不能排除。")
    if config.time_column in config.feature_columns:
        raise DataPreparationError("時間欄用於排序，不當作數值歷史特徵。")


def history_columns(config):
    return list(dict.fromkeys([config.target] + [c for c in config.feature_columns
                                                if c not in config.excluded_columns]))


def ordered_history(frame, config):
    """Sort without removing missing-target rows (removing rows changes the horizon)."""
    required = [config.time_column, *history_columns(config)]
    missing = set(required) - set(frame.columns)
    if missing:
        raise DataPreparationError(f"歷史資料缺少必要欄位：{sorted(missing)}")
    clean = clean_frame(frame[required], config.missing_tokens)
    times = _dates(clean[config.time_column])
    if times.isna().any():
        raise DataPreparationError("時間欄有缺值或無法解析的日期，請先修正。")
    if times.duplicated().any():
        raise DataPreparationError("時間欄有重複時間；目前支援單一序列，請先選一個商品／股票或依時間彙總。")
    order = np.argsort(times.to_numpy(), kind="stable")
    ordered = clean.iloc[order].copy()
    ordered[config.time_column] = times.iloc[order].to_numpy()
    for col in history_columns(config):
        values = _numeric(ordered[col])
        if (ordered[col].notna() & values.isna()).any():
            raise DataPreparationError(f"{col} 含非數值或無限值；時間序列歷史特徵目前只接受數值。")
        ordered[col] = values
    return ordered, order


def window_names(config):
    # lag is measured relative to the future target row, not the forecast origin.
    return [f"{column}__lag_{lag}" for column in history_columns(config)
            for lag in range(config.horizon + config.lookback - 1, config.horizon - 1, -1)]


def make_windows(ordered, config, target_positions):
    cols = history_columns(config)
    if len(target_positions) * config.lookback * len(cols) > MAX_WINDOW_CELLS:
        raise DataPreparationError("歷史視窗超過 500 萬個數值，請縮短視窗、減少欄位或資料筆數。")
    origin = np.asarray(target_positions) - config.horizon
    positions = origin[:, None] - np.arange(config.lookback - 1, -1, -1)[None, :]
    values = np.concatenate([ordered[c].to_numpy()[positions] for c in cols], axis=1)
    return pd.DataFrame(values, columns=window_names(config), index=target_positions)


@dataclass
class ForecastData:
    config: ForecastConfig
    history: pd.DataFrame
    windows: pd.DataFrame
    targets: pd.Series
    train_positions: np.ndarray
    test_positions: np.ndarray
    manifest: pd.DataFrame
    report: dict
    raw_history: pd.DataFrame


def prepare_forecast(frame, config):
    validate_config(frame, config)
    ordered, source_positions = ordered_history(frame, config)
    start = config.lookback + config.horizon - 1
    positions = np.arange(start, len(ordered))
    target = ordered[config.target].to_numpy()
    # Missing labels and unavailable Naive values are skipped, never imputed.
    valid = np.isfinite(target[positions]) & np.isfinite(target[positions - config.horizon])
    usable = positions[valid]
    if len(usable) < 12:
        raise DataPreparationError("建立歷史視窗後，有效樣本不足 12 筆；請增加資料或縮短視窗／跨度。")
    cut = int(math.floor(len(usable) * (1 - config.test_size)))
    test = usable[cut:]
    first_test_origin = int(test[0] - config.horizon)
    train = usable[:cut][usable[:cut] < first_test_origin]
    purged = usable[:cut][usable[:cut] >= first_test_origin]
    if len(train) < 8 or len(test) < 2:
        raise DataPreparationError("保留時間間隔後，訓練不足 8 筆或測試不足 2 筆；請增加資料或縮短跨度。")
    windows = make_windows(ordered, config, usable)
    times = pd.Series(ordered[config.time_column].to_numpy())
    # Determine interval from pre-test history only. Business-day calendars are not guessed.
    train_times = pd.DatetimeIndex(times.iloc[:int(train[-1]) + 1])
    frequency = pd.infer_freq(train_times) if len(train_times) >= 3 else None
    notes = ["依時間排序；目標為歷史視窗結束後第 horizon 筆，跨度單位是資料筆數。",
             "訓練標籤時間嚴格早於第一筆測試預測起點；交界樣本已隔離。",
             "測試採滾動起點：每次只使用當時已觀測到的歷史，模型固定、不重新訓練。",
             "較晚測試視窗可以使用已經發生的測試期真實值；這不是一次預測整段未知未來。",
             "沒有填補目標；歷史缺值的補值及標準化只從訓練視窗學習。",
             "提供歷史視窗 + Ridge／Random Forest，以及本機選用 LSTM；不以測試分數挑模型。"]
    if frequency is None:
        notes.append("時間間隔不固定：預測第幾筆，而非固定幾天；不猜測未來時間戳。")
    train_set, test_set = set(train), set(test)
    manifest = pd.DataFrame({
        "target_position": usable,
        "target_source_data_row": source_positions[usable] + 1,
        "origin_source_data_row": source_positions[usable - config.horizon] + 1,
        "history_start_time": times.iloc[usable - config.horizon - config.lookback + 1].astype(str).to_numpy(),
        "origin_time": times.iloc[usable - config.horizon].astype(str).to_numpy(),
        "target_time": times.iloc[usable].astype(str).to_numpy(),
        "split": ["train" if p in train_set else "test" if p in test_set else "purged" for p in usable],
    })
    report = {"version": __version__, "kind": "time_series", "config": asdict(config),
              "rows": {"input": len(frame), "train": len(train), "test": len(test),
                       "warmup": min(start, len(frame)), "missing_label_or_origin": int((~valid).sum()),
                       "purged": len(purged)},
              "history_columns": history_columns(config),
              "excluded_columns": list(config.excluded_columns),
              "unused_columns": [c for c in frame if c not in history_columns(config) + [config.time_column]],
              "feature_names": window_names(config), "frequency": frequency,
              "train_last_target_time": str(times.iloc[train[-1]]),
              "test_first_origin_time": str(times.iloc[first_test_origin]),
              "evaluation": "rolling_origin_fixed_model", "notes": notes,
              "environment": {p: version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "joblib", "jieba")}}
    return ForecastData(config, ordered, windows, pd.Series(target[usable], index=usable),
                        train, test, manifest, report, frame.copy())


@dataclass
class ForecastModel:
    config: ForecastConfig
    preprocessor: TabularPreprocessor
    estimator: object
    frequency: str | None

    def forecast(self, history):
        # Unused or explicitly excluded fields need not be supplied again.
        ordered, _ = ordered_history(history, self.config)
        if len(ordered) < self.config.lookback:
            raise DataPreparationError(f"預測至少需要最近 {self.config.lookback} 筆歷史。")
        origin_value = ordered[self.config.target].iloc[-1]
        if not np.isfinite(origin_value):
            raise DataPreparationError("最後一筆歷史目標必須有已觀測的數值。")
        target_pos = len(ordered) - 1 + self.config.horizon
        features = make_windows(ordered, self.config, np.array([target_pos]))
        prediction = float(self.estimator.predict(self.preprocessor.transform(features))[0])
        origin_time = pd.Timestamp(ordered[self.config.time_column].iloc[-1])
        observed_frequency = pd.infer_freq(pd.DatetimeIndex(ordered[self.config.time_column])) if len(ordered) >= 3 else None
        forecast_time = None
        if self.frequency and observed_frequency == self.frequency:
            forecast_time = str(origin_time + self.config.horizon * pd.tseries.frequencies.to_offset(self.frequency))
        return {"origin_time": str(origin_time), "forecast_time": forecast_time,
                "horizon_rows": self.config.horizon, "prediction": prediction,
                "naive_prediction": float(origin_value)}

    def predict(self, history):
        return np.array([self.forecast(history)["prediction"]])


def validation_positions(data):
    positions = data.train_positions
    cut = int(len(positions) * 0.8)
    val = positions[cut:]
    train = positions[:cut][positions[:cut] < val[0] - data.config.horizon]
    if len(train) < 8 or len(val) < 2:
        raise DataPreparationError("訓練集不足以再切時間驗證集；請增加資料、縮短跨度或選單一 Ridge／Random Forest。")
    return train, val


def fit_candidate(data, positions, name, validation=None, epochs=None):
    cfg = data.config
    train_x = data.windows.loc[positions]
    pre = TabularPreprocessor(column_roles={c: "numeric" for c in train_x},
                              drop_constant=False, missing_indicators=False)
    X_train = pre.fit_transform(train_x)
    y_train = data.targets.loc[positions]
    if name == "lstm":
        from lstm_model import LSTMRegressor
        estimator = LSTMRegressor(cfg.lookback, len(history_columns(cfg)), units=cfg.lstm_units,
                                  epochs=epochs or cfg.lstm_epochs, seed=cfg.seed)
        val = None if validation is None else (pre.transform(data.windows.loc[validation]), data.targets.loc[validation])
        estimator.fit(X_train, y_train, validation=val)
    else:
        estimator = (Ridge(alpha=1.0, solver="lsqr") if name == "ridge" else
                     RandomForestRegressor(n_estimators=150, max_depth=12, min_samples_leaf=2,
                                           random_state=cfg.seed, n_jobs=1))
        estimator.fit(X_train, y_train)
    return ForecastModel(cfg, pre, estimator, data.report["frequency"])


def train_forecast(data):
    cfg = data.config
    selected = cfg.model
    comparison = []
    selected_epochs = None
    validation_history = None
    if selected == "auto" or selected == "lstm":
        inner_train, inner_val = validation_positions(data)
        names = ["lstm"] if selected == "lstm" else ["ridge", "random_forest"] + (["lstm"] if cfg.include_lstm else [])
        for name in names:
            candidate = fit_candidate(data, inner_train, name, validation=inner_val if name == "lstm" else None)
            prediction = candidate.estimator.predict(candidate.preprocessor.transform(data.windows.loc[inner_val]))
            row = {"candidate": name, "validation_scores": _scores(data.targets.loc[inner_val], prediction, "regression")}
            if name == "lstm":
                row["best_epoch"] = candidate.estimator.best_epoch
                validation_history = candidate.estimator.training_history
            comparison.append(row)
        winner = min(comparison, key=lambda item: item["validation_scores"]["mae"])
        selected, selected_epochs = winner["candidate"], winner.get("best_epoch")
        data.report["selection"] = {"used": "inner_validation_only", "metric": "mae",
                                    "train_last_target_position": int(inner_train[-1]),
                                    "validation_first_origin_position": int(inner_val[0] - cfg.horizon),
                                    "validation_last_target_position": int(inner_val[-1]),
                                    "test_first_target_position": int(data.test_positions[0]),
                                    "candidates": comparison}
    # Refit selected settings on the complete outer training split, then evaluate test once.
    model = fit_candidate(data, data.train_positions, selected, epochs=selected_epochs)
    prediction = model.estimator.predict(model.preprocessor.transform(data.windows.loc[data.test_positions]))
    actual = data.targets.loc[data.test_positions].to_numpy()
    naive = data.history[cfg.target].iloc[data.test_positions - cfg.horizon].to_numpy()
    model_scores = _scores(actual, prediction, "regression")
    naive_scores = _scores(actual, naive, "regression")
    metrics = {"model": model.estimator.__class__.__name__, "selected_model": selected,
               "test_scores": model_scores, "naive_scores": naive_scores, "evaluation": data.report["evaluation"],
               "mae_skill_vs_naive": (1 - model_scores["mae"] / naive_scores["mae"]
                                      if naive_scores["mae"] > 0 else None),
               "beats_naive_mae": model_scores["mae"] < naive_scores["mae"]}
    if comparison:
        metrics.update(model_comparison=comparison, selection_data="inner_validation_only", selection_metric="mae")
    if selected_epochs:
        metrics["lstm_refit_epochs"] = selected_epochs
    if validation_history is not None:
        metrics["lstm_validation_history"] = validation_history
        data.report["environment"].update({p: version(p) for p in ("tensorflow", "keras")})
    predictions = data.manifest.set_index("target_position").loc[data.test_positions].reset_index()
    predictions["actual"], predictions["prediction"], predictions["naive_prediction"] = actual, prediction, naive
    data.report["learned_from_training_only"] = model.preprocessor.learned_values()
    return model, metrics, predictions


def make_forecast_bundle(data, trained):
    model, metrics, predictions = trained
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        buff = io.BytesIO()
        joblib.dump(model, buff)
        z.writestr("model.joblib", buff.getvalue())
        if hasattr(model.estimator, "keras_bytes"):
            z.writestr("model.keras", model.estimator.keras_bytes)
            prep = io.BytesIO(); joblib.dump(model.preprocessor, prep)
            z.writestr("preprocessor.joblib", prep.getvalue())
            z.writestr("lstm_scaling.json", json_text({"y_mean": model.estimator.y_mean,
                          "y_scale": model.estimator.y_scale, "lookback": data.config.lookback,
                          "channels": len(history_columns(data.config)), "layout": "column_major_lags_to_time_major"}))
        for name, value in (("config.json", asdict(data.config)), ("report.json", data.report), ("metrics.json", metrics)):
            z.writestr(name, json_text(value))
        for name, value in (("history.csv", data.raw_history), ("test_predictions.csv", predictions), ("window_manifest.csv", data.manifest)):
            z.writestr(name, _csv_bytes(value))
        for split, positions in (("train", data.train_positions), ("test", data.test_positions)):
            z.writestr(f"X_{split}.csv", _csv_bytes(data.windows.loc[positions]))
            z.writestr(f"y_{split}.csv", _csv_bytes(pd.DataFrame({data.config.target: data.targets.loc[positions]})))
        here = Path(__file__).resolve().parent
        for name in ("forecasting.py", "forecast.py", "preprocessing.py", "text_features.py", "version.py", "lstm_model.py", "automl.py"):
            z.writestr(name, (here / name).read_bytes())
        z.writestr("requirements.txt", "\n".join(f"{p}=={v}" for p, v in data.report["environment"].items()) + "\n")
        z.writestr("README.md", FORECAST_README)
    return stream.getvalue()


FORECAST_README = """# 時間序列模型

安裝套件後，用最近一段已觀測歷史預測：

```powershell
python -m pip install -r requirements.txt
python forecast.py --model model.joblib --csv history.csv --output future_prediction.csv
```

需要原始時間欄、目標的歷史值及選中的歷史數值欄。至少提供 lookback 筆，程式會依時間排序。
輸出一筆：最後觀測起點之後第 horizon 筆的預測；不是 horizon 筆連續預測。
日期不規則時 forecast_time 留空（不猜股票休市日），horizon_rows 仍有效。
模型內含只用訓練視窗 fit 的補值與標準化；不要先自行轉換。

重新訓練相同設定：

```powershell
python forecast.py --retrain --config config.json --csv history.csv --output retrained.zip
```

測試使用 rolling-origin fixed-model：模型不更新，較晚起點可用已觀測的較早測試期歷史值。
所有訓練標籤早於第一筆測試起點，交界隔離樣本見 window_manifest.csv。
MAE/RMSE 越低越好；beats_naive_mae 為 false 表示 MAE 沒勝過最近一次真值。
不把曲線接近視為模型有效。目標不補值；模型可為 Ridge/Random Forest/LSTM。
AutoML 僅用訓練集內的時間驗證區間挑模型；LSTM 也只用該區間選 epoch，然後重新 fit 整個外層訓練集。
LSTM 另附 model.keras、preprocessor.joblib、lstm_scaling.json。model.keras 接受經前處理並排成
(samples, lookback, channels) 的數值，輸出需乘 y_scale 再加 y_mean；建議直接用 forecast.py 處理原始 CSV。
僅支援單一序列，重複時間請先選擇單一商品／股票或彙總。不要用整段測試集反覆調參。
config.json、report.json 保留設定與處理紀錄。joblib 只載入自己產生且信任的檔案。
"""
