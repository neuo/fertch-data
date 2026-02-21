# financial-data

抓取美股标的历史分时数据（1min），计算技术指标，并提供可视化 Web 界面。

## 安装依赖

```bash
# Python 依赖（数据抓取 + API 后端）
pip3 install -r requirements.txt

# 前端依赖
cd frontend && npm install
```

## 启动

**后端 API（终端 1）：**

```bash
uvicorn backend.api:app --reload --port 8000
```

**前端开发服务器（终端 2）：**

```bash
cd frontend && npm run dev
```

访问 http://localhost:5173

## 数据抓取

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

也可以在 Web 界面点击右上角 **Update** 按钮触发增量更新。

## 功能

- 选择标的 / 时间范围（1D / 3D / 1W / 2W / 1M）
- K 线图叠加 EMA10（蓝）、EMA20（橙）、VWAP（紫虚线）
- 下方 RSI(14) 子图，带 30/70 参考线
- 点击 Update 触发后台增量拉取并自动刷新

## 数据存储

每个标的持久化到 `./data/<TICKER>.records`，每行一个交易日：

```
2026-02-19: [{"time": "09:30", "open": 124.5, "high": 125.1, "low": 124.2, "close": 124.8, "volume": 38200, "RSI_14": 58.3, "EMA_10": 123.1, "EMA_20": 121.8, "VWAP": 124.4}, ...]
```

## 说明

- 数据源：[yfinance](https://github.com/ranaroussi/yfinance)，1min 数据受 Yahoo Finance API 限制最多回溯 30 天
- 访问频率限制：≤ 5 次/分钟
- 增量更新时，最后一个交易日会自动重新拉取（覆盖可能不完整的数据）
