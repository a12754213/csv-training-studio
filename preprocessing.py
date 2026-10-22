"""表格資料準備：所有學習到的規則只從訓練集 fit。Python 3.10+。"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import warnings
import zipfile
from dataclasses import asdict, dataclass, field
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, classification_report,
    confusion_matrix, f1_score, mean_absolute_error, mean_squared_error, r2_score,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from text_features import SafeTextVectorizer, WordTokenizer, parse_quantity
from version import __version__

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_ROWS = 200_000
MAX_COLUMNS = 500
MAX_DENSE_CELLS = 2_000_000
DATE_PARTS = ("year", "month", "day", "dayofweek", "hour")
DEFAULT_MISSING_TOKENS: tuple[str, ...] = ()  # 預設只把空白當缺值，保留有效的 NA 類別。


class DataPreparationError(ValueError):
    """給使用者看的可修正資料問題。"""


def clean_frame(frame: pd.DataFrame, missing_tokens=()) -> pd.DataFrame:
    """不學習統計值的格式整理；保留前導零與類別的原始文字。"""
    result = frame.copy()
    markers = {"", *[str(x).strip() for x in missing_tokens]}
    for col in result.columns:
        s = result[col].astype("string").str.strip()
        result[col] = s.mask(s.isin(markers)).astype(object)
        result[col] = result[col].where(pd.notna(result[col]), np.nan)
    return result


def read_csv_bytes(content: bytes, encoding="auto", separator="auto"):
    if len(content) > MAX_UPLOAD_BYTES:
        raise DataPreparationError("支援 30 MB 以內的 CSV；請先分割大型檔案。")
    if not content.strip():
        raise DataPreparationError("檔案是空的。")
    encodings = [encoding] if encoding != "auto" else ["utf-8-sig", "utf-16", "cp950"]
    text = None
    chosen = None
    for enc in encodings:
        try:
            if enc == "utf-16" and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            text = content.decode(enc, errors="strict")
            chosen = enc
            break
        except (UnicodeError, LookupError):
            continue
    if text is None:
        raise DataPreparationError("無法解碼 CSV。請手動選擇編碼，或另存為 UTF-8 CSV。")
    if "\x00" in text:
        raise DataPreparationError("檔案含有 NUL 字元，可能不是 CSV 或編碼選錯。")
    if separator == "auto":
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    else:
        delimiter = separator
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        header = next((r for r in reader if r), [])
        names = [str(c).strip() for c in header]
        if not names or any(not name for name in names):
            raise DataPreparationError("每個欄位都需要名稱，請修正空白欄名。")
        if len(set(names)) != len(names):
            raise DataPreparationError("有重複欄名（或去掉空白後重複）；請先改成不同名稱。")
        if len(names) > MAX_COLUMNS:
            raise DataPreparationError(f"最多支援 {MAX_COLUMNS} 個原始欄位。")
        for row in reader:
            if row and len(row) != len(names):
                raise DataPreparationError(
                    f"CSV 第 {reader.line_num} 行的欄位數與標題不同；請檢查分隔符號、引號或缺少的逗號。"
                )
        frame = pd.read_csv(io.StringIO(text), sep=delimiter, header=0,
                            dtype=str, keep_default_na=False, on_bad_lines="error",
                            nrows=MAX_ROWS + 1)
        frame.columns = names
    except (pd.errors.ParserError, pd.errors.EmptyDataError, csv.Error) as exc:
        raise DataPreparationError(f"CSV 格式無法解析：{exc}") from exc
    if len(frame) > MAX_ROWS:
        raise DataPreparationError(f"最多支援 {MAX_ROWS:,} 筆資料。")
    if frame.empty:
        raise DataPreparationError("CSV 只有欄名，沒有資料。")
    return frame, {"encoding": chosen, "separator": delimiter, "rows": len(frame), "columns": len(names)}


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).astype(float)


def _dates(series: pd.Series) -> pd.Series:
    # 自動日期只接受明確年月日；手動日期模式才允許其他 pandas 可解析的表示法。
    return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")


def _identifier_name(name: str) -> bool:
    low = name.strip().lower()
    return bool(re.search(r"(^id$|^index$|^unnamed:|_id$|^id_|編號$|識別碼$|流水號$|電話|手機|email|e-mail)", low))


def infer_kind(series: pd.Series, column: str) -> str:
    present = series.dropna().astype(str)
    if present.empty:
        return "empty"
    if _identifier_name(column):
        return "identifier"
    if re.search(r"型號|型号|(^|_)(model|sku|code)($|_)", column.lower()):
        return "categorical"
    if present.str.match(r"^[+-]?0\d+$").any():
        return "categorical"  # 郵遞區號等前導零不自動抹掉。
    parsed = pd.to_numeric(present, errors="coerce")
    if parsed.notna().all():
        return "numeric"
    date_looking = present.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?$")
    if date_looking.all() and _dates(present).notna().all():
        return "datetime"
    if all(parse_quantity(v) is not None for v in present):
        return "quantity"
    if re.search(r"評論|评论|評價|评价|描述|備註|备注|留言|(^|_)(text|review|comment|description|message|notes?)($|_)", column.lower()):
        return "text"
    sentence_like = present.str.contains(r"[。！？!?，,；;]|\S+\s+\S+\s+\S+", regex=True)
    if present.str.len().mean() > 80 or (present.str.len().mean() >= 12 and sentence_like.mean() >= 0.6):
        return "text"
    return "categorical"


def profile_frame(frame: pd.DataFrame, missing_tokens=()) -> pd.DataFrame:
    clean = clean_frame(frame, missing_tokens)
    rows = []
    for col in clean.columns:
        s = clean[col]
        valid = s.dropna()
        kind = infer_kind(s, col)
        hints = []
        if kind == "identifier":
            hints.append("疑似識別碼；自動模式會排除，可手動改為特徵")
        elif kind == "text":
            hints.append("中文／英文斷詞並轉 TF-IDF；可在整理頁預覽與調整")
        elif kind == "quantity":
            hints.append("單一數字加明確單位；可拆分並換算相容單位，幣別不換匯")
        if len(valid) and kind == "categorical":
            ratio = _numeric(valid).notna().mean()
            if 0.8 <= ratio < 1:
                hints.append("多數可轉數值；請檢查單位、逗號或錯字再手動指定")
            quantity_count = sum(parse_quantity(v) is not None for v in valid)
            if 0 < quantity_count < len(valid):
                hints.append("部分值含可解析的數字與單位；請確認其他值後再手動指定，避免誤拆型號")
        if s.nunique(dropna=True) <= 1:
            hints.append("空欄或常數欄；是否排除以訓練集為準")
        if s.nunique(dropna=True) > 50 and kind == "categorical":
            hints.append("類別較多；訓練時將合併低頻類別")
        rows.append({"欄位": col, "推測類型": kind, "缺值數": int(s.isna().sum()),
                     "缺值率 (%)": round(float(s.isna().mean() * 100), 2),
                     "不同值數": int(s.nunique(dropna=True)),
                     "範例": " | ".join(str(v)[:45] for v in valid.head(3)),
                     "提醒": "；".join(hints)})
    return pd.DataFrame(rows)


def preview_transformations(frame, column_roles=None, missing_tokens=(), normalize_units=True,
                            custom_words=(), stop_words=(), lowercase=True,
                            max_text_chars=20000, sample_rows=5, columns=None):
    """只顯示確定性的解析結果；不建立詞彙表、不計算 IDF 或補值統計。"""
    clean = clean_frame(frame, missing_tokens)
    tokenizer = WordTokenizer(custom_words, stop_words, lowercase)
    records = []
    for col in (columns if columns is not None else clean.columns):
        role = (column_roles or {}).get(col, "auto")
        kind = infer_kind(clean[col], col) if role == "auto" else role
        for value in clean[col].head(sample_rows):
            missing = pd.isna(value)
            converted = "缺值；依訓練集規則處理"
            if not missing:
                if kind == "text":
                    tokens = tokenizer(str(value)[:max_text_chars])
                    converted = " | ".join(tokens[:60]) or "沒有可用詞彙"
                    if len(tokens) > 60:
                        converted += " …（只預覽前 60 個 token）"
                    if len(str(value)) > max_text_chars:
                        converted += f"；文字截至前 {max_text_chars:,} 字"
                elif kind == "quantity":
                    parsed = parse_quantity(value, normalize_units)
                    converted = (f"{parsed.value:g} {parsed.unit} → {parsed.normalized_value:g} "
                                 f"{parsed.normalized_unit}（{parsed.dimension}）") if parsed else "無法辨識；以缺值及解析失敗指示標記"
                elif kind in {"identifier", "ignore"}:
                    converted = "排除特徵；原始資料仍保留"
                elif kind == "categorical":
                    converted = "保留完整字串，再做類別編碼"
                elif kind == "numeric":
                    converted = "數值；補值與縮放由訓練集決定"
                elif kind == "datetime":
                    converted = "日期；展開成年／月／日／星期／小時"
            records.append({"欄位": col, "類型": kind, "原始值": "（缺值）" if missing else str(value)[:300],
                            "處理預覽": converted})
    return pd.DataFrame(records, columns=["欄位", "類型", "原始值", "處理預覽"])


def numeric_summary(frame: pd.DataFrame, missing_tokens=()) -> pd.DataFrame:
    """全表 EDA，僅供觀察；這些統計不會用於補值或欄位選擇。"""
    clean = clean_frame(frame, missing_tokens)
    records = []
    for col in clean:
        if infer_kind(clean[col], col) != "numeric":
            continue
        values = _numeric(clean[col]).dropna()
        if values.empty:
            continue
        q1, median, q3 = values.quantile([0.25, 0.5, 0.75])
        iqr = q3 - q1
        suspects = int(((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).sum()) if iqr > 0 else None
        records.append({"欄位": col, "有效筆數": len(values), "平均": values.mean(),
                        "標準差": values.std(ddof=0), "最小": values.min(), "中位數": median,
                        "最大": values.max(), "IQR 疑似離群筆數": suspects})
    return pd.DataFrame(records)


class TabularPreprocessor(BaseEstimator, TransformerMixin):
    """可直接放入 sklearn Pipeline / CV 的有狀態前處理器。"""

    def __init__(self, column_roles=None, missing_tokens=(), numeric_strategy="median",
                 categorical_strategy="most_frequent", scale_numeric=True,
                 missing_indicators=True, max_categories=50, min_frequency=2,
                 drop_missing_above=0.95, drop_constant=True,
                 text_max_features=5000, text_min_df=1, text_ngram_range=(1, 2),
                 custom_words=(), stop_words=(), text_lowercase=True,
                 max_text_chars=20000, normalize_units=True):
        self.column_roles = column_roles
        self.missing_tokens = missing_tokens
        self.numeric_strategy = numeric_strategy
        self.categorical_strategy = categorical_strategy
        self.scale_numeric = scale_numeric
        self.missing_indicators = missing_indicators
        self.max_categories = max_categories
        self.min_frequency = min_frequency
        self.drop_missing_above = drop_missing_above
        self.drop_constant = drop_constant
        self.text_max_features = text_max_features
        self.text_min_df = text_min_df
        self.text_ngram_range = text_ngram_range
        self.custom_words = custom_words
        self.stop_words = stop_words
        self.text_lowercase = text_lowercase
        self.max_text_chars = max_text_chars
        self.normalize_units = normalize_units

    def fit(self, X, y=None):
        if not isinstance(X, pd.DataFrame) or X.columns.duplicated().any():
            raise DataPreparationError("前處理需要欄名唯一的 pandas DataFrame。")
        if self.numeric_strategy not in {"mean", "median", "constant"}:
            raise DataPreparationError("數值補值策略必須是 median、mean 或 constant。")
        if self.categorical_strategy not in {"most_frequent", "constant"}:
            raise DataPreparationError("類別補值策略必須是 most_frequent 或 constant。")
        clean = clean_frame(X, self.missing_tokens)
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        self.specs_ = []
        self.decisions_ = []
        roles = self.column_roles or {}
        for i, col in enumerate(clean.columns):
            s = clean[col]
            requested = roles.get(col, "auto")
            if requested not in {"auto", "numeric", "categorical", "datetime", "text", "quantity", "ignore"}:
                raise DataPreparationError(f"{col} 的欄位角色無效。")
            kind = infer_kind(s, col) if requested == "auto" else requested
            reason = ""
            if kind in {"identifier", "empty", "ignore"}:
                reason = {"identifier": "疑似識別碼",
                          "empty": "訓練集全缺值", "ignore": "使用者排除"}[kind]
            evaluated = _numeric(s) if kind == "numeric" else (_dates(s) if kind == "datetime" else s)
            quantities = None
            if kind == "quantity":
                quantities = [parse_quantity(v, self.normalize_units) for v in s]
                evaluated = pd.Series([None if q is None else (q.dimension, q.normalized_value)
                                       for q in quantities], index=s.index, dtype=object)
            missing_ratio = float(evaluated.isna().mean())
            if not reason and evaluated.isna().all():
                reason = "訓練集全缺值或無法轉換"
            if not reason and missing_ratio > self.drop_missing_above:
                reason = "訓練集缺值率超過門檻"
            if not reason and self.drop_constant and evaluated.nunique(dropna=True) <= 1:
                reason = "訓練集為常數欄"
            self.decisions_.append({"column": col, "requested": requested, "kind": kind,
                                    "action": "drop" if reason else "keep", "reason": reason,
                                    "train_missing_rate_after_conversion": missing_ratio})
            if not reason:
                spec = {"column": col, "kind": kind, "key": f"f{i:04d}_{col}"}
                if kind == "text":
                    spec["transformer"] = f"text{i:04d}"
                if kind == "quantity":
                    spec["dimensions"] = dict(sorted({q.dimension: q.normalized_unit for q in quantities if q is not None}.items()))
                self.specs_.append(spec)
        if not self.specs_:
            raise DataPreparationError("沒有可用特徵。請檢查是否全為缺值、常數或識別碼，並調整欄位角色。")
        prepared, nums, cats = self._prepare(clean)
        self.numeric_columns_ = nums
        self.categorical_columns_ = cats
        self.missing_category_ = "__MISSING__"
        while cats and any((prepared[c] == self.missing_category_).any() for c in cats):
            self.missing_category_ += "_"
        transforms = []
        if nums:
            numeric_steps = [("imputer", SimpleImputer(
                strategy=self.numeric_strategy, fill_value=0,
                add_indicator=self.missing_indicators, keep_empty_features=True))]
            if self.scale_numeric:
                numeric_steps.append(("scaler", StandardScaler()))
            transforms.append(("num", Pipeline(numeric_steps), nums))
        if cats:
            cat_pipe = Pipeline([
                ("imputer", SimpleImputer(strategy=self.categorical_strategy,
                                          fill_value=self.missing_category_, keep_empty_features=True)),
                ("encoder", OneHotEncoder(handle_unknown="infrequent_if_exist", sparse_output=True,
                                           max_categories=self.max_categories,
                                           min_frequency=self.min_frequency, dtype=np.float64)),
            ])
            transforms.append(("cat", cat_pipe, cats))
        for spec in self.specs_:
            if spec["kind"] == "text":
                vectorizer = SafeTextVectorizer(
                    max_features=self.text_max_features, min_df=self.text_min_df,
                    ngram_range=self.text_ngram_range, custom_words=self.custom_words,
                    stop_words=self.stop_words, lowercase=self.text_lowercase,
                    max_text_chars=self.max_text_chars)
                transforms.append((spec["transformer"], vectorizer, spec["key"]))
        self.transformer_ = ColumnTransformer(transforms, remainder="drop", sparse_threshold=1.0)
        self.transformer_.fit(prepared)
        self.output_names_ = self.transformer_.get_feature_names_out()
        self.training_categories_ = {s["column"]: set(clean[s["column"]].dropna().astype(str))
                                     for s in self.specs_ if s["kind"] == "categorical"}
        return self

    def _prepare(self, clean):
        prepared = pd.DataFrame(index=clean.index)
        nums, cats = [], []
        for spec in self.specs_:
            col, key, kind = spec["column"], spec["key"], spec["kind"]
            if col not in clean:
                raise DataPreparationError(f"新資料缺少必要欄位：{col}")
            if kind == "numeric":
                prepared[key] = _numeric(clean[col]); nums.append(key)
            elif kind == "datetime":
                dates = _dates(clean[col])
                for part in DATE_PARTS:
                    name = f"{key}_{part}"
                    prepared[name] = getattr(dates.dt, part).astype(float); nums.append(name)
            elif kind == "text":
                prepared[key] = clean[col].fillna("").astype(str)
                if self.missing_indicators:
                    name = f"{key}_text_missing"
                    prepared[name] = clean[col].isna().astype(float); nums.append(name)
            elif kind == "quantity":
                quantities = [parse_quantity(v, self.normalize_units) for v in clean[col]]
                for dimension, unit in spec["dimensions"].items():
                    selected = [q is not None and q.dimension == dimension for q in quantities]
                    name = f"{key}_{dimension}_value_{unit}"
                    prepared[name] = [q.normalized_value if take else 0.0 for q, take in zip(quantities, selected)]
                    nums.append(name)
                    present = f"{key}_{dimension}_present"
                    prepared[present] = np.asarray(selected, dtype=float); nums.append(present)
                # 已知／未知量綱均保留單位類別。未知量綱不能臨時新增數值欄。
                name = f"{key}_unit"
                prepared[name] = [q.normalized_unit if q is not None else np.nan for q in quantities]; cats.append(name)
                flags = {"missing": clean[col].isna().to_numpy(),
                         "invalid": [q is None and pd.notna(v) for q, v in zip(quantities, clean[col])],
                         "unseen_dimension": [q is not None and q.dimension not in spec["dimensions"] for q in quantities]}
                for suffix, values in flags.items():
                    name = f"{key}_{suffix}"
                    prepared[name] = np.asarray(values, dtype=float); nums.append(name)
            else:
                prepared[key] = clean[col].astype(object); cats.append(key)
        return prepared, nums, cats

    def transform(self, X):
        check_is_fitted(self, "transformer_")
        clean = clean_frame(X, self.missing_tokens)
        prepared, _, _ = self._prepare(clean)
        matrix = sparse.csr_matrix(self.transformer_.transform(prepared), dtype=np.float64)
        if not np.isfinite(matrix.data).all():
            raise DataPreparationError("前處理後仍有非有限數值，請檢查數值的極端大小。")
        return matrix

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "output_names_")
        return self.output_names_.copy()

    def audit(self, X):
        check_is_fitted(self, "transformer_")
        clean = clean_frame(X, self.missing_tokens)
        items = []
        for spec in self.specs_:
            col, kind = spec["column"], spec["kind"]
            if col not in clean:
                raise DataPreparationError(f"新資料缺少必要欄位：{col}")
            s = clean[col]
            invalid, unknown = 0, 0
            if kind == "numeric":
                invalid = int((s.notna() & _numeric(s).isna()).sum())
            elif kind == "datetime":
                invalid = int((s.notna() & _dates(s).isna()).sum())
            elif kind == "categorical":
                unknown = int((s.notna() & ~s.isin(self.training_categories_[col])).sum())
            extra = {}
            if kind == "text":
                extra = self.transformer_.named_transformers_[spec["transformer"]].audit(s)
            elif kind == "quantity":
                parsed = [parse_quantity(v, self.normalize_units) for v in s]
                invalid = sum(q is None and pd.notna(v) for q, v in zip(parsed, s))
                extra["unseen_quantity_dimensions"] = sum(q is not None and q.dimension not in spec["dimensions"] for q in parsed)
            items.append({"column": col, "kind": kind, "missing_input": int(s.isna().sum()),
                          "invalid_converted_to_missing": int(invalid), "unknown_categories": unknown, **extra})
        return items

    def learned_values(self):
        check_is_fitted(self, "transformer_")
        result = {}
        if self.numeric_columns_:
            imp = self.transformer_.named_transformers_["num"].named_steps["imputer"]
            result["numeric_fill"] = {k: float(v) for k, v in zip(self.numeric_columns_, imp.statistics_)}
        if self.categorical_columns_:
            cat = self.transformer_.named_transformers_["cat"]
            result["categorical_fill"] = dict(zip(self.categorical_columns_, cat.named_steps["imputer"].statistics_.tolist()))
            result["category_counts"] = {k: len(v) for k, v in zip(self.categorical_columns_, cat.named_steps["encoder"].categories_)}
        text_columns = {}
        for spec in self.specs_:
            if spec["kind"] == "text":
                vectorizer = self.transformer_.named_transformers_[spec["transformer"]]
                text_columns[spec["column"]] = {"vocabulary_size": vectorizer.vocabulary_size_,
                    "example_tokens": vectorizer.get_feature_names_out()[:30].tolist(),
                    "empty_vocabulary_warning": vectorizer.empty_reason_}
        if text_columns:
            result["text_columns"] = text_columns
        quantities = {spec["column"]: spec["dimensions"] for spec in self.specs_ if spec["kind"] == "quantity"}
        if quantities:
            result["quantity_columns"] = quantities
        return result

    def text_vocabularies(self):
        check_is_fitted(self, "transformer_")
        return {spec["column"]: self.transformer_.named_transformers_[spec["transformer"]].vocabulary_records()
                for spec in self.specs_ if spec["kind"] == "text"}

    def preview(self, X, sample_rows=3):
        check_is_fitted(self, "transformer_")
        return preview_transformations(
            X, {spec["column"]: spec["kind"] for spec in self.specs_}, self.missing_tokens,
            self.normalize_units, self.custom_words, self.stop_words, self.text_lowercase,
            self.max_text_chars, sample_rows, [spec["column"] for spec in self.specs_])


@dataclass
class PrepConfig:
    target: str
    task: str = "classification"
    test_size: float = 0.2
    seed: int = 42
    split_mode: str = "random"
    split_column: str | None = None
    deduplicate: bool = True
    preprocessor: dict = field(default_factory=dict)
    excluded_columns: tuple[str, ...] = ()
    model: str = "baseline"


@dataclass
class PreparedData:
    config: PrepConfig
    raw_train: pd.DataFrame
    raw_test: pd.DataFrame
    unlabeled: pd.DataFrame
    X_train: sparse.csr_matrix
    X_test: sparse.csr_matrix
    y_train: pd.Series
    y_test: pd.Series
    preprocessor: TabularPreprocessor
    report: dict


def prepare_data(frame: pd.DataFrame, config: PrepConfig) -> PreparedData:
    if config.target not in frame:
        raise DataPreparationError("請先選擇目標欄位。")
    if config.task not in {"classification", "regression"}:
        raise DataPreparationError("請指定分類或回歸任務。")
    if config.model not in {"baseline", "random_forest", "auto"}:
        raise DataPreparationError("表格模型支援 baseline、random_forest 或 auto。")
    unknown = set(config.excluded_columns) - set(frame.columns)
    if unknown:
        raise DataPreparationError(f"排除清單含不存在的欄位：{sorted(unknown)}")
    if config.target in config.excluded_columns:
        raise DataPreparationError("目標欄位不能同時列入排除清單。")
    if not 0.1 <= config.test_size <= 0.4:
        raise DataPreparationError("測試集比例需介於 10% 到 40%。")
    clean = clean_frame(frame.reset_index(drop=True), config.preprocessor.get("missing_tokens", ()))
    input_count = len(clean)
    duplicates = int(clean.duplicated().sum())
    if config.deduplicate:
        clean = clean.drop_duplicates()
    unlabeled = clean.loc[clean[config.target].isna()].copy()
    labeled = clean.loc[clean[config.target].notna()].copy()
    if len(labeled) < 10:
        raise DataPreparationError("有標籤且去重後的資料不足 10 筆，無法建立有意義的訓練／測試切分。")
    if config.task == "regression":
        numeric_target = _numeric(labeled[config.target])
        if numeric_target.isna().any():
            raise DataPreparationError("回歸的目標欄含非數值或無限值；請先修正，目標值不會自動補值。")
        labeled[config.target] = numeric_target
    else:
        classes = labeled[config.target].value_counts()
        if len(classes) < 2:
            raise DataPreparationError("分類目標至少需要兩種類別。")
        if len(classes) > 100:
            raise DataPreparationError("分類目標超過 100 種；請確認是不是連續數值，應改選回歸。")
    y = labeled[config.target]
    indices = np.arange(len(labeled))
    if config.split_mode == "random":
        try:
            train_idx, test_idx = train_test_split(indices, test_size=config.test_size,
                                                  random_state=config.seed,
                                                  stratify=y if config.task == "classification" else None)
        except ValueError as exc:
            raise DataPreparationError("無法分層切分：每類至少需 2 筆，訓練與測試筆數也需涵蓋所有類別。請增加樣本或調整比例。") from exc
    elif config.split_mode in {"group", "time"}:
        column = config.split_column
        if column not in labeled or column == config.target:
            raise DataPreparationError("請選擇有效且不同於目標的分組／時間欄位。")
        if labeled[column].isna().any():
            raise DataPreparationError("分組／時間欄不能有缺值；請先修正。")
        if config.split_mode == "group":
            groups = labeled[column]
            if groups.nunique() < 2:
                raise DataPreparationError("分組切分至少需要兩個不同群組。")
            splitter = GroupShuffleSplit(n_splits=1, test_size=config.test_size, random_state=config.seed)
            train_idx, test_idx = next(splitter.split(labeled, y, groups))
        else:
            times = _dates(labeled[column])
            if times.isna().any():
                raise DataPreparationError("時間欄含無法解析的日期；建議先統一成 YYYY-MM-DD HH:MM:SS。")
            ordered = np.argsort(times.to_numpy(), kind="stable")
            cut = max(1, int(math.floor(len(labeled) * (1 - config.test_size))))
            boundary = times.iloc[ordered[cut]]
            train_idx = ordered[(times.iloc[ordered] < boundary).to_numpy()]
            test_idx = ordered[(times.iloc[ordered] >= boundary).to_numpy()]
    else:
        raise DataPreparationError("不支援的切分模式。")
    if len(train_idx) < 4 or len(test_idx) < 2:
        raise DataPreparationError("切分後訓練集不足 4 筆或測試集不足 2 筆；請調整資料量／比例。")
    raw_train, raw_test = labeled.iloc[train_idx].copy(), labeled.iloc[test_idx].copy()
    y_train, y_test = raw_train[config.target].copy(), raw_test[config.target].copy()
    if config.task == "classification":
        if y_train.nunique() < 2:
            raise DataPreparationError("訓練集只有一種類別，請調整切分或增加資料。")
        unseen = set(y_test) - set(y_train)
        if unseen:
            raise DataPreparationError(f"測試集有訓練集未出現的目標類別：{sorted(unseen)}。請檢查類別與切分設計。")
    excluded = [config.target, *config.excluded_columns]
    if config.split_mode in {"group", "time"}:
        excluded.append(config.split_column)
    feature_cols = [c for c in labeled.columns if c not in excluded]
    if not feature_cols:
        raise DataPreparationError("排除選定欄位、目標與切分欄後，沒有特徵欄位。")
    preprocessor = TabularPreprocessor(**config.preprocessor)
    X_train = preprocessor.fit_transform(raw_train[feature_cols])
    X_test = preprocessor.transform(raw_test[feature_cols])
    explicit_decisions = [{"column": c, "requested": "ignore", "kind": "ignore",
                           "action": "drop", "reason": "使用者排除"}
                          for c in dict.fromkeys(config.excluded_columns)]
    notes = ["缺失目標列已隔離，沒有推測或補填標籤。", "所有補值、類別字典、TF-IDF 詞彙與 IDF、縮放及自動欄位選擇只在訓練集 fit。",
             "日期展開不代表已完成時間序列預測；預測時尚未知的欄位需自行排除。",
             "測試集僅供最終評估；不要反覆看測試分數調參。"]
    if duplicates and not config.deduplicate:
        notes.append("保留了完全重複列；重複資料可能跨集合，建議去重或按實體分組。")
    if config.split_mode == "group":
        notes.append("分組切分按群組數決定比例，實際資料列比例可能不同；分組欄不當特徵。")
    elif config.split_mode == "time":
        notes.append("較早時間用於訓練，較晚時間用於測試；相同時間不會跨集合，時間切分欄不當特徵。")
    if config.task == "classification" and y_train.value_counts(normalize=True).max() > 0.9:
        notes.append("目標類別不平衡，請同時看 balanced accuracy、macro-F1 與各類別 Recall。")
    learned = preprocessor.learned_values()
    for column, details in learned.get("text_columns", {}).items():
        if details["empty_vocabulary_warning"]:
            notes.append(f"{column}：{details['empty_vocabulary_warning']}；保留一個零值佔位特徵，請調整文字設定。")
    if learned.get("text_columns"):
        notes.append(f"文字每筆最多處理前 {preprocessor.max_text_chars:,} 字；截斷及非空文字的零向量筆數列在檢查報告。")
    if learned.get("quantity_columns"):
        notes.append("數字與單位按量綱分欄；缺值／解析失敗以 0 及指示欄表示。新量綱不新增欄位，會標示為未知。幣別不換匯。")
    report = {
        "version": __version__, "config": asdict(config),
        "rows": {"input": input_count, "duplicate_rows_found": duplicates,
                 "duplicates_removed": duplicates if config.deduplicate else 0,
                 "missing_target_quarantined": len(unlabeled),
                 "train": len(raw_train), "test": len(raw_test)},
        "feature_columns": feature_cols, "feature_count": X_train.shape[1],
        "excluded_columns": list(dict.fromkeys(config.excluded_columns)),
        "used_feature_columns": [spec["column"] for spec in preprocessor.specs_],
        "output_feature_names": preprocessor.get_feature_names_out().tolist(),
        "column_decisions": explicit_decisions + preprocessor.decisions_,
        "learned_from_training_only": learned,
        "train_audit": preprocessor.audit(raw_train), "test_audit": preprocessor.audit(raw_test),
        "finite_output": bool(np.isfinite(X_train.data).all() and np.isfinite(X_test.data).all()),
        "class_counts_train": y_train.value_counts().to_dict() if config.task == "classification" else None,
        "class_counts_test": y_test.value_counts().to_dict() if config.task == "classification" else None,
        "notes": notes,
        "environment": {"numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__,
                        "scikit-learn": sklearn.__version__, "joblib": joblib.__version__,
                        "jieba": package_version("jieba")},
    }
    return PreparedData(config, raw_train, raw_test, unlabeled, X_train, X_test, y_train, y_test, preprocessor, report)


def _scores(y_true, predictions, task):
    if task == "classification":
        return {"accuracy": float(accuracy_score(y_true, predictions)),
                "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
                "macro_f1": float(f1_score(y_true, predictions, average="macro", zero_division=0))}
    return {"mae": float(mean_absolute_error(y_true, predictions)),
            "rmse": float(np.sqrt(mean_squared_error(y_true, predictions))),
            "r2": float(r2_score(y_true, predictions))}


def train_baseline(preprocessor, X_train, X_test, y_train, y_test, task, seed=42, model_name="baseline"):
    if model_name not in {"baseline", "random_forest"}:
        raise DataPreparationError("模型必須為 baseline 或 random_forest。")
    if task == "classification":
        estimator = LogisticRegression(max_iter=1500, class_weight="balanced", random_state=seed)
        dummy = DummyClassifier(strategy="most_frequent")
    else:
        estimator = Ridge(alpha=1.0, solver="lsqr")
        dummy = DummyRegressor(strategy="mean")
    if model_name == "random_forest":
        cls = RandomForestClassifier if task == "classification" else RandomForestRegressor
        kwargs = {"class_weight": "balanced_subsample"} if task == "classification" else {}
        estimator = cls(n_estimators=150, max_depth=12, min_samples_leaf=2, n_jobs=1,
                        random_state=seed, **kwargs)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        estimator.fit(X_train, y_train)
        prediction = estimator.predict(X_test)
        dummy.fit(X_train, y_train)
        metrics = {"model": estimator.__class__.__name__, "test_scores": _scores(y_test, prediction, task),
                   "dummy_scores": _scores(y_test, dummy.predict(X_test), task)}
    metrics["warnings"] = list(dict.fromkeys(str(w.message) for w in captured))
    if task == "classification":
        metrics["classification_report"] = classification_report(y_test, prediction, output_dict=True, zero_division=0)
        metrics["classes"] = estimator.classes_.tolist()
        metrics["confusion_matrix"] = confusion_matrix(y_test, prediction, labels=estimator.classes_).tolist()
    model = Pipeline([("preprocess", preprocessor), ("model", estimator)])
    predictions = pd.DataFrame({"actual": np.asarray(y_test), "prediction": prediction}, index=y_test.index)
    return model, metrics, predictions


def json_text(data) -> str:
    def convert(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        raise TypeError(f"Unsupported JSON type: {type(value)}")
    return json.dumps(data, ensure_ascii=False, indent=2, default=convert, allow_nan=False)


def _csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")


def make_training_bundle(data: PreparedData, trained=None) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, matrix in [("X_train", data.X_train), ("X_test", data.X_test)]:
            buff = io.BytesIO(); sparse.save_npz(buff, matrix); z.writestr(f"{name}.npz", buff.getvalue())
        for name, series in [("y_train", data.y_train), ("y_test", data.y_test)]:
            z.writestr(f"{name}.csv", _csv_bytes(pd.DataFrame({data.config.target: series.to_numpy()})))
        z.writestr("raw_train.csv", _csv_bytes(data.raw_train))
        z.writestr("raw_test.csv", _csv_bytes(data.raw_test))
        if not data.unlabeled.empty:
            z.writestr("unlabeled_rows.csv", _csv_bytes(data.unlabeled))
        manifest = pd.DataFrame({"source_data_row": list(data.raw_train.index + 1) + list(data.raw_test.index + 1),
                                 "split": ["train"] * len(data.raw_train) + ["test"] * len(data.raw_test)})
        z.writestr("row_manifest.csv", _csv_bytes(manifest))
        z.writestr("feature_names.json", json_text(data.preprocessor.get_feature_names_out().tolist()))
        z.writestr("text_vocabulary.json", json_text(data.preprocessor.text_vocabularies()))
        z.writestr("transformation_preview.csv", _csv_bytes(data.preprocessor.preview(data.raw_train)))
        z.writestr("report.json", json_text(data.report))
        z.writestr("config.json", json_text(asdict(data.config)))
        buff = io.BytesIO(); joblib.dump(data.preprocessor, buff); z.writestr("preprocessor.joblib", buff.getvalue())
        if (data.X_train.shape[0] + data.X_test.shape[0]) * data.X_train.shape[1] <= MAX_DENSE_CELLS:
            names = data.preprocessor.get_feature_names_out()
            z.writestr("X_train.csv", _csv_bytes(pd.DataFrame(data.X_train.toarray(), columns=names)))
            z.writestr("X_test.csv", _csv_bytes(pd.DataFrame(data.X_test.toarray(), columns=names)))
        if trained is not None:
            model, metrics, predictions = trained
            buff = io.BytesIO(); joblib.dump(model, buff); z.writestr("model.joblib", buff.getvalue())
            z.writestr("metrics.json", json_text(metrics))
            z.writestr("test_predictions.csv", _csv_bytes(predictions.reset_index(names="source_index")))
        here = Path(__file__).resolve().parent
        for filename in ["preprocessing.py", "text_features.py", "version.py", "train.py", "predict.py", "automl.py"]:
            z.writestr(filename, (here / filename).read_bytes())
        exact = "\n".join(f"{name}=={version}" for name, version in data.report["environment"].items())
        z.writestr("requirements.txt", exact + "\n")
        z.writestr("README.md", BUNDLE_README)
    return stream.getvalue()


BUNDLE_README = """# 可訓練資料包

