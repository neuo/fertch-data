#!/usr/bin/env python3
"""日内超短交易质量评分系统"""
'''
## 7. 项目要求（数据分析-交易评分）
我需要根据 data 中的数据标的交易数据进行数据分析(新的Python脚本)。
数据说明
- 数据有两类，1 是标的的分时数据，由 Python 抓取而来，每个文件名是“标的.records"；2 是交易记录，是最近的交易记录，文件名是 transaction.csv
- 交易记录有些标的的历史记录尚没有抓取（文件不存在），可以忽略这些交易记录

这个数据分析的主要目的是 **日内超短交易质量评分系统**，目标：判断这笔交易 值不值得做
- 系统核心理念：复盘的本质不是看盈亏，而是看 —— 这笔交易在“当时”是否具有正期望结构？（结构正确性，入场质量， 出场质量，风控纪律，情绪痕迹）
- 为了方便你后续进行程序化（Python/量化平台），我们需要将感性的复盘转化为**确定性的逻辑开关**。

以下是将超短复盘模型拆解为**量化规则**的框架
## 核心算法逻辑：正期望结构判定

### 一、 结构正确性 (Structure Alignment) - 30分

*判定目标：你在这一分钟买入时，市场是否处于“多头共振”状态？*

| 维度 | 量化规则 (多头示例，空头反向) | 判定逻辑 (程序化条件) | 分值 |
| --- | --- | --- | --- |
| **S1: 趋势共振** | 价格与均线位置 |  且  (均线扣称向上) | 10 |
| **S2: 相对强度** | 个股 vs 指数 |  (进场前30分钟超额收益) | 10 |
| **S3: 波动收敛** | 突破前的震荡幅度 |  (代表处于爆发前夜而非乱战) | 10 |

---

### 二、 入场质量 (Entry Efficiency) - 25分

*判定目标：你买在了“起爆点”还是“鱼尾巴”？*

| 维度 | 量化规则 | 判定逻辑 (程序化条件) | 分值 |
| --- | --- | --- | --- |
| **E1: 量能触发** | 相对倍量 () |  | 10 |
| **E2: 价格偏离** | 追高系数 |  < 0.7 | 10 |
| **E3: 静态位置** | 乖离率 (Bias) |  (防止买在短线力竭点) | 5 |

---

### 三、 出场质量 (Exit Efficiency) - 20分

*判定目标：你是“恐慌下车”还是“利润最大化”？*

| 维度 | 量化规则 | 判定逻辑 (程序化条件) | 分值 |
| --- | --- | --- | --- |
| **X1: 利润留存比** |  转化率 |  | 10 |
| **X2: 反转卖出** | 趋势破位卖出 | 价格跌破  或  分钟低点后 2 根 K 线内成交 | 10 |
| **X3: 盲目持有** | 时间成本 | 买入后  分钟内价格未脱离成本区 (横盘) 是否果断离场 | 5 |

---

### 四、 风控纪律 (Risk Control) - 15分

*判定目标：执行是否违背了“生存法则”？*

| 维度 | 量化规则 | 判定逻辑 (程序化条件) | 分值 |
| --- | --- | --- | --- |
| **R1: 硬止损执行** | 最大回撤控制 | 实际亏损  预设止损位 (如 -3%) | 10 |
| **R2: 仓位一致性** | 风险敞口 | 实际买入金额与账户总额比例是否符合模型预设 | 5 |

---

### 五、 情绪痕迹 (Sentiment Trace) - 10分

*判定目标：量化分时图上的“急躁”与“贪婪”。*

| 维度 | 量化规则 | 判定逻辑 (程序化条件) | 分值 |
| --- | --- | --- | --- |
| **T1: 抢跑/滞后** | 信号一致性 |  (时间差 > 3分钟扣分) | 5 |
| **T2: 报复性交易** | 交易频率限制 | 该笔交易与上一笔亏损交易的时间间隔是否 < 15 分钟 | 5 |

---

## 复盘输出结果 (Markdown 格式示例)

程序运行后，每笔交易应生成如下摘要：

### **复盘报告：[代码.SH/SZ] - 2026-XX-XX**

> **综合评分：82/100 (等级：优秀执行)**

* **[结构] 30/30:** 完美共振。个股强于大盘 2%，VWAP 趋势向上。
* **[入场] 15/25:** 扣分项。买入时已偏离均线 3.2%，存在追高嫌疑，RV 倍量不明显。
* **[出场] 18/20:** 优。在高位放量滞涨后的第二分钟离场，抓住了 85% 的波动。
* **[风控] 15/15:** 止损位设置合理且未触碰。
* **[情绪] 4/10:** 扣分项。买入信号触发后延迟了 5 分钟才下单，存在心理犹豫。
'''


