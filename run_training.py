"""ChatGPT/local terminal entry point using exactly the same training engine as the UI."""
import argparse
import json
from pathlib import Path
import sys
from preprocessing import json_text, profile_frame, read_csv_bytes
from training_service import run_training_bytes, suggested_exclusions


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='從原始 CSV 一次完成整理、訓練與 ZIP 匯出')
    parser.add_argument('--csv', required=True)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--config', help='JSON 設定，包含 task、target、excluded_columns 等')
    parser.add_argument('--output', default='outputs/training_data.zip')
    args = parser.parse_args()
    payload = Path(args.csv).read_bytes()
    if args.inspect:
        frame, info = read_csv_bytes(payload)
        print(json_text({'file': info, 'columns': list(frame.columns),
                         'suggested_excluded_columns': suggested_exclusions(frame),
                         'profile': profile_frame(frame).to_dict(orient='records')}))
        return
    if not args.config:
        parser.error('訓練需要 --config，請明確指定目標欄位。')
    bundle, summary = run_training_bytes(payload, json.loads(Path(args.config).read_text(encoding='utf-8')))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        parser.error('輸出檔案已存在，請使用新的 --output，避免覆蓋舊訓練結果。')
    output.write_bytes(bundle)
    output.with_suffix('.summary.json').write_text(json_text(summary), encoding='utf-8')
    print(json_text({'output': str(output.resolve()), **summary}))


if __name__ == '__main__':
    main()