這個資料包由 CSV Training Studio 產生。先解壓縮並進入資料夾：

```powershell
python -m pip install -r requirements.txt
python train.py --data .
python predict.py --model model.joblib --csv 新資料.csv --output predictions.csv
```

若匯出時已試跑模型，內含 model.joblib，可直接預測。模型已包含前處理，
predict.py 接受原始欄位；不要先自行編碼或標準化。

- X_train.npz / X_test.npz：可直接交給支援 scipy sparse 的 sklearn 模型。
- y_train.csv / y_test.csv：目標標籤，與對應 X 的列順序一致；分類保留原始類別字串。
- 小型輸出另附 X_train.csv / X_test.csv；大資料只輸出 NPZ，避免展開吃光記憶體。
- raw_train.csv / raw_test.csv：切分後、尚未學習補值與編碼的資料，保留原始欄位。
- row_manifest.csv：原始資料的第幾筆（從 1 起算，不含欄名；不是實際 CSV 文字行號）。
- unlabeled_rows.csv（如有）：沒有目標值而隔離的列，不會被偷偷補上答案。
- preprocessor.joblib + preprocessing.py + text_features.py：只從訓練集學到的規則與實作。
- text_vocabulary.json：各文字欄的詞彙、欄內索引及 IDF（只由訓練集建立）。
- transformation_preview.csv：訓練集前幾筆的斷詞／單位處理預覽。
- report.json：欄位選擇、補值統計、轉換失敗、新類別數、資料切分與環境版本。
- config.json / feature_names.json：可重現設定與輸出欄位順序。

