# financial-data

抓取美股标的历史分时数据（1min），并计算 RSI(14)、EMA(10/20)、VWAP 指标。

## 安装依赖

```bash
pip3 install -r requirements.txt
```

## 使用

**初始化**（清空旧数据，拉取最近 30 天历史）：

```bash
python3 fetch_data.py --init
python3 fetch_data.py AAPL TSLA --init   # 指定标的
```

**增量更新**（从文件末尾接续到最新）：

```bash
python3 fetch_data.py                    # 默认 SNDK / QQQ / NVDA
python3 fetch_data.py AAPL TSLA          # 指定标的
```

## 数据存储

每个标的持久化到 `./data/<TICKER>.records`，每行一个交易日：

```
2026-02-19: [{"time": "09:30", "open": 124.5, "high": 125.1, "low": 124.2, "close": 124.8, "volume": 38200, "RSI_14": 58.3, "EMA_10": 123.1, "EMA_20": 121.8, "VWAP": 124.4}, ...]
```

## 说明

- 数据源：[yfinance](https://github.com/ranaroussi/yfinance)，1min 数据受 Yahoo Finance API 限制最多回溯 30 天
- 访问频率限制：≤ 5 次/分钟
- 增量更新时，最后一个交易日会自动重新拉取（覆盖可能不完整的数据）