import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path("./data")
TRANSACTION_FILE = DATA_DIR / "transaction.csv"

# ── 评分阈值配置 ──────────────────────────────────────────────
STOP_LOSS_PCT       = 0.03   # R1 硬止损线
ACCOUNT_TOTAL       = 100_000  # R2 账户总额假设 (USD)
POSITION_PCT_TARGET = 0.10   # R2 目标仓位比例
REL_VOL_HIGH        = 1.5    # E1 相对倍量高阈值
REL_VOL_LOW         = 1.2    # E1 相对倍量低阈值
CHASE_MAX           = 0.70   # E2 追高系数上限（良好）
CHASE_WARN          = 0.85   # E2 追高系数上限（警告）
BIAS_GOOD           = 0.03   # E3 乖离率良好上限
BIAS_WARN           = 0.05   # E3 乖离率警告上限
RS_OUTPERFORM       = 0.01   # S2 超额收益阈值
VOL_CONV_GOOD       = 0.015  # S3 收敛阈值（好）
VOL_CONV_WARN       = 0.025  # S3 收敛阈值（一般）
CAPTURE_GOOD        = 0.60   # X1 利润留存良好阈值
CAPTURE_WARN        = 0.30   # X1 利润留存警告阈值
POST_MISS_GOOD      = 0.005  # X2 出场后错过收益良好阈值
POST_MISS_WARN      = 0.015  # X2 出场后错过收益警告阈值
STAGNATION_BARS     = 5      # X3 判定横盘的连续K线数
STAGNATION_PCT      = 0.003  # X3 横盘判定价格容差
REVENGE_MIN         = 15     # T2 报复性交易最小间隔（分钟）
LAG_GOOD_MIN        = 3      # T1 下单到成交最大延迟（分钟）
LAG_WARN_MIN        = 5


@dataclass
class Bar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    ema10: Optional[float]
    ema20: Optional[float]


@dataclass
class Trade:
    ticker: str
    date: str
    direction: str          # "long" / "short"
    entry_time: str         # HH:MM
    entry_price: float
    entry_order_time: str   # 下单时间 HH:MM
    exit_time: str
    exit_price: float
    quantity: int

    @property
    def sign(self) -> int:
        return 1 if self.direction == "long" else -1

    @property
    def pnl_pct(self) -> float:
        return self.sign * (self.exit_price - self.entry_price) / self.entry_price

    @property
    def pnl_usd(self) -> float:
        return self.sign * (self.exit_price - self.entry_price) * self.quantity


@dataclass
class Score:
    s1: int = 0; s2: int = 0; s3: int = 0
    e1: int = 0; e2: int = 0; e3: int = 0
    x1: int = 0; x2: int = 0; x3: int = 0
    r1: int = 0; r2: int = 0
    t1: int = 0; t2: int = 0
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def structure(self) -> int: return self.s1 + self.s2 + self.s3
    @property
    def entry(self) -> int:     return self.e1 + self.e2 + self.e3
    @property
    def exit(self) -> int:      return self.x1 + self.x2 + self.x3
    @property
    def risk(self) -> int:      return self.r1 + self.r2
    @property
    def sentiment(self) -> int: return self.t1 + self.t2
    @property
    def total(self) -> int:
        return self.structure + self.entry + self.exit + self.risk + self.sentiment

    def grade(self) -> str:
        t = self.total
        if t >= 85: return "优秀执行 🌟"
        if t >= 70: return "良好执行 ✅"
        if t >= 55: return "中等执行 ⚠️"
        if t >= 40: return "需要改进 ❌"
        return "严重问题 🚨"