## 使用邊界

這是一般表格分類／回歸流程；AutoML 僅比較有限候選模型，並用訓練集內的驗證資料選模，
不會自動理解業務規則、確認因果關係或保證準確率。
請排除預測當下尚未知的欄位。同一人多筆要分組切分；時間資料需檢查時間範圍、預測跨度與重疊。
不自動截斷離群值、不補目標、不做 SMOTE。文字以 jieba／英文分詞及 TF-IDF 表示，並非語意嵌入模型。
每筆文字預設最多處理前 20,000 字，可在設定中調整；截斷和零向量數見 report.json。
數字與單位只解析明確支援的單一數量，例如 30cm、500元、NT$1,200、50%。
長度／重量等相容單位可換算；不同幣別分開，元不猜幣別。範圍、複合尺寸及裸 $ 不自動猜。
缺失／解析失敗的量值用 0 及指示欄表示，不跨單位猜補；新量綱只標記、不新增特徵。
每個日期欄展開為年／月／日／星期／小時，時區會統一到 UTC。

## 交叉驗證

不要直接在已對整個訓練集 fit 過的 X_train.npz 上做嚴格交叉驗證。
請用 raw_train.csv，將新的 TabularPreprocessor 與模型放進同一條 sklearn Pipeline，
讓每一折各自 fit。分組／時間資料須搭配 GroupKFold／TimeSeriesSplit 等合適切分。
測試集只用來做最終評估，不要反覆看分數挑模型。

## 環境

requirements.txt 鎖定產生資料包時的套件版本；更換 Python 或 sklearn 版本時，
請回到原始 CSV 重新建立資料包。joblib 檔請只載入自己產生且信任的檔案。
"""
