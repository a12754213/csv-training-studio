"""啟動：python -m streamlit run app.py"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from version import __version__
from ui_layout import (apply_page_layout, render_page_header,
                       render_hub_directory, HOME_HEADING)
from automl import train_prepared

from preprocessing import (
    DataPreparationError, PrepConfig, _identifier_name, clean_frame, json_text,
    make_training_bundle, numeric_summary, prepare_data, preview_transformations,
    profile_frame, read_csv_bytes, train_baseline,
)

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="AI Agent Hub｜多功能智慧工作台", page_icon="🤖", layout="wide")
apply_page_layout()
render_page_header(
    title=HOME_HEADING,
    category="WORKSPACE",
    description="將資料分析、AutoML 訓練、網頁擷取與文字工具整合在同一個工作區；"
                "從下方挑選模組開始，不必每次都從 CSV 出發。",
)
render_hub_directory()
st.subheader("📊 CSV / AutoML 訓練工作區")
st.caption("這是 Hub 其中一個完整模組：探索 CSV、整理特徵、訓練分類／回歸／時間序列模型，並匯出可重現的成果。")

SAMPLES = {"客戶流失｜分類": ("demo_churn.csv", "是否流失"),
           "房價預測｜回歸": ("demo_housing.csv", "房價萬元"),
           "評論與單位｜混合特徵分類": ("demo_reviews.csv", "是否推薦"),
           "每日銷量｜時間序列": ("demo_timeseries.csv", "銷量")}

with st.sidebar:
    st.header("CSV 訓練資料")
    source = st.radio("資料來源", ["使用示範資料", "上傳我的 CSV"])
    sample = None
    uploaded = None
    if source == "使用示範資料":
        sample = st.selectbox("範例", list(SAMPLES))
        filename = SAMPLES[sample][0]
        payload = (ROOT / "samples" / filename).read_bytes()
        st.caption("合成資料，刻意加入缺值、重複列與識別碼，供練習使用。")
    else:
        uploaded = st.file_uploader("選擇 CSV", type=["csv", "tsv", "txt"])
        if uploaded is None:
            st.info("先上傳 CSV，或切換到示範資料。")
            st.stop()
        filename, payload = uploaded.name, uploaded.getvalue()
    with st.expander("讀檔設定"):
        encoding = st.selectbox("文字編碼", ["auto", "utf-8-sig", "utf-8", "cp950", "big5", "utf-16", "gb18030"])
        sep_label = st.selectbox("分隔符號", ["自動", "逗號 ,", "分號 ;", "Tab", "直線 |"])
        separator = {"自動": "auto", "逗號 ,": ",", "分號 ;": ";", "Tab": "\t", "直線 |": "|"}[sep_label]
        token_text = st.text_input("其他缺值標記（逗號分隔）", value="", placeholder="例如：N/A,NULL,?")
        st.caption("預設只處理空白；NA 可能是真正類別，不會擅自刪除。")
    st.divider()
    st.caption("適合含數值、類別與文字的表格分類／回歸。支援 30 MB、20 萬列、500 個欄位以內的 CSV。")
    st.caption("本地啟動：資料由你的電腦處理。線上使用：上傳內容會送到部署此程式的伺服器處理。兩者都不呼叫 AI 服務。")
    st.caption("請下載要保留的結果；重新整理或伺服器重啟後，工作階段內容可能消失。")
    st.caption(f"AI Agent Hub · 程式版本 v{__version__}")

missing_tokens = tuple(x.strip() for x in token_text.split(",") if x.strip())
try:
    frame, file_info = read_csv_bytes(payload, encoding, separator)
except (DataPreparationError, ValueError) as exc:
    st.error(str(exc)); st.stop()
clean = clean_frame(frame, missing_tokens)
file_digest = hashlib.sha256(payload + repr((encoding, separator, missing_tokens)).encode()).hexdigest()[:16]
st.caption(f"目前檔案：{filename} · 編碼：{file_info['encoding']}")
cards = st.columns(4)
cards[0].metric("資料筆數", f"{len(frame):,}")
cards[1].metric("原始欄位", len(frame.columns))
cards[2].metric("缺值儲存格", f"{int(clean.isna().sum().sum()):,}")
cards[3].metric("完全重複列", int(clean.duplicated().sum()))

training_mode = st.radio("訓練模式", ["一般表格｜分類／回歸", "時間序列｜預測未來數值"],
                         index=1 if sample and "時間序列" in sample else 0, horizontal=True, key=f"mode_{file_digest}")
if os.environ.get("CSV_STUDIO_LOCAL") == "1":
    from chatgpt_panel import render_chatgpt_panel
    render_chatgpt_panel()

tab_overview, tab_prepare, tab_output = st.tabs(["1 · 資料概況", "2 · 整理與切分", "3 · 訓練與下載"])
with tab_overview:
    st.subheader("資料預覽")
    st.dataframe(clean.head(30), width="stretch", hide_index=True)
    st.subheader("每一欄的狀況")
    profile = profile_frame(frame, missing_tokens)
    st.dataframe(profile, width="stretch", hide_index=True)
    st.caption("這裡是全表的探索概況。真正的類型判定、欄位排除、補值與編碼只用訓練集來決定。")
    missing = profile.set_index("欄位")["缺值率 (%)"].sort_values(ascending=False).head(20)
    if (missing > 0).any():
        st.bar_chart(missing[missing > 0], horizontal=True, color="#16816d")
    summary = numeric_summary(frame, missing_tokens)
    if not summary.empty:
        st.subheader("數值分布摘要")
        st.dataframe(summary.round(3), width="stretch", hide_index=True)
        st.caption("IQR 只標記可能的離群值，不直接刪除。這是全表探索統計，不會用於前處理的 fit。")

if training_mode.startswith("時間序列"):
    from forecast_ui import render_forecast_ui
    render_forecast_ui(frame, file_digest, missing_tokens, tab_prepare, tab_output)
    st.stop()

with tab_prepare:
    st.subheader("先告訴我：你要預測什麼？")
    default_target = SAMPLES[sample][1] if sample else None
    options = ["（請選擇目標欄位）"] + list(frame.columns)
    target_index = options.index(default_target) if default_target in options else 0
    left, right = st.columns(2)
    target = left.selectbox("目標欄位 y", options, index=target_index, key=f"target_{file_digest}")
    task_label = right.selectbox("任務類型", ["分類｜預測類別", "回歸｜預測數值"],
                                 index=1 if sample and "回歸" in sample else 0, key=f"task_{file_digest}")
    task = "classification" if task_label.startswith("分類") else "regression"
    model_label = st.selectbox("模型選擇", ["基準模型", "Random Forest", "AutoML｜比較後選擇"], key=f"model_{file_digest}")
    model_choice = {"基準模型": "baseline", "Random Forest": "random_forest", "AutoML｜比較後選擇": "auto"}[model_label]
    if target in frame:
        n_missing = int(clean[target].isna().sum())
        st.caption(f"目標的不同值數：{clean[target].nunique(dropna=True):,} · 缺失目標列：{n_missing:,}（會另外隔離，不補答案）")
    st.subheader("資料怎麼分？")
    split_label = st.radio("切分方式", ["隨機切分", "按群組切分", "按時間切分"], horizontal=True)
    split_mode = {"隨機切分": "random", "按群組切分": "group", "按時間切分": "time"}[split_label]
    split_column = None
    candidates = [c for c in frame if c != target]
    if split_mode == "group":
        st.info("同一客戶、病患、機台有多筆資料時使用，確保同一個群組不會同時出現在訓練與測試集。")
        split_column = st.selectbox("群組欄位（不當作特徵）", candidates, key=f"group_{file_digest}") if candidates else None
    elif split_mode == "time":
        st.info("以較早資料訓練、較晚資料測試。同一時間不會跨集合；仍需自行確認預測跨度與資料重疊。")
        split_column = st.selectbox("時間欄位（不當作特徵）", candidates, key=f"time_{file_digest}") if candidates else None
    else:
        st.caption("分類採分層抽樣，盡量保留類別比例。若同一人有多筆或資料有時間順序，請改用適合的切分。")
    left, right = st.columns(2)
    test_size = left.slider("測試集比例 (%)", 10, 40, 20, step=5) / 100
    seed = int(right.number_input("隨機種子（固定可重現結果）", min_value=0, max_value=2147483647, value=42))
    deduplicate = st.checkbox("切分前移除完全重複列", value=True)

    st.subheader("自動整理，也能手動調整")
    selectable = [c for c in frame if c not in [target, split_column]]
    suggested = [c for c in frame if _identifier_name(c)]
    excluded_columns = st.multiselect(
        "不參與訓練的欄位", selectable,
        default=[c for c in suggested if c in selectable],
        key=f"exclude_{file_digest}_{target}_{split_column}",
        help="編號、姓名、流水號或預測時還不知道的欄位可在這裡排除。原始資料仍保留於下載包。")
    remaining = [c for c in selectable if c not in excluded_columns]
    st.caption(f"已排除 {len(excluded_columns)} 欄；剩餘 {len(remaining)} 個候選特徵。目標與切分欄會自動排除。")
    role_labels = {"自動判斷": "auto", "數值": "numeric", "類別": "categorical", "日期": "datetime",
                   "文字斷詞 + TF-IDF": "text", "數字 + 單位": "quantity", "排除": "ignore"}
    role_columns = remaining
    kind_labels = {v: k for k, v in role_labels.items()}
    kind_labels.update({"identifier": "疑似識別碼，排除", "empty": "空欄，排除"})
    guessed = profile.set_index("欄位")["推測類型"].to_dict()
    role_table = pd.DataFrame({"欄位": role_columns,
                               "全表格式建議": [kind_labels[guessed[c]] for c in role_columns],
                               "處理方式": ["自動判斷"] * len(role_columns)})
    edited = st.data_editor(role_table, hide_index=True, width="stretch", disabled=["欄位", "全表格式建議"],
                            column_config={"處理方式": st.column_config.SelectboxColumn(
                                "處理方式", options=list(role_labels), required=True)},
                            key=f"roles_{file_digest}_{target}_{split_column}_{tuple(excluded_columns)}")
    st.caption("評論／描述可轉文字特徵；明確的單一數量可拆數字與單位。ID 自動排除；型號與前導零代碼保留完整類別。自動判定最終以訓練集為準，可在此手動指定。")
    st.caption("請自行排除預測時還不知道的資訊，例如以評論預測推薦時，必須確定預測當下已經有評論。")
    with st.expander("補值與編碼設定", expanded=False):
        l, r = st.columns(2)
        num_label = l.selectbox("數值缺值", ["中位數（預設）", "平均數", "固定 0"])
        cat_label = r.selectbox("類別缺值", ["眾數（預設）", "獨立缺失類別"])
        scale = st.checkbox("數值標準化", value=True)
        indicator = st.checkbox("加上數值與文字缺值指示欄", value=True)
        max_categories = int(st.number_input("每欄最多保留的 One-Hot 類別數（含低頻合併類）", 2, 200, 50))
        min_frequency = int(st.number_input("低於這個出現次數的類別合併", 1, 100, 2))
        threshold = st.slider("訓練集缺值率高於多少 % 就排除", 50, 100, 95, step=5) / 100
        drop_constant = st.checkbox("排除訓練集常數欄", value=True)
        st.caption("日期展開成年、月、日、星期、小時；離群值會保留。")
    with st.expander("文字斷詞與 TF-IDF 設定", expanded=False):
        st.write("中文用 jieba 斷詞；英文按單詞切分，RTX4070 等連續代碼保持完整。每個文字欄各自建立 TF-IDF 特徵。")
        l, r = st.columns(2)
        text_max_features = int(l.number_input("每個文字欄最多特徵數", 100, 20000, 5000, step=100))
        text_min_df = int(r.number_input("詞彙至少出現在幾筆訓練文字", 1, 100, 1))
        ngram_label = st.selectbox("文字特徵", ["單詞 + 相鄰雙詞", "僅單詞"])
        text_lowercase = st.checkbox("英文統一小寫（只影響文字欄）", value=True)
        max_text_chars = int(st.number_input("每筆文字最多處理字數", 100, 100000, 20000, step=100))
        l, r = st.columns(2)
        custom_text = l.text_area("自訂詞（每行一個）", placeholder="低噪音\n台積電", max_chars=20000)
        stop_text = r.text_area("停用詞（每行一個）", placeholder="例如要忽略的語助詞", max_chars=20000)
        st.caption("專有名詞或繁體中文切分不理想時可加自訂詞；預設不刪停用詞，以保留「不」等否定語意。各最多 500 詞。詞彙與 IDF 只用訓練集建立。")
    with st.expander("數字與單位設定", expanded=False):
        normalize_units = st.checkbox("將相容量值換成共同單位", value=True)
        st.write("例如 30cm → 0.3m、500g → 0.5kg、50% → 0.5。關閉換算時，不同單位各用不同數值欄。")
        st.caption("不同量綱與幣別分開；不換匯，也不把「元」猜成某種幣別。支援 NT$1,200 等明確格式；30×40cm、10–20cm、裸 $ 和型號不會自動拆分。")
        st.caption("量值缺失／解析失敗用 0 加指示欄表示；不把不同單位混在一起取平均。")
    custom_words = tuple(w.strip() for w in custom_text.splitlines() if w.strip())
    stop_words = tuple(w.strip() for w in stop_text.splitlines() if w.strip())
    if max(len(custom_words), len(stop_words)) > 500 or any(len(w) > 100 for w in (*custom_words, *stop_words)):
        st.error("自訂詞／停用詞各最多 500 個，每個最多 100 字。"); st.stop()
    roles = {row["欄位"]: role_labels[row["處理方式"]] for _, row in edited.iterrows()}
    prep_args = {"column_roles": roles, "missing_tokens": missing_tokens,
                 "numeric_strategy": {"中位數（預設）": "median", "平均數": "mean", "固定 0": "constant"}[num_label],
                 "categorical_strategy": "most_frequent" if cat_label.startswith("眾數") else "constant",
                 "scale_numeric": scale, "missing_indicators": indicator,
                 "max_categories": max_categories, "min_frequency": min_frequency,
                 "drop_missing_above": threshold, "drop_constant": drop_constant,
                 "text_max_features": text_max_features, "text_min_df": text_min_df,
                 "text_ngram_range": (1, 2) if ngram_label.startswith("單詞 +") else (1, 1),
                 "custom_words": custom_words, "stop_words": stop_words, "text_lowercase": text_lowercase,
                 "max_text_chars": max_text_chars, "normalize_units": normalize_units}
    if role_columns:
        st.subheader("先看看會怎麼處理")
        preferred = next((c for c in role_columns if guessed[c] in {"text", "quantity"}), role_columns[0])
        preview_col = st.selectbox("預覽欄位", role_columns, index=role_columns.index(preferred),
                                    key=f"preview_{file_digest}_{target}_{split_column}")
        st.dataframe(preview_transformations(frame, roles, missing_tokens, normalize_units,
                     custom_words, stop_words, text_lowercase, max_text_chars, columns=[preview_col]),
                     width="stretch", hide_index=True)
        st.caption("此處只預覽解析方式，尚未補值或建立 TF-IDF。設定變更後需要重新整理。")
    config = PrepConfig(target, task, test_size, seed, split_mode, split_column, deduplicate, prep_args,
                        tuple(excluded_columns), model_choice)
    signature = hashlib.sha256((file_digest + repr(config)).encode()).hexdigest()
    if st.session_state.get("result_signature") != signature:
        for key in ("prepared", "trained", "download_bytes"):
            st.session_state.pop(key, None)
    if st.button("整理成訓練資料", type="primary", disabled=target not in frame):
        try:
            with st.spinner("切分資料，再只用訓練集建立補值與編碼規則…"):
                prepared = prepare_data(frame, config)
                st.session_state["prepared"] = prepared
                st.session_state["result_signature"] = signature
                st.session_state.pop("trained", None)
                st.session_state.pop("download_bytes", None)
            st.success("整理完成，請切換到「3 · 訓練與下載」。")
        except (DataPreparationError, ValueError, OverflowError) as exc:
            st.error(str(exc))

with tab_output:
    prepared = st.session_state.get("prepared")
    if prepared is None:
        st.info("先到「2 · 整理與切分」選擇目標並按下整理按鈕。修改設定後也需要重新整理。")
    else:
        st.subheader("資料已就緒")
        a, b, c = st.columns(3)
        a.metric("訓練資料", f"{prepared.X_train.shape[0]:,} 筆")
        b.metric("測試資料", f"{prepared.X_test.shape[0]:,} 筆")
        c.metric("輸出特徵", f"{prepared.X_train.shape[1]:,} 欄")
        st.write("實際採用的原始特徵：", "、".join(prepared.report["used_feature_columns"]))
        st.caption("手動排除：" + ("、".join(prepared.report["excluded_columns"]) or "無"))
        for note in prepared.report["notes"]:
            st.caption("• " + note)
        st.write("處理後的特徵預覽（前 8 筆、最多 20 欄）")
        names = prepared.preprocessor.get_feature_names_out()
        st.dataframe(pd.DataFrame(prepared.X_train[:8, :20].toarray(), columns=names[:20]),
                     width="stretch", hide_index=True)
        with st.expander("實際採用的文字／單位處理與詞彙"):
            preview = prepared.preprocessor.preview(prepared.raw_train)
            st.dataframe(preview[preview["類型"].isin(["text", "quantity"])], width="stretch", hide_index=True)
            st.json({k: v for k, v in prepared.report["learned_from_training_only"].items()
                     if k in {"text_columns", "quantity_columns"}})
        with st.expander("欄位取捨與測試集檢查"):
            st.dataframe(pd.DataFrame(prepared.report["column_decisions"]), width="stretch", hide_index=True)
            st.dataframe(pd.DataFrame(prepared.report["test_audit"]), width="stretch", hide_index=True)
            st.caption("invalid_converted_to_missing：數值／日期／單位解析失敗；unknown_categories：新類別；unseen_quantity_dimensions：新量綱。text_nonempty_zero_vectors：非空但沒有詞彙命中的文字；text_truncated_rows：超過字數上限。")
            st.json(prepared.report["learned_from_training_only"])
        st.divider()
        st.subheader("訓練與評估")
        st.caption("基準模型為 Logistic Regression／Ridge，也可選 Random Forest。AutoML 只用訓練集內的驗證資料比較，再訓練選中的模型；測試集最後才評估。")
        if st.button("訓練並查看測試結果", type="secondary"):
            try:
                with st.spinner("訓練模型並評估一次保留的測試集…"):
                    st.session_state["trained"] = train_prepared(prepared)
                    st.session_state.pop("download_bytes", None)
            except (DataPreparationError, ValueError, OverflowError) as exc:
                st.error(str(exc))
        trained = st.session_state.get("trained")
        if trained is not None:
            _, metrics, predictions = trained
            if "model_comparison" in metrics:
                st.write("驗證集模型比較（不使用測試分數選模型）")
                st.dataframe(pd.json_normalize(metrics["model_comparison"]), hide_index=True, width="stretch")
            st.caption("這次模型：" + metrics["model"])
            scores = pd.DataFrame({"基準模型": metrics["test_scores"], "Dummy 對照": metrics["dummy_scores"]})
            st.dataframe(scores, width="stretch")
            st.caption("Accuracy／balanced accuracy／macro-F1 越高越好；MAE／RMSE 越低越好，R² 越高越好。")
            if "confusion_matrix" in metrics:
                labels = metrics["classes"]
                st.write("混淆矩陣：列＝真實類別、欄＝預測類別")
                st.dataframe(pd.DataFrame(metrics["confusion_matrix"], index=labels, columns=labels), width="stretch")
                with st.expander("各類別 Precision／Recall／F1"):
                    st.json(metrics["classification_report"])
            for message in metrics["warnings"]:
                st.warning(message)
        st.divider()
        st.subheader("下載，接著訓練或預測")
        st.write("包含 X／y、原始切分資料、處理規則、斷詞與單位預覽、詞彙及 IDF、品質報告與 train.py／predict.py。若剛才已訓練，也會包含模型。")
        if st.button("產生可下載資料包"):
            with st.spinner("打包資料與程式…"):
                st.session_state["download_bytes"] = make_training_bundle(prepared, trained)
        if "download_bytes" in st.session_state:
            st.download_button("下載 training_data.zip", st.session_state["download_bytes"],
                                file_name="training_data.zip", mime="application/zip", type="primary")
        st.caption("大型特徵矩陣以 NPZ 儲存；小型資料另外附 CSV。分類標籤保留原始文字，scikit-learn 可直接使用。")
