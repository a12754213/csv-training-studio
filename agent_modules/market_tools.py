"""TWSE daily prices and descriptive analysis; fixed provider, no arbitrary URLs."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib import request, error, parse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from agent_hub import AgentContext, AgentRegistry, Capability

ENDPOINT = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
SOURCE_PAGE = "https://www.twse.com.tw/zh/trading/historical/stock-day.html"


class MarketError(ValueError):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MarketError("證交所資料服務轉址，已停止；請稍後重試。")


def resolve_symbol(instruction: str) -> str | None:
    """Only resolve explicit TWSE identifiers; never infer US ADR from TSMC."""
    if re.search(r"\bTSM\b|ADR|美股|美國", instruction, re.I):
        return None
    named = any(x in instruction.lower() for x in ("台積電", "臺積電", "tsmc"))
    symbols = re.findall(r"(?<![\d.])([0-9]{4,6})(?:\.TW)?(?![\d.]|年|月|日|元|點|%)", instruction, re.I)
    symbols = list(dict.fromkeys(symbols))
    if named:
        return "2330" if not symbols or symbols == ["2330"] else None
    if len(symbols) == 1:
        return symbols[0]
    return None


def parse_month(doc: dict, month: str, *, today=None) -> tuple[list[dict], int]:
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        raise MarketError("此月份無可用成交資料，可能非上市股票、尚未更新或服務受限。")
    fields = doc.get("fields", [])
    required = {"日期": "Date", "開盤價": "Open", "最高價": "High",
                "最低價": "Low", "收盤價": "Close", "成交股數": "Volume"}
    if not isinstance(fields, list) or not all(k in fields for k in required):
        raise MarketError("證交所欄位格式已變更。")
    rows, skipped = [], 0
    limit = today or datetime.now(ZoneInfo("Asia/Taipei")).date()
    raw = doc.get("data")
    if not isinstance(raw, list) or len(raw) > 40:
        raise MarketError("證交所資料格式不正確。")
    for values in raw:
        try:
            if not isinstance(values, list):
                raise ValueError
            y, m, d = map(int, values[fields.index("日期")].split("/"))
            date = datetime(y + 1911 if y < 1911 else y, m, d).date()
            if date.strftime("%Y%m") != month[:6] or date > limit:
                raise ValueError
            row = {"Date": date.isoformat()}
            for field, name in required.items():
                if name != "Date":
                    row[name] = float(str(values[fields.index(field)]).replace(",", ""))
            nums = [row[k] for k in ("Open", "High", "Low", "Close", "Volume")]
            if not all(np.isfinite(nums)) or min(nums[:4]) <= 0 or row["Volume"] < 0:
                raise ValueError
            if row["Low"] > min(row["Open"], row["Close"]) or row["High"] < max(row["Open"], row["Close"]):
                raise ValueError
            rows.append(row)
        except (ValueError, TypeError, IndexError, AttributeError):
            skipped += 1
    return rows, skipped


def fetch_prices(context: AgentContext, params: dict) -> dict:
    if set(params) - {"symbol", "months"}:
        raise MarketError("股價工具只接受 symbol 與 months。")
    symbol, months = params.get("symbol", "2330"), params.get("months", 6)
    if not isinstance(symbol, str) or not re.fullmatch(r"\d{4,6}", symbol):
        raise MarketError("目前支援證交所上市股票／ETF 代碼，例如 2330；不含上櫃與美股。")
    if type(months) is not int or not 3 <= months <= 12:
        raise MarketError("查詢範圍為最近 3～12 個月份。")
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    rows, sources, failures, skipped = [], [], [], 0
    opener = request.build_opener(NoRedirect())
    for offset in reversed(range(months)):
        ym = today.year * 12 + today.month - 1 - offset
        month = f"{ym // 12:04d}{ym % 12 + 1:02d}01"
        url = ENDPOINT + "?" + parse.urlencode({"date": month, "stockNo": symbol, "response": "json"})
        req = request.Request(url, headers={"Accept": "application/json", "User-Agent": "AIAgentHub/3.2"})
        try:
            with opener.open(req, timeout=10) as response:
                raw = response.read(500_001)
            if len(raw) > 500_000:
                raise MarketError("資料超過大小限制。")
            parsed, dropped = parse_month(json.loads(raw), month, today=today)
            if not parsed:
                raise MarketError("本月沒有有效成交列。")
            rows.extend(parsed)
            skipped += dropped
            sources.append({"url": url, "month": month[:6], "rows": len(parsed)})
        except (OSError, TimeoutError, ValueError, error.URLError):
            failures.append(month[:6])
        if offset:
            time.sleep(0.35)
    if not rows:
        raise MarketError("證交所資料暫時無法取得。請稍後重試，或到 CSV 訓練上傳你已有的股價資料。")
    frame = pd.DataFrame(rows).sort_values("Date").drop_duplicates("Date")
    warnings = ["證交所未還原日成交價；除權息／分割會影響報酬與回測。不是即時報價。"]
    if failures:
        warnings.append("未取得月份：" + "、".join(failures) + "；不以不完整月份資料進行模型回測。")
    if skipped:
        warnings.append(f"排除 {skipped} 筆無效成交資料；暫不進行模型回測。")
    asof = frame.iloc[-1]["Date"]
    if (today - datetime.fromisoformat(asof).date()).days > 7:
        warnings.append("最新資料距今超過 7 個日曆日；可能停牌、長假或資料未更新。")
    return {"symbol": symbol, "currency": "TWD", "provider": "TWSE", "adjusted": False,
            "as_of": asof, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "rows": frame.to_dict(orient="records"), "sources": sources,
            "missing_months": failures, "invalid_rows": skipped, "warnings": warnings,
            "status": "partial" if failures or skipped else "completed"}


def analyze_prices(prices: dict) -> dict:
    frame = pd.DataFrame(prices["rows"]).sort_values("Date")
    if len(frame) < 21:
        raise MarketError("至少需要 21 筆有效日成交資料才能分析趨勢。")
    close = frame["Close"].astype(float)
    for n in (5, 20, 60):
        frame[f"MA{n}"] = close.rolling(n).mean()
    returns = close.pct_change()
    latest = float(close.iloc[-1])
    ma20 = float(frame["MA20"].iloc[-1])
    ma60 = float(frame["MA60"].iloc[-1]) if len(frame) >= 60 else None
    trend = "短中期訊號不一致"
    if ma60 is not None:
        if latest > ma20 > ma60:
            trend = "目前收盤價與均線呈多頭排列"
        elif latest < ma20 < ma60:
            trend = "目前收盤價與均線呈空頭排列"
    else:
        trend = "資料不足 60 筆，僅提供短期均線"
    stats = {"latest_close": latest, "change_1d_pct": float(returns.iloc[-1] * 100),
             "change_20_sessions_pct": float((latest / close.iloc[-21] - 1) * 100),
             "volatility_annualized_pct": float(returns.std(ddof=1) * np.sqrt(252) * 100),
             "max_drawdown_pct": float((close / close.cummax() - 1).min() * 100),
             "ma20": ma20, "ma60": ma60, "trend": trend}
    return {"statistics": stats, "chart": json.loads(frame.to_json(orient="records")),
            "interpretation": f"{trend}。這描述已發生的價格結構，無法保證未來漲跌。",
            "method": "20 個成交觀測值的價格變動；年化波動採 252 日假設；最大回撤限本次資料期間。"}


def backtest_prices(prices: dict, horizon: int = 5):
    """Reuse time-isolated AutoML; return artifact only on explicit training action."""
    if prices.get("missing_months") or prices.get("invalid_rows"):
        raise MarketError("月份或成交列不完整，請重新取得完整資料再回測。")
    if type(horizon) is not int or horizon not in (1, 5, 20):
        raise MarketError("預測跨度可選 1、5、20 筆成交資料。")
    from forecasting import ForecastConfig, prepare_forecast, train_forecast, make_forecast_bundle
    frame = pd.DataFrame(prices["rows"])
    if len(frame) < 100:
        raise MarketError("回測至少需要 100 筆成交資料；請增加歷史月份。")
    cfg = ForecastConfig(target="Close", time_column="Date", lookback=20, horizon=horizon,
                         model="auto", feature_columns=("Open", "High", "Low", "Volume"))
    prepared = prepare_forecast(frame, cfg)
    trained = train_forecast(prepared)
    model, metrics, predictions = trained
    future = model.forecast(frame)
    metrics["direction_accuracy"] = float(np.mean(
        np.sign(predictions["prediction"] - predictions["naive_prediction"]) ==
        np.sign(predictions["actual"] - predictions["naive_prediction"])))
    return {"metrics": metrics, "future": future,
            "predictions": predictions.to_dict(orient="records"),
            "split": prepared.report["rows"],
            "note": "模型以訓練期擬合，按時間保留測試集；比較 Ridge／Random Forest 與 Naive。"
                    "未還原價格回測不等於投資報酬，未計成本；不預測確切交易日期。"}, make_forecast_bundle(prepared, trained)


def register(registry: AgentRegistry) -> None:
    registry.register(Capability("market.twse", "取得證交所上市股票日成交資料", fetch_prices,
                                 requires_approval=True))
