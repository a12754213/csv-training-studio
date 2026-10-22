"""Auditable suggestions for a ChatGPT agent; heuristics do not determine business intent."""
import importlib.util
from preprocessing import _dates, _numeric, clean_frame, infer_kind, read_csv_bytes
from training_service import suggested_exclusions


def suggest_plan(payload, target=None, time_column=None, forecast_intent=False, encoding='auto', separator='auto'):
    frame, info = read_csv_bytes(payload, encoding, separator)
    clean = clean_frame(frame)
    dates = [c for c in frame if infer_kind(clean[c], c) == 'datetime']
    report = {'columns': list(frame.columns), 'date_candidates': dates,
              'target_required': target not in frame, 'notes': [], 'lstm_installed': importlib.util.find_spec('tensorflow') is not None}
    if target not in frame:
        report['notes'].append('請先確認想預測的目標欄。資料型態無法決定使用者的業務目的。')
        return report
    numeric = _numeric(clean[target])
    nonmissing = clean[target].notna()
    is_numeric = bool(nonmissing.any() and numeric[nonmissing].notna().all())
    unique = clean[target].nunique()
    excluded = suggested_exclusions(frame, [target, time_column])
    if forecast_intent or time_column is not None:
        if not is_numeric:
            report['notes'].append('時間序列預測目前需要數值目標；這份目標非純數值。')
            return report
        if time_column is None and len(dates) == 1:
            time_column = dates[0]
        if time_column not in frame or time_column == target:
            report['notes'].append('未來預測需要明確的時間欄；請先確認 time_column。')
            return report
        times = _dates(clean[time_column])
        if times.isna().any() or times.duplicated().any():
            report['notes'].append('時間欄缺失／無法解析／重複，請先整理成單一序列。')
            return report
        task, model = 'time_series', 'auto'
        options = {'target': target, 'task': task, 'model': model, 'time_column': time_column,
                   'lookback': min(14, max(1, len(frame) // 10)), 'horizon': 1,
                   'excluded_columns': [c for c in excluded if c != time_column], 'feature_columns': []}
        report['notes'].append('已知要預測未來：建議歷史視窗與時間驗證。lookback 與 horizon 是初始建議，可依使用者目標調整。')
    else:
        task = 'regression' if is_numeric and unique > 20 else 'classification'
        options = {'target': target, 'task': task, 'model': 'auto', 'excluded_columns': excluded}
        if is_numeric and unique <= 20:
            report['notes'].append('數值目標只有少量不同值：先建議分類，但必須確認它是類別代碼還是連續數量。')
        if dates:
            report['notes'].append('有日期欄不代表一定是時間序列。請依預測目的確認同筆預測、未來預測或時間切分。')
        report['notes'].append('如同一客戶／商品有多列，請採群組或時間切分；不能僅依欄位型態確定獨立性。')
    report.update(suggested_options=options, recommendation_basis='transparent_rules_for_agent_review',
                  requires_intent_review=True)
    report['notes'].append('模型比較只用訓練集內的驗證集；測試集最後才評估。排除名單還需檢查預測時未知的欄位。')
    return report
