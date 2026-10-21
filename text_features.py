"""文字特徵與明確數字／單位解析；沒有外部 API，也不以測試資料建立詞彙。"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import math
import re
import unicodedata

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.utils.validation import check_is_fitted


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value))


@lru_cache(maxsize=2)
def _segmenter(custom_words: tuple[str, ...]):
    import jieba
    jieba.setLogLevel(logging.WARNING)
    # 每份自訂字典使用獨立實例，避免其他欄位／使用者的字典污染結果。
    tokenizer = jieba.Tokenizer()
    tokenizer.initialize()
    for word in custom_words:
        tokenizer.add_word(word, freq=10_000_000)
    return tokenizer


class WordTokenizer:
    """中文斷詞；英文、數字及 RTX4070／AB-123 等連續代碼保留為完整 token。"""

    def __init__(self, custom_words=(), stop_words=(), lowercase=True):
        self.custom_words = custom_words
        self.stop_words = stop_words
        self.lowercase = lowercase

    def __call__(self, text):
        text = normalize_text(text)
        if self.lowercase:
            text = text.lower()
        normalize = lambda w: normalize_text(w).lower() if self.lowercase else normalize_text(w)
        custom = tuple(sorted({normalize(w).strip() for w in self.custom_words if str(w).strip()}))
        stops = {normalize(w).strip() for w in self.stop_words if str(w).strip()}
        tokens = []
        for chunk in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*", text):
            if re.match(r"[\u3400-\u4dbf\u4e00-\u9fff]", chunk):
                words = _segmenter(custom).cut(chunk, HMM=True)
            else:
                words = [chunk]
            tokens.extend(w for w in words if w.strip() and w not in stops)
        return tokens


class SafeTextVectorizer(BaseEstimator, TransformerMixin):
    """可序列化且能處理全空詞彙的 TF-IDF；每個文字欄獨立 fit。"""

    def __init__(self, max_features=5000, min_df=1, ngram_range=(1, 2),
                 custom_words=(), stop_words=(), lowercase=True, max_text_chars=20000):
        self.max_features = max_features
        self.min_df = min_df
        self.ngram_range = ngram_range
        self.custom_words = custom_words
        self.stop_words = stop_words
        self.lowercase = lowercase
        self.max_text_chars = max_text_chars

    def _documents(self, X):
        values = np.asarray(X, dtype=object).reshape(-1)
        return ["" if pd.isna(v) else str(v)[:self.max_text_chars] for v in values]

    def fit(self, X, y=None):
        if not isinstance(self.max_text_chars, int) or self.max_text_chars < 1:
            raise ValueError("每筆文字的長度上限必須是正整數。")
        if not isinstance(self.min_df, int) or self.min_df < 1:
            raise ValueError("文字最少出現文件數必須是正整數。")
        if not isinstance(self.max_features, int) or self.max_features < 1:
            raise ValueError("每欄文字特徵上限必須是正整數。")
        if len(self.custom_words) > 500 or len(self.stop_words) > 500:
            raise ValueError("自訂詞與停用詞各最多 500 個。")
        if any(len(str(w)) > 100 for w in (*self.custom_words, *self.stop_words)):
            raise ValueError("單一自訂詞／停用詞最多 100 個字。")
        self.vectorizer_ = TfidfVectorizer(
            tokenizer=WordTokenizer(self.custom_words, self.stop_words, self.lowercase),
            token_pattern=None, lowercase=False, ngram_range=tuple(self.ngram_range),
            min_df=self.min_df, max_features=self.max_features, sublinear_tf=True,
            dtype=np.float64,
        )
        docs = self._documents(X)
        self.empty_reason_ = ""
        if self.min_df > len(docs):
            self.empty_reason_ = "最少出現文件數超過訓練筆數"
        else:
            try:
                self.vectorizer_.fit(docs)
            except ValueError as exc:
                if not any(message in str(exc) for message in ("empty vocabulary", "After pruning, no terms remain")):
                    raise
                self.empty_reason_ = "訓練文字經斷詞、停用詞及低頻篩選後沒有可用詞彙"
        if self.empty_reason_:
            self.vectorizer_ = None
            self.vocabulary_size_ = 0
        else:
            self.vocabulary_size_ = len(self.vectorizer_.vocabulary_)
        return self

    def transform(self, X):
        check_is_fitted(self, "vocabulary_size_")
        docs = self._documents(X)
        if self.vectorizer_ is None:
            # 固定零值佔位欄使空詞彙仍能與其餘表格特徵合併，絕不從新資料 fit。
            return sparse.csr_matrix((len(docs), 1), dtype=np.float64)
        return self.vectorizer_.transform(docs)

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "vocabulary_size_")
        if self.vectorizer_ is None:
            return np.asarray(["__EMPTY_VOCABULARY__"], dtype=object)
        return self.vectorizer_.get_feature_names_out()

    def vocabulary_records(self):
        check_is_fitted(self, "vocabulary_size_")
        if self.vectorizer_ is None:
            return []
        return [{"index": i, "token": token, "idf": float(idf)}
                for i, (token, idf) in enumerate(zip(self.get_feature_names_out(), self.vectorizer_.idf_))]

    def audit(self, X):
        original = ["" if pd.isna(v) else str(v) for v in np.asarray(X, dtype=object).reshape(-1)]
        matrix = self.transform(X)
        return {"text_nonempty_zero_vectors": int(sum(bool(v.strip()) and n == 0
                    for v, n in zip(original, matrix.getnnz(axis=1)))),
                "text_truncated_rows": sum(len(v) > self.max_text_chars for v in original)}


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str
    normalized_value: float
    normalized_unit: str
    dimension: str


# (dimension, canonical unit, factor, offset)。幣別只辨識，不換匯；「元」不猜幣別。
_UNITS = {}


def _add_units(aliases, dimension, canonical, factor=1.0, offset=0.0):
    for alias in aliases:
        _UNITS[normalize_text(alias).lower()] = (dimension, canonical, factor, offset)


_add_units(["mm", "毫米"], "length", "m", 0.001)
_add_units(["cm", "公分", "厘米"], "length", "m", 0.01)
_add_units(["m", "公尺", "米"], "length", "m")
_add_units(["km", "公里", "千米"], "length", "m", 1000)
_add_units(["mg", "毫克"], "mass", "kg", 0.000001)
_add_units(["g", "克", "公克"], "mass", "kg", 0.001)
_add_units(["kg", "公斤", "千克"], "mass", "kg")
_add_units(["ml", "毫升"], "volume", "L", 0.001)
_add_units(["l", "公升", "升"], "volume", "L")
_add_units(["s", "sec", "秒"], "duration", "s")
_add_units(["min", "分鐘", "分钟"], "duration", "s", 60)
_add_units(["h", "hr", "小時", "小时"], "duration", "s", 3600)
_add_units(["%", "百分比"], "ratio", "ratio", 0.01)
_add_units(["‰"], "ratio", "ratio", 0.001)
_add_units(["°c", "℃", "攝氏度", "摄氏度"], "temperature", "°C")
_add_units(["°f", "℉", "華氏度", "华氏度"], "temperature", "°C", 5 / 9, -32 * 5 / 9)
_add_units(["nt$", "twd", "台幣", "新台幣", "新臺幣"], "currency_TWD", "TWD")
_add_units(["us$", "usd", "美元", "美金"], "currency_USD", "USD")
_add_units(["cny", "rmb", "人民幣", "人民币"], "currency_CNY", "CNY")
_add_units(["eur", "€", "歐元", "欧元"], "currency_EUR", "EUR")
_add_units(["jpy", "日圓", "日元"], "currency_JPY", "JPY")
_add_units(["元"], "currency_unspecified", "元")

_NUMBER = r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
_UNIT_PATTERN = "|".join(re.escape(x) for x in sorted(_UNITS, key=len, reverse=True))
_LABEL = r"(?:(?:尺寸|長度|长度|寬度|宽度|高度|重量|容量|價格|价格|金額|金额|溫度|温度|比例|length|width|height|weight|volume|price|temperature)\s*[:：=]?\s*)?"
_SUFFIX_QUANTITY = re.compile(rf"^{_LABEL}(?P<number>{_NUMBER})\s*(?P<unit>{_UNIT_PATTERN})$", re.IGNORECASE)
_CURRENCY_PREFIX = "|".join(re.escape(u) for u, info in _UNITS.items() if info[0].startswith("currency_") and u != "元")
_PREFIX_QUANTITY = re.compile(rf"^{_LABEL}(?P<unit>{_CURRENCY_PREFIX})\s*(?P<number>{_NUMBER})$", re.IGNORECASE)


def parse_quantity(value, normalize_units=True):
    """只接受一個數字與明確支援的單位；不猜範圍、型號、裸 $ 或逗號小數。"""
    if pd.isna(value):
        return None
    text = normalize_text(value).strip()
    match = _SUFFIX_QUANTITY.fullmatch(text) or _PREFIX_QUANTITY.fullmatch(text)
    if match is None:
        return None
    number = float(match.group("number").replace(",", ""))
    unit = match.group("unit")
    dimension, canonical, factor, offset = _UNITS[unit.lower()]
    normalized = number * factor + offset
    if not math.isfinite(number) or not math.isfinite(normalized):
        return None
    if not normalize_units:
        # 關閉換算後，各種寫法／單位各自一欄，不把 cm 的 30 與 m 的 30 當成相同量。
        return Quantity(number, unit, number, unit.lower(), f"{dimension}_{unit.lower()}")
    return Quantity(number, unit, normalized, canonical, dimension)
