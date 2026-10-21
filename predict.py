"""使用已訓練模型，對新的原始 CSV 預測。"""
from pathlib import Path
import argparse
import sys
import json
import joblib
import pandas as pd
from preprocessing import clean_frame, json_text, read_csv_bytes


def main():
    # Keep Chinese output readable when Windows redirects stdout/stderr to pipes.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="對原始 CSV 套用相同規則並預測")
    parser.add_argument("--model", default="model.joblib")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", default="predictions.csv")
    parser.add_argument("--encoding", default="auto")
    parser.add_argument("--separator", default="auto")
    args = parser.parse_args()
    model = joblib.load(args.model)
    frame, _ = read_csv_bytes(Path(args.csv).read_bytes(), args.encoding, args.separator)
    # 模型中的前處理器負責轉換，新資料不能重新 fit。
    predicted = model.predict(frame)
    output = pd.DataFrame({"source_data_row": range(1, len(frame) + 1), "prediction": predicted})
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(frame)
        for i, label in enumerate(model.named_steps["model"].classes_):
            output[f"probability_{label}"] = probs[:, i]
    output_path = Path(args.output)
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    audit = model.named_steps["preprocess"].audit(frame)
    output_path.with_suffix(".audit.json").write_text(json_text(audit), encoding="utf-8")
    print(f"完成 {len(output):,} 筆預測：{output_path}")
    print("另附 .audit.json，記錄缺值、轉型失敗與訓練時未見過的類別。")


if __name__ == "__main__":
    main()
