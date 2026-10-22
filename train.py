"""解壓資料包後執行：python train.py --data ."""
from pathlib import Path
import argparse
import sys
import json
import joblib
import pandas as pd
from scipy import sparse
from preprocessing import PreparedData, PrepConfig, json_text, train_baseline
from automl import train_prepared


def main():
    # Keep Chinese output readable when Windows redirects stdout/stderr to pipes.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="用整理好的資料訓練基準模型")
    parser.add_argument("--data", default=".", help="解壓後的訓練資料包資料夾")
    args = parser.parse_args()
    folder = Path(args.data)
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    preprocessor = joblib.load(folder / "preprocessor.joblib")
    X_train, X_test = (sparse.load_npz(folder / f"X_{s}.npz") for s in ("train", "test"))
    # 不讓 001 變成 1，也不把有效的 NA 類別誤認為缺值。
    y_train, y_test = (pd.read_csv(folder / f"y_{s}.csv", dtype=str, keep_default_na=False).iloc[:, 0]
                       for s in ("train", "test"))
    if config["task"] == "regression":
        y_train, y_test = pd.to_numeric(y_train), pd.to_numeric(y_test)
    raw_train, raw_test = (pd.read_csv(folder / f"raw_{s}.csv", dtype=str, keep_default_na=False)
                           for s in ("train", "test"))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    data = PreparedData(PrepConfig(**config), raw_train, raw_test, pd.DataFrame(),
                        X_train, X_test, y_train, y_test, preprocessor, report)
    model, metrics, predictions = train_prepared(data)
    joblib.dump(model, folder / "model.joblib")
    (folder / "metrics.json").write_text(json_text(metrics), encoding="utf-8")
    predictions.to_csv(folder / "test_predictions.csv", index=False, encoding="utf-8-sig")
    print(json_text(metrics))
    print("模型已儲存為 model.joblib，包含補值、編碼及縮放流程。")


if __name__ == "__main__":
    main()