# ── 数据加载 ──────────────────────────────────────────────────

def load_records(ticker: str) -> dict[str, list[Bar]]:
    fp = DATA_DIR / f"{ticker}.records"
    if not fp.exists():
        return {}
    result: dict[str, list[Bar]] = {}
    with open(fp) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sep = line.index(": ")
            date = line[:sep]
            result[date] = [
                Bar(
                    time=b["time"], open=b["open"], high=b["high"],
                    low=b["low"], close=b["close"], volume=b["volume"],
                    ema10=b.get("EMA_10"), ema20=b.get("EMA_20"),
                )
                for b in json.loads(line[sep + 2:])
            ]
    return result


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s.split(" (")[0].strip(), "%Y/%m/%d %H:%M:%S")


def parse_filled(s: str) -> tuple[int, float]:
    """'20@577.99' → (20, 577.99)"""
    qty_str, price_str = s.split("@")
    return int(qty_str), float(price_str.replace(",", ""))


def load_orders() -> list[dict]:
    """读取所有美股已成交主订单（过滤空行、撤单、失败）"""
    rows = []
    with open(TRANSACTION_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row["方向"] or row["市场"] != "美股":
                continue
            if row["交易状态"] not in ("全部成交",):
                continue
            if not row["已成交@均价"] or "@" not in row["已成交@均价"]:
                continue
            rows.append(row)
    return rows


# ── 配对成完整交易 ────────────────────────────────────────────

def pair_trades(orders: list[dict]) -> list[Trade]:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for o in orders:
        by_ticker[o["代码"]].append(o)

    trades: list[Trade] = []
    for ticker, ticker_orders in by_ticker.items():
        ticker_orders.sort(key=lambda x: parse_dt(x["成交时间"]))
        position = 0
        entry: Optional[dict] = None

        for o in ticker_orders:
            qty, price = parse_filled(o["已成交@均价"])
            fill_dt = parse_dt(o["成交时间"])
            order_dt = parse_dt(o["下单时间"])
            direction = o["方向"]

            if direction == "买入" and position == 0:
                position, entry = qty, o
            elif direction == "卖空" and position == 0:
                position, entry = -qty, o
            elif direction == "卖出" and position > 0 and entry:
                e_qty, e_price = parse_filled(entry["已成交@均价"])
                e_dt = parse_dt(entry["成交时间"])
                trades.append(Trade(
                    ticker=ticker, date=e_dt.strftime("%Y-%m-%d"),
                    direction="long",
                    entry_time=e_dt.strftime("%H:%M"), entry_price=e_price,
                    entry_order_time=parse_dt(entry["下单时间"]).strftime("%H:%M"),
                    exit_time=fill_dt.strftime("%H:%M"), exit_price=price,
                    quantity=min(qty, e_qty),
                ))
                position, entry = 0, None
            elif direction == "买入" and position < 0 and entry:
                e_qty, e_price = parse_filled(entry["已成交@均价"])
                e_dt = parse_dt(entry["成交时间"])
                trades.append(Trade(
                    ticker=ticker, date=e_dt.strftime("%Y-%m-%d"),
                    direction="short",
                    entry_time=e_dt.strftime("%H:%M"), entry_price=e_price,
                    entry_order_time=parse_dt(entry["下单时间"]).strftime("%H:%M"),
                    exit_time=fill_dt.strftime("%H:%M"), exit_price=price,
                    quantity=min(qty, abs(position)),
                ))
                position, entry = 0, None

    return sorted(trades, key=lambda t: (t.date, t.entry_time))


# ── 辅助 ─────────────────────────────────────────────────────

def bar_at(bars: list[Bar], time_str: str) -> int:
    """返回时间 >= time_str 的第一个 bar 的索引"""
    for i, b in enumerate(bars):
        if b.time >= time_str:
            return i
    return len(bars) - 1


def time_diff_min(t1: str, t2: str) -> float:
    """两个 HH:MM 字符串之差（分钟，正数表示 t2 在 t1 之后）"""
    base = datetime(2000, 1, 1)
    dt1 = datetime.strptime(t1, "%H:%M").replace(year=2000, month=1, day=1)
    dt2 = datetime.strptime(t2, "%H:%M").replace(year=2000, month=1, day=1)
    _ = base  # unused but keeps base for clarity
    return (dt2 - dt1).total_seconds() / 60


# ── 评分引擎 ──────────────────────────────────────────────────

def score_trade(
    trade: Trade,
    records: dict[str, list[Bar]],
    qqq: dict[str, list[Bar]],
    prev_loss: Optional[Trade],
) -> Score:
    sc = Score()
    day = records.get(trade.date, [])
    if not day:
        sc.notes["error"] = f"无 {trade.date} 的分时数据（可能为盘前/盘后交易）"
        return sc

    ei = bar_at(day, trade.entry_time)
    xi = bar_at(day, trade.exit_time)
    cross_day = xi < ei   # 出场在次日盘前，exit_time 早于当日首根K线
    if cross_day:
        xi = len(day) - 1  # 用当日最后一根做出场估算
    eb = day[ei]
    sign = trade.sign

    # ── S1：趋势共振 (10分) ───────────────────────────────────
    if eb.ema10 is not None and eb.ema20 is not None:
        if sign == 1:
            cond = [eb.close > eb.ema10, eb.ema10 > eb.ema20]
        else:
            cond = [eb.close < eb.ema10, eb.ema10 < eb.ema20]
        met = sum(cond)
        sc.s1 = [0, 5, 10][met]
        labels = ["价格", "EMA10/20"]
        unmet = [labels[i] for i, c in enumerate(cond) if not c]
        sc.notes["S1"] = f"均线共振 {met}/2{'，未满足: ' + '、'.join(unmet) if unmet else '，完美共振'}"
    else:
        sc.s1 = 5
        sc.notes["S1"] = "EMA 数据不足，给予中性分"

    # ── S2：相对强度 (10分) ───────────────────────────────────
    qqq_day = qqq.get(trade.date, [])
    pre_start = max(0, ei - 30)
    stock_pre = day[pre_start: ei + 1]
    if qqq_day and stock_pre:
        qi = bar_at(qqq_day, trade.entry_time)
        qqq_pre = qqq_day[max(0, qi - 30): qi + 1]
        if qqq_pre:
            sr = (stock_pre[-1].close - stock_pre[0].open) / stock_pre[0].open
            qr = (qqq_pre[-1].close - qqq_pre[0].open) / qqq_pre[0].open
            excess = sign * (sr - qr)
            sc.s2 = 10 if excess > RS_OUTPERFORM else (5 if excess > 0 else 0)
            sc.notes["S2"] = f"进场前30分超额收益={excess*100:+.2f}%（vs QQQ）"
        else:
            sc.s2, sc.notes["S2"] = 5, "QQQ 数据不足"
    else:
        sc.s2, sc.notes["S2"] = 5, "无 QQQ 数据，给予中性分"

    # ── S3：波动收敛 (10分) ───────────────────────────────────
    pre10 = day[max(0, ei - 10): ei]
    if pre10:
        rng = max(b.high for b in pre10) - min(b.low for b in pre10)
        avg_p = sum(b.close for b in pre10) / len(pre10)
        ratio = rng / avg_p if avg_p else 1.0
        sc.s3 = 10 if ratio < VOL_CONV_GOOD else (5 if ratio < VOL_CONV_WARN else 0)
        sc.notes["S3"] = f"入场前震荡幅度={ratio*100:.2f}%（{'收敛' if ratio < VOL_CONV_GOOD else '偏宽'}）"
    else:
        sc.s3, sc.notes["S3"] = 5, "数据不足"

    # ── E1：量能触发 (10分) ───────────────────────────────────
    avg20 = day[max(0, ei - 20): ei]
    if avg20:
        avg_vol = sum(b.volume for b in avg20) / len(avg20)
        rv = eb.volume / avg_vol if avg_vol else 1.0
        sc.e1 = 10 if rv >= REL_VOL_HIGH else (5 if rv >= REL_VOL_LOW else 0)
        sc.notes["E1"] = f"相对成交量={rv:.2f}x（阈值 {REL_VOL_HIGH}x）"
    else:
        sc.e1, sc.notes["E1"] = 5, "数据不足"

    # ── E2：追高系数 (10分) ───────────────────────────────────
    bar_range = eb.high - eb.low
    if bar_range > 1e-6:
        raw = (trade.entry_price - eb.low) / bar_range
        raw = max(0.0, min(1.0, raw))           # 成交均价偶尔超出bar区间，钳制到[0,1]
        chase = raw if sign == 1 else (1 - raw) # 空头：希望在高位卖，chase 越小越好
        sc.e2 = 10 if chase < CHASE_MAX else (5 if chase < CHASE_WARN else 0)
        sc.notes["E2"] = f"追{'高' if sign==1 else '低'}系数={chase:.2f}（上限 {CHASE_MAX}）"
    else:
        sc.e2, sc.notes["E2"] = 5, "K线实体为0（一字线）"

    # ── E3：乖离率 (5分) ─────────────────────────────────────
    if eb.ema20 and eb.ema20 > 0:
        bias = abs(trade.entry_price - eb.ema20) / eb.ema20
        sc.e3 = 5 if bias < BIAS_GOOD else (2 if bias < BIAS_WARN else 0)
        sc.notes["E3"] = f"EMA20 乖离率={bias*100:.2f}%（阈值 {BIAS_GOOD*100:.0f}%）"
    else:
        sc.e3, sc.notes["E3"] = 2, "EMA20 数据不足"

    # ── 交易区间分析 ──────────────────────────────────────────
    trade_bars = day[ei: xi + 1]
    if trade_bars:
        max_hi = max(b.high for b in trade_bars)
        min_lo = min(b.low for b in trade_bars)
        if sign == 1:
            best = max_hi
            worst = min_lo
        else:
            best = min_lo
            worst = max_hi
    else:
        best = trade.exit_price
        worst = trade.entry_price

    potential = abs(best - trade.entry_price)
    actual    = sign * (trade.exit_price - trade.entry_price)
    mae       = abs(worst - trade.entry_price) / trade.entry_price

    # ── X1：利润留存比 (10分) ────────────────────────────────
    if potential > 1e-6:
        capture = actual / potential
        sc.x1 = 10 if capture >= CAPTURE_GOOD else (5 if capture >= CAPTURE_WARN else 0)
        sc.notes["X1"] = f"利润留存={capture*100:.1f}%（实盈={actual:.2f}，最大波动={potential:.2f}）"
    else:
        sc.x1 = 5 if actual >= 0 else 0
        sc.notes["X1"] = "波动空间不足，无法有效评估"

    # ── X2：反转出场 (5分) ───────────────────────────────────
    post = day[xi + 1: xi + 4]
    if post:
        if sign == 1:
            missed_pct = max(0, max(b.high for b in post) - trade.exit_price) / trade.entry_price
        else:
            missed_pct = max(0, trade.exit_price - min(b.low for b in post)) / trade.entry_price
        sc.x2 = 5 if missed_pct < POST_MISS_GOOD else (2 if missed_pct < POST_MISS_WARN else 0)
        sc.notes["X2"] = f"出场后额外{'涨幅' if sign==1 else '跌幅'}={missed_pct*100:.2f}%"
    else:
        sc.x2, sc.notes["X2"] = 5, "已是末尾K线，无后续数据"

    if cross_day:
        sc.notes["cross_day"] = f"⚠️ 跨日持仓（出场于 {trade.exit_time} 盘前），出场维度基于当日末尾估算"

    # ── X3：时间纪律 (5分) ───────────────────────────────────
    stagnant_count = sum(
        1 for b in trade_bars[:STAGNATION_BARS]
        if abs(b.close - trade.entry_price) / trade.entry_price < STAGNATION_PCT
    )
    hold_bars = xi - ei
    if stagnant_count >= STAGNATION_BARS and hold_bars > STAGNATION_BARS * 2:
        sc.x3 = 0
        sc.notes["X3"] = f"横盘 {stagnant_count} 根后仍持有 {hold_bars} 根K线，存在盲目持有"
    else:
        sc.x3 = 5
        sc.notes["X3"] = f"持仓 {hold_bars} 根K线，无明显横盘拖延"

    # ── R1：硬止损 (10分) ────────────────────────────────────
    sc.r1 = 10 if mae <= STOP_LOSS_PCT else (5 if mae <= STOP_LOSS_PCT * 1.5 else 0)
    sc.notes["R1"] = f"最大不利偏移={mae*100:.2f}%（止损线={STOP_LOSS_PCT*100:.0f}%）"

    # ── R2：仓位一致性 (5分) ─────────────────────────────────
    pos_pct = (trade.entry_price * trade.quantity) / ACCOUNT_TOTAL
    diff = abs(pos_pct - POSITION_PCT_TARGET)
    sc.r2 = 5 if diff < 0.03 else (2 if diff < 0.06 else 0)
    sc.notes["R2"] = (
        f"实际仓位={pos_pct*100:.1f}% vs 目标={POSITION_PCT_TARGET*100:.0f}%"
        f"（账户假设=${ACCOUNT_TOTAL:,}）"
    )

    # ── T1：信号延迟 (5分) ───────────────────────────────────
    lag = abs(time_diff_min(trade.entry_order_time, trade.entry_time))
    sc.t1 = 5 if lag <= LAG_GOOD_MIN else (2 if lag <= LAG_WARN_MIN else 0)
    sc.notes["T1"] = f"下单至成交延迟={lag:.1f} 分钟"

    # ── T2：报复性交易 (5分) ─────────────────────────────────
    if prev_loss:
        gap = time_diff_min(
            f"{prev_loss.date.replace('-','/')} {prev_loss.exit_time}",
            f"{trade.date.replace('-','/')} {trade.entry_time}",
        ) if prev_loss.date == trade.date else 9999
        # cross-day gap: always OK
        if prev_loss.date != trade.date:
            sc.t2, sc.notes["T2"] = 5, "非同日连续亏损，无报复交易风险"
        elif gap < REVENGE_MIN:
            sc.t2 = 0
            sc.notes["T2"] = f"距上次亏损出场仅 {gap:.0f} 分钟（< {REVENGE_MIN} 分钟），疑似报复性交易"
        else:
            sc.t2 = 5
            sc.notes["T2"] = f"距上次亏损出场 {gap:.0f} 分钟，情绪冷却充分"
    else:
        sc.t2, sc.notes["T2"] = 5, "无前序亏损交易记录"

    return sc


# ── 报告输出 ──────────────────────────────────────────────────

def render(trade: Trade, sc: Score) -> str:
    dir_label = "做多▲" if trade.direction == "long" else "做空▼"
    pnl_sign = "+" if trade.pnl_usd >= 0 else ""
    cross_note = f"\n> {sc.notes['cross_day']}" if "cross_day" in sc.notes else ""
    lines = [
        f"### 复盘报告：{trade.ticker} - {trade.date}（{dir_label}）",
        "",
        f"> **综合评分：{sc.total}/100（{sc.grade()}）**{cross_note}",
        f"> 入场 {trade.entry_time} @ **{trade.entry_price:.2f}** → "
        f"出场 {trade.exit_time} @ **{trade.exit_price:.2f}** | "
        f"盈亏：{pnl_sign}{trade.pnl_usd:.2f} USD"
        f"（{pnl_sign}{trade.pnl_pct*100:.2f}%）× {trade.quantity} 股",
        "",
        f"| 维度 | 得分 | 详情 |",
        f"| --- | --- | --- |",
        f"| **[结构] {sc.structure}/30** | S1趋势共振 {sc.s1}/10 | {sc.notes.get('S1','-')} |",
        f"| | S2相对强度 {sc.s2}/10 | {sc.notes.get('S2','-')} |",
        f"| | S3波动收敛 {sc.s3}/10 | {sc.notes.get('S3','-')} |",
        f"| **[入场] {sc.entry}/25** | E1量能触发 {sc.e1}/10 | {sc.notes.get('E1','-')} |",
        f"| | E2价格偏离 {sc.e2}/10 | {sc.notes.get('E2','-')} |",
        f"| | E3静态位置 {sc.e3}/5 | {sc.notes.get('E3','-')} |",
        f"| **[出场] {sc.exit}/20** | X1利润留存 {sc.x1}/10 | {sc.notes.get('X1','-')} |",
        f"| | X2反转出场 {sc.x2}/5 | {sc.notes.get('X2','-')} |",
        f"| | X3时间纪律 {sc.x3}/5 | {sc.notes.get('X3','-')} |",
        f"| **[风控] {sc.risk}/15** | R1硬止损 {sc.r1}/10 | {sc.notes.get('R1','-')} |",
        f"| | R2仓位 {sc.r2}/5 | {sc.notes.get('R2','-')} |",
        f"| **[情绪] {sc.sentiment}/10** | T1信号延迟 {sc.t1}/5 | {sc.notes.get('T1','-')} |",
        f"| | T2报复交易 {sc.t2}/5 | {sc.notes.get('T2','-')} |",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def main():
    if not TRANSACTION_FILE.exists():
        print(f"错误：找不到 {TRANSACTION_FILE}")
        return

    all_orders = load_orders()
    all_trades = pair_trades(all_orders)

    available = {
        ticker for ticker in set(t.ticker for t in all_trades)
        if (DATA_DIR / f"{ticker}.records").exists()
    }

    valid_trades = [t for t in all_trades if t.ticker in available]
    skipped = [t for t in all_trades if t.ticker not in available]

    qqq = load_records("QQQ")
    records_cache: dict[str, dict[str, list[Bar]]] = {
        ticker: load_records(ticker) for ticker in available
    }

    print("# 交易质量复盘报告\n")
    print(f"- 分析交易：**{len(valid_trades)}** 笔（跳过无数据标的：{len(skipped)} 笔）")
    if skipped:
        skip_info = ", ".join(f"{t.ticker}({t.date})" for t in skipped)
        print(f"- 跳过标的：{skip_info}")
    print()
    print("---\n")

    results: list[tuple[Trade, Score]] = []
    prev_loss: Optional[Trade] = None

    for trade in valid_trades:
        sc = score_trade(trade, records_cache[trade.ticker], qqq, prev_loss)
        results.append((trade, sc))
        if trade.pnl_pct < 0:
            prev_loss = trade

    for trade, sc in results:
        print(render(trade, sc))

    # ── 汇总 ──────────────────────────────────────────────────
    if not results:
        return

    wins  = [(t, s) for t, s in results if t.pnl_pct > 0]
    loses = [(t, s) for t, s in results if t.pnl_pct < 0]
    total_pnl = sum(t.pnl_usd for t, _ in results)

    def avg(vals: list[int]) -> str:
        return f"{sum(vals)/len(vals):.1f}" if vals else "N/A"

    scores = [s.total for _, s in results]
    print("## 📊 汇总统计\n")
    print(f"| 指标 | 值 |")
    print(f"| --- | --- |")
    print(f"| 总交易笔数 | {len(results)} |")
    print(f"| 胜率 | {len(wins)/len(results)*100:.1f}%（{len(wins)}胜 {len(loses)}负）|")
    print(f"| 合计盈亏 | {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} USD |")
    print(f"| 平均综合分 | {avg(scores)}/100 |")
    print(f"| 平均结构分 | {avg([s.structure for _,s in results])}/30 |")
    print(f"| 平均入场分 | {avg([s.entry for _,s in results])}/25 |")
    print(f"| 平均出场分 | {avg([s.exit for _,s in results])}/20 |")
    print(f"| 平均风控分 | {avg([s.risk for _,s in results])}/15 |")
    print(f"| 平均情绪分 | {avg([s.sentiment for _,s in results])}/10 |")

    if results:
        best = max(results, key=lambda x: x[1].total)
        worst = min(results, key=lambda x: x[1].total)
        print(f"| 最高分交易 | {best[0].ticker} {best[0].date} {best[1].total}分 |")
        print(f"| 最低分交易 | {worst[0].ticker} {worst[0].date} {worst[1].total}分 |")


if __name__ == "__main__":
    main()
