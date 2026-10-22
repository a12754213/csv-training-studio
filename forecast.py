"""Standalone forecasting/retraining entry point included in exported bundles."""
import argparse
import json
from pathlib import Path
import sys
import joblib
import pandas as pd
from forecasting import ForecastConfig, ForecastModel, make_forecast_bundle, prepare_forecast, train_forecast
from preprocessing import read_csv_bytes


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='用原始歷史 CSV 預測第 horizon 筆未來數值')
    parser.add_argument('--csv', required=True)
    parser.add_argument('--model', default='model.joblib')
    parser.add_argument('--output', default='future_prediction.csv')
    parser.add_argument('--retrain', action='store_true')
    parser.add_argument('--config', default='config.json')
    args = parser.parse_args()
    frame, _ = read_csv_bytes(Path(args.csv).read_bytes())
    output = Path(args.output)
    if args.retrain:
        config = ForecastConfig(**json.loads(Path(args.config).read_text(encoding='utf-8')))
        data = prepare_forecast(frame, config)
        output.write_bytes(make_forecast_bundle(data, train_forecast(data)))
    else:
        model = joblib.load(args.model)
        if not isinstance(model, ForecastModel):
            parser.error('這不是時間序列模型；一般表格模型請用 predict.py。')
        pd.DataFrame([model.forecast(frame)]).to_csv(output, index=False, encoding='utf-8-sig')
    print(f'已輸出：{output}')


if __name__ == '__main__':
    main()
