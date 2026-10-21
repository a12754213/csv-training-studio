"""建立可重現的合成範例，不包含真實個人資料。"""
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    rng = np.random.default_rng(42)
    destination = Path(__file__).resolve().parent / "samples"
    destination.mkdir(exist_ok=True)
    n = 360
    age = rng.integers(18, 72, n).astype(float)
    months = rng.integers(1, 50, n)
    spend = rng.normal(1500, 400, n).clip(100)
    plan = rng.choice(["月繳", "年繳", "季繳"], n, p=[0.5, 0.3, 0.2])
    complaints = rng.poisson(0.5, n)
    logits = -1.7 + 1.4 * (plan == "月繳") + 0.7 * complaints - 0.035 * months + 0.0003 * spend
    churn = rng.random(n) < 1 / (1 + np.exp(-logits))
    frame = pd.DataFrame({"客戶編號": [f"C{i:05d}" for i in range(n)],
                          "年齡": age, "使用月數": months, "月消費": spend.round(2),
                          "方案": plan, "城市": rng.choice(["台北", "台中", "高雄", "台南"], n),
                          "客訴次數": complaints, "註冊日期": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
                          "固定欄位": "示範", "完全空白欄": np.nan,
                          "是否流失": np.where(churn, "是", "否")})
    for col, size in [("年齡", 25), ("月消費", 18), ("方案", 15), ("城市", 10)]:
        frame.loc[rng.choice(n, size, replace=False), col] = np.nan
    frame.loc[[5, 97, 201], "是否流失"] = np.nan
    frame = pd.concat([frame, frame.iloc[:5]], ignore_index=True)
    frame.to_csv(destination / "demo_churn.csv", index=False, encoding="utf-8-sig")
    size = rng.uniform(12, 70, n)
    location = rng.choice(["台北", "台中", "高雄"], n)
    years = rng.integers(0, 45, n)
    prices = size * np.select([location == "台北", location == "台中"], [80, 40], default=30) - years * 8 + rng.normal(0, 160, n)
    housing = pd.DataFrame({"物件編號": [f"H{i:05d}" for i in range(n)], "坪數": size.round(2),
                            "城市": location, "屋齡": years.astype(float),
                            "樓層": rng.integers(1, 20, n), "房價萬元": prices.clip(100).round(1)})
    housing.loc[rng.choice(n, 25, replace=False), "坪數"] = np.nan
    housing.loc[rng.choice(n, 16, replace=False), "屋齡"] = np.nan
    housing.to_csv(destination / "demo_housing.csv", index=False, encoding="utf-8-sig")
    comments = ["包裝完整，安裝簡單，低噪音的設計很滿意。", "Good quality and easy to use. Works with RTX4070.",
                "送貨快速，尺寸剛好，日常使用很方便。", "做工粗糙，使用時聲音太大，不符合期待。",
                "Poor quality. The package arrived damaged.", "說明不清楚，安裝很麻煩，希望改善品質。"]
    picks = rng.integers(0, len(comments), 180)
    recommendation = np.where(picks < 3, "推薦", "不推薦")
    flipped = rng.choice(180, 18, replace=False)
    recommendation[flipped] = np.where(recommendation[flipped] == "推薦", "不推薦", "推薦")
    reviews = pd.DataFrame({"訂單編號": [f"R{i:05d}" for i in range(180)],
                            "型號": rng.choice(["AB123", "RTX4070", "00123"], 180),
                            "商品類別": rng.choice(["風扇", "散熱器", "機殼"], 180),
                            "評論": [comments[i] for i in picks],
                            "尺寸": rng.choice(["30cm", "0.3m", "尺寸40cm", "500mm", "0.6m"], 180),
                            "重量": rng.choice(["500g", "0.5kg", "800公克", "1.2公斤"], 180),
                            "售價": rng.choice(["NT$1,200", "800台幣", "1500TWD", "500元"], 180),
                            "折扣比例": rng.choice(["10%", "15%", "20%", "25%"], 180),
                            "是否推薦": recommendation})
    for col in ["評論", "尺寸", "重量"]:
        reviews.loc[rng.choice(180, 8, replace=False), col] = np.nan
    reviews.to_csv(destination / "demo_reviews.csv", index=False, encoding="utf-8-sig")
    print("Created all three synthetic CSV samples")


if __name__ == "__main__":
    main()
