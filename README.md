# 台股選股策略回測（三條件＋頸線）

網友分享的「MACD 柱狀體翻正＋布林通道開口放大＋站上上揚 20 日線」策略，加上兩個同型的三條件策略，
在台股市值前 100／前 500 的回測；比較「一般版（訊號日收盤成交）」與「買得到版（隔日開盤成交）」，並對照同期 0050。

兩組研究（網頁用分頁切換）：
1. 三條件策略：脆友 MACD＋布林＋月線，與兩個同型策略
2. 頸線策略：W 底、頭肩底、底底高突破前波高；標的含 0050 單一標的、市值前 100／前 500

網頁：見 repo 的 GitHub Pages（`index.html`）。

## 檔案
- `backtest.py`：回測引擎與三條件策略（輸出 `results.json`）
- `neckline.py`：三種頸線策略（輸出 `results_neckline.json`）
- `results.json`、`results_neckline.json`：回測結果（網頁資料來源）
- `template.html`、`build.py`：把結果嵌入網頁，產出 `index.html`

## 重現
價格資料不在此 repo（來源為證交所／櫃買公開行情整理的還原日線）。自備資料後：

    python backtest.py daily.parquet codes.txt results.json
    python neckline.py daily.parquet codes.txt results_neckline.json
    python build.py

## 限制
股票池以「今天」的市值排名選取，有存活者偏差；回測期間為一段多頭；未計滑價；沒有樣本外檢驗。
僅供研究，非投資建議。

MIT License
