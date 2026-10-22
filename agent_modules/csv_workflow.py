"""CSV tools reuse the original, audited preprocessing and training service."""
from __future__ import annotations

from agent_hub import AgentContext, AgentRegistry, Capability


def inspect(context: AgentContext, params: dict) -> dict:
    from preprocessing import profile_frame, read_csv_bytes
    from training_service import suggested_exclusions
    frame, file_info = read_csv_bytes(context.payload, context.encoding, context.separator)
    return {'filename': context.filename, 'file': file_info,
            'rows': len(frame), 'columns': list(frame.columns),
            'suggested_excluded_columns': suggested_exclusions(frame),
            'profile': profile_frame(frame).to_dict(orient='records')}


def plan(context: AgentContext, params: dict) -> dict:
    from agent_planner import suggest_plan
    return suggest_plan(context.payload, target=params.get('target'),
                        time_column=params.get('time_column'),
                        forecast_intent=bool(params.get('forecast_intent', False)),
                        encoding=context.encoding, separator=context.separator)


def train(context: AgentContext, params: dict) -> dict:
    from preprocessing import DataPreparationError
    from training_service import run_training_bytes
    allowed = {'target', 'task', 'model', 'excluded_columns', 'test_size',
               'split_mode', 'split_column', 'time_column', 'lookback', 'horizon',
               'feature_columns', 'include_lstm', 'lstm_epochs', 'lstm_units',
               'preprocessor', 'seed', 'deduplicate'}
    unknown = set(params) - allowed
    if unknown:
        raise DataPreparationError(f'未知訓練設定：{sorted(unknown)}')
    if not params.get('target'):
        raise DataPreparationError('必須先確認目標欄位，不能自行猜測。')
    options = dict(params)
    options.update(encoding=context.encoding, separator=context.separator)
    bundle, summary = run_training_bytes(context.payload, options)
    return {'bundle': bundle, 'summary': summary}


def register(registry: AgentRegistry) -> None:
    registry.register(Capability('csv.inspect', 'CSV 欄位與資料品質概況', inspect))
    registry.register(Capability('csv.plan', '建議分類／回歸／時間序列與排除欄位', plan))
    registry.register(Capability('csv.train', '沿用原訓練引擎訓練、評估並輸出 ZIP', train,
                                 requires_approval=True))
