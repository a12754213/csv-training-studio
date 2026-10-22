"""Small, bounded model selection using only the outer training split."""
from dataclasses import replace
from preprocessing import DataPreparationError, prepare_data, train_baseline


def train_prepared(data):
    selected = data.config.model
    comparison = []
    if selected == 'auto':
        try:
            inner = prepare_data(data.raw_train, replace(data.config, test_size=0.2, model='baseline'))
        except DataPreparationError as exc:
            raise DataPreparationError(f'訓練集不足以再分出驗證集，請改用單一基準模型：{exc}') from exc
        for name in ('baseline', 'random_forest'):
            result = train_baseline(inner.preprocessor, inner.X_train, inner.X_test,
                                    inner.y_train, inner.y_test, inner.config.task, inner.config.seed, name)
            scores = result[1]['test_scores']
            comparison.append({'candidate': name, 'model': result[1]['model'], 'validation_scores': scores})
        metric = 'macro_f1' if data.config.task == 'classification' else 'mae'
        choose = max if data.config.task == 'classification' else min
        selected = choose(comparison, key=lambda r: r['validation_scores'][metric])['candidate']
    trained = train_baseline(data.preprocessor, data.X_train, data.X_test,
                             data.y_train, data.y_test, data.config.task, data.config.seed, selected)
    if comparison:
        trained[1].update(selected_model=selected, selection_metric=metric,
                          model_comparison=comparison, selection_data='inner_validation_only',
                          selection_rows={'train': len(inner.y_train), 'validation': len(inner.y_test)})
    return trained
