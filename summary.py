#!/usr/bin/env python3
'''
## 8. 项目要求（数据分析-交易总结）
我需要根据 data 中的数据标的交易数据进行数据分析(新的Python脚本)。
数据说明
- 数据有两类，1 是标的的分时数据，由 Python 抓取而来，每个文件名是“标的.records"；2 是交易记录，是最近的交易记录，文件名是 transaction.csv
- 交易记录有些标的的历史记录尚没有抓取（文件不存在），可以忽略这些交易记录

这个数据分析的主要目的是 **分析交易特性**，目标：通过将**分时数据（行情）与交易记录（动作）**对齐，我们可以从心理、技术和执行三个维度还原你的交易逻辑。
下是一个量化分析模型的逻辑框架，分为四个核心模块：

1. 基础画像模块 (Basic Statistics)
首先通过静态数据，定义你的交易“底色”。

胜率与盈亏比： 计算总期望值，判断你是靠“高准确率”生存还是靠“捕捉大行情”生存。

持仓周期分布： 统计从买入到卖出的平均时长，识别你是日内超短、波段还是长线。

周内/日内活跃度： 分析你在交易日哪个时段（如开盘半小时、尾盘）交易最频繁，以及胜率最高。

2. 择时质量分析 (Timing & Entry/Exit)
这是最核心的部分，需要将交易点位映射到分时图（Min-level）上。

入场位置评价： * 左侧 vs 右侧： 观察买入点是在价格下跌企稳前（抄底）还是放量突破后（追高）。

相对位置： 买入点处于当日振幅的百分比位置。

出场效率 (Excursion Analysis)：

MFE (最大潜在利润)： 卖出后，价格是否继续大幅上涨？（是否存在恐慌性早卖）

MAE (最大回撤)： 买入后，价格反向运行了多少才企稳？（入场点是否过于急躁）

反向指标检验： 统计“卖出即起飞”或“买入即巅峰”的频率。

3. 价格行为一致性 (Price Action Consistency)
分析你下单时的市场环境（Context）。

趋势跟随度： 下单时，价格是处于均线（如 VWAP 或 20线）上方还是下方？你是在顺势而为还是执着于逆势。

波动率偏好： 你倾向于在缩量盘整时潜伏，还是在放量剧烈波动时入场？

成交量分布： 你的买入是否伴随成交量异常放大（确认信号）。

4. 风险控制与心态画像 (Risk & Psychology)
通过数据捕捉潜意识里的交易缺陷。

止损果断性： 亏损单的持仓时长是否显著长于盈利单？（是否存在“扛单”行为）

加仓逻辑： 盈利加仓（锦上添花）还是亏损加仓（摊平摊死）。

复利与情绪性交易： 在一笔大亏后，下一笔交易的间隔时间和仓位变化情况（是否存在报复性交易）。

5. 可考虑建议（非强制）： 为分时表增加计算列，如 VWAP（成交量加权平均价）、Relative_Volume（相对成交量）、Volatility（波动率）。
'''
"""交易特性分析报告"""

import csv
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR = Path("./data")
TRANSACTION_FILE = DATA_DIR / "transaction.csv"
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ── 数据结构（与 analyze.py 共享逻辑，独立实现） ──────────────

@dataclass
class Bar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    ema20: Optional[float]


@dataclass
class Trade:
    ticker: str
    date: str
    direction: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    quantity: int
    order_time: str

    @property
    def sign(self) -> int:
        return 1 if self.direction == "long" else -1

    @property
    def pnl_pct(self) -> float:
        return self.sign * (self.exit_price - self.entry_price) / self.entry_price

    @property
    def pnl_usd(self) -> float:
        return self.sign * (self.exit_price - self.entry_price) * self.quantity

    @property
    def is_win(self) -> bool:
        return self.pnl_usd > 0


@dataclass
class RichTrade:
    trade: Trade
    hold_minutes: float
    cross_day: bool
    day_position_pct: float     # 入场价在当日振幅的百分位 [0,1]
    entry_side: str              # "左侧" / "右侧"
    mfe_pct: float               # 最大潜在利润 %
    mae_pct: float               # 最大不利回撤 %
    post_exit_pct: float         # 出场后额外运行 %（反向指标）
    capture_pct: float           # 利润捕获率 = actual/(actual+post)
    above_vwap: bool             # 入场时是否在 VWAP 上方
    above_ema20: bool            # 入场时是否在 EMA20 上方
    rel_volume: float            # 入场分钟成交量相对倍数
    entry_hour: int
    entry_weekday: int           # 0=周一


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
                Bar(b["time"], b["open"], b["high"], b["low"],
                    b["close"], b["volume"], b.get("EMA_20"))
                for b in json.loads(line[sep + 2:])
            ]
    return result


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s.split(" (")[0].strip(), "%Y/%m/%d %H:%M:%S")


def parse_filled(s: str) -> tuple[int, float]:
    qty, price = s.split("@")
    return int(qty), float(price.replace(",", ""))


def load_orders() -> list[dict]:
    rows = []
    with open(TRANSACTION_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row["方向"] or row["市场"] != "美股":
                continue
            if row["交易状态"] != "全部成交":
                continue
            if not row.get("已成交@均价") or "@" not in row["已成交@均价"]:
                continue
            rows.append(row)
    return rows


def pair_trades(orders: list[dict]) -> list[Trade]:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for o in orders:
        by_ticker[o["代码"]].append(o)

    trades: list[Trade] = []
    for ticker, grp in by_ticker.items():
        grp.sort(key=lambda x: parse_dt(x["成交时间"]))
        pos = 0
        entry: Optional[dict] = None
        for o in grp:
            qty, price = parse_filled(o["已成交@均价"])
            fill_dt = parse_dt(o["成交时间"])
            d = o["方向"]
            if d == "买入" and pos == 0:
                pos, entry = qty, o
            elif d == "卖空" and pos == 0:
                pos, entry = -qty, o
            elif d == "卖出" and pos > 0 and entry:
                eq, ep = parse_filled(entry["已成交@均价"])
                edt = parse_dt(entry["成交时间"])
                trades.append(Trade(
                    ticker=ticker, date=edt.strftime("%Y-%m-%d"), direction="long",
                    entry_time=edt.strftime("%H:%M"), entry_price=ep,
                    exit_time=fill_dt.strftime("%H:%M"), exit_price=price,
                    quantity=min(qty, eq), order_time=parse_dt(entry["下单时间"]).strftime("%H:%M"),
                ))
                pos, entry = 0, None
            elif d == "买入" and pos < 0 and entry:
                eq, ep = parse_filled(entry["已成交@均价"])
                edt = parse_dt(entry["成交时间"])
                trades.append(Trade(
                    ticker=ticker, date=edt.strftime("%Y-%m-%d"), direction="short",
                    entry_time=edt.strftime("%H:%M"), entry_price=ep,
                    exit_time=fill_dt.strftime("%H:%M"), exit_price=price,
                    quantity=min(qty, abs(pos)), order_time=parse_dt(entry["下单时间"]).strftime("%H:%M"),
                ))
                pos, entry = 0, None
    return sorted(trades, key=lambda t: (t.date, t.entry_time))


# ── 行情辅助 ──────────────────────────────────────────────────

def bar_idx(bars: list[Bar], t: str) -> int:
    for i, b in enumerate(bars):
        if b.time >= t:
            return i
    return len(bars) - 1


def vwap_at(bars: list[Bar], idx: int) -> float:
    cum_tp_vol = sum((b.high + b.low + b.close) / 3 * b.volume for b in bars[:idx + 1])
    cum_vol = sum(b.volume for b in bars[:idx + 1])
    return cum_tp_vol / cum_vol if cum_vol else bars[idx].close


def hold_mins(trade: Trade, cross_day: bool) -> float:
    base = datetime(2000, 1, 1)
    et = datetime.strptime(trade.entry_time, "%H:%M").replace(2000, 1, 1)
    if cross_day:
        xt = datetime.strptime(trade.exit_time, "%H:%M").replace(2000, 1, 2)  # next day
    else:
        xt = datetime.strptime(trade.exit_time, "%H:%M").replace(2000, 1, 1)
    _ = base
    return max(0.0, (xt - et).total_seconds() / 60)


# ── 丰富单笔交易 ──────────────────────────────────────────────

def enrich(trade: Trade, records: dict[str, list[Bar]]) -> Optional[RichTrade]:
    day = records.get(trade.date)
    if not day:
        return None

    ei = bar_idx(day, trade.entry_time)
    xi_raw = bar_idx(day, trade.exit_time)
    cross = xi_raw < ei
    xi = len(day) - 1 if cross else xi_raw

    sign = trade.sign
    trade_bars = day[ei: xi + 1]
    post_bars  = day[xi + 1: xi + 6]
    avg20_vol  = sum(b.volume for b in day[max(0, ei - 20): ei]) or 1
    avg20_n    = max(1, min(20, ei))

    day_high = max(b.high for b in day)
    day_low  = min(b.low  for b in day)
    rng = day_high - day_low or 1e-6

    eb = day[ei]
    mfe = max(((b.high if sign == 1 else -b.low) for b in trade_bars),
              default=trade.entry_price * sign) * sign
    mae = min(((b.low  if sign == 1 else -b.high) for b in trade_bars),
              default=trade.entry_price * sign) * sign

    mfe_pct = max(0.0, sign * (mfe - trade.entry_price) / trade.entry_price)
    mae_pct = max(0.0, sign * (trade.entry_price - mae) / trade.entry_price)

    if post_bars:
        post_ext = max(b.high for b in post_bars) if sign == 1 else min(b.low for b in post_bars)
        post_pct = max(0.0, sign * (post_ext - trade.exit_price) / trade.entry_price)
    else:
        post_pct = 0.0

    actual_pct = sign * (trade.exit_price - trade.entry_price) / trade.entry_price
    capture = actual_pct / (actual_pct + post_pct) if (actual_pct + post_pct) > 1e-6 else 1.0

    day_pos = (trade.entry_price - day_low) / rng
    day_pos = max(0.0, min(1.0, day_pos))
    # 左侧/右侧：long 在低位(<0.4)=左侧, short 在高位(>0.6)=左侧
    if sign == 1:
        side = "左侧" if day_pos < 0.4 else "右侧"
    else:
        side = "左侧" if day_pos > 0.6 else "右侧"

    vwap = vwap_at(day, ei)
    rel_vol = eb.volume / (avg20_vol / avg20_n) if avg20_n else 1.0

    entry_dt = datetime.strptime(f"{trade.date} {trade.entry_time}", "%Y-%m-%d %H:%M")

    return RichTrade(
        trade=trade,
        hold_minutes=hold_mins(trade, cross),
        cross_day=cross,
        day_position_pct=day_pos,
        entry_side=side,
        mfe_pct=mfe_pct * 100,
        mae_pct=mae_pct * 100,
        post_exit_pct=post_pct * 100,
        capture_pct=capture * 100,
        above_vwap=(trade.entry_price > vwap),
        above_ema20=(eb.ema20 is not None and trade.entry_price > eb.ema20),
        rel_volume=rel_vol,
        entry_hour=entry_dt.hour,
        entry_weekday=entry_dt.weekday(),
    )


# ── 报告工具 ──────────────────────────────────────────────────

def pct_bar(value: float, total: int, width: int = 20) -> str:
    filled = round(value / total * width) if total else 0
    return "█" * filled + "░" * (width - filled)


def safe_mean(lst: list[float]) -> float:
    return statistics.mean(lst) if lst else 0.0


def safe_median(lst: list[float]) -> float:
    return statistics.median(lst) if lst else 0.0


# ── 四大模块 ──────────────────────────────────────────────────

def module1(rich: list[RichTrade]) -> str:
    trades = [r.trade for r in rich]
    wins   = [r for r in rich if r.trade.is_win]
    loses  = [r for r in rich if not r.trade.is_win]
    n = len(rich)

    total_pnl = sum(t.pnl_usd for t in trades)
    avg_win   = safe_mean([r.trade.pnl_usd for r in wins])
    avg_loss  = safe_mean([r.trade.pnl_usd for r in loses])
    pf = abs(avg_win / avg_loss) if avg_loss else float("inf")
    expectancy = (len(wins) / n * avg_win + len(loses) / n * avg_loss) if n else 0

    hold_all  = [r.hold_minutes for r in rich if not r.cross_day]
    hold_win  = [r.hold_minutes for r in wins  if not r.cross_day]
    hold_loss = [r.hold_minutes for r in loses if not r.cross_day]

    # 周内统计
    by_day: dict[int, list[RichTrade]] = defaultdict(list)
    for r in rich:
        by_day[r.entry_weekday].append(r)

    # 日内时段统计
    by_hour: dict[int, list[RichTrade]] = defaultdict(list)
    for r in rich:
        by_hour[r.entry_hour].append(r)

    lines = ["## 1. 基础画像 (Basic Statistics)\n"]

    lines += ["### 总体表现\n", "| 指标 | 值 |", "| --- | --- |",
              f"| 总交易笔数 | {n} |",
              f"| 胜率 | {len(wins)/n*100:.1f}% （{len(wins)}胜 / {len(loses)}负）|",
              f"| 合计盈亏 | {total_pnl:+.2f} USD |",
              f"| 平均盈利 | +{avg_win:.2f} USD |",
              f"| 平均亏损 | {avg_loss:.2f} USD |",
              f"| 盈亏比 (P/F) | {pf:.2f} |",
              f"| 单笔期望值 | {expectancy:+.2f} USD |", ""]

    lines += ["### 持仓时长分布\n", "| 组别 | 均值 | 中位数 | 最短 | 最长 |", "| --- | --- | --- | --- | --- |"]
    for label, grp in [("全部", hold_all), ("盈利单", hold_win), ("亏损单", hold_loss)]:
        if grp:
            lines.append(f"| {label} | {safe_mean(grp):.1f}分钟 | {safe_median(grp):.1f}分钟 | "
                         f"{min(grp):.0f}分钟 | {max(grp):.0f}分钟 |")
    lines.append("")

    lines += ["### 周内活跃度\n", "| 交易日 | 次数 | 胜 | 负 | 胜率 | 盈亏 |", "| --- | --- | --- | --- | --- | --- |"]
    for wd in range(5):
        grp = by_day.get(wd, [])
        if not grp:
            continue
        w = sum(1 for r in grp if r.trade.is_win)
        pnl = sum(r.trade.pnl_usd for r in grp)
        lines.append(f"| {WEEKDAY_CN[wd]} | {len(grp)} | {w} | {len(grp)-w} | "
                     f"{w/len(grp)*100:.0f}% | {pnl:+.2f} |")
    lines.append("")

    lines += ["### 日内时段活跃度（ET）\n", "| 时段 | 次数 | 分布 | 胜率 | 盈亏 |", "| --- | --- | --- | --- | --- |"]
    for h in sorted(by_hour):
        grp = by_hour[h]
        w = sum(1 for r in grp if r.trade.is_win)
        pnl = sum(r.trade.pnl_usd for r in grp)
        bar = pct_bar(len(grp), n, 15)
        lines.append(f"| {h:02d}:xx | {len(grp)} | `{bar}` | {w/len(grp)*100:.0f}% | {pnl:+.2f} |")
    lines.append("")

    return "\n".join(lines)


def module2(rich: list[RichTrade]) -> str:
    n = len(rich)
    wins  = [r for r in rich if r.trade.is_win]
    loses = [r for r in rich if not r.trade.is_win]

    left  = [r for r in rich if r.entry_side == "左侧"]
    right = [r for r in rich if r.entry_side == "右侧"]

    # 入场日内位置分布
    pos_bins = {"低位(0~33%)": [], "中位(33~67%)": [], "高位(67~100%)": []}
    for r in rich:
        p = r.day_position_pct
        if p < 0.33:
            pos_bins["低位(0~33%)"].append(r)
        elif p < 0.67:
            pos_bins["中位(33~67%)"].append(r)
        else:
            pos_bins["高位(67~100%)"].append(r)

    # 卖出即起飞 / 买入即巅峰
    fly_after_exit   = [r for r in rich if r.post_exit_pct > 1.0 and r.trade.is_win]
    top_at_entry     = [r for r in rich if r.mae_pct > 1.0 and r.trade.pnl_pct < 0.005]

    lines = ["## 2. 择时质量分析 (Timing & Entry/Exit)\n"]

    lines += ["### 入场位置评价\n", "| 维度 | 左侧 | 右侧 |", "| --- | --- | --- |",
              f"| 笔数 | {len(left)} | {len(right)} |",
              f"| 胜率 | {sum(1 for r in left if r.trade.is_win)/max(1,len(left))*100:.0f}% "
              f"| {sum(1 for r in right if r.trade.is_win)/max(1,len(right))*100:.0f}% |",
              f"| 平均盈亏 | {safe_mean([r.trade.pnl_usd for r in left]):+.2f} "
              f"| {safe_mean([r.trade.pnl_usd for r in right]):+.2f} |", ""]

    lines += ["### 入场点当日振幅分布\n", "| 价格区间 | 笔数 | 胜率 | 平均盈亏 |", "| --- | --- | --- | --- |"]
    for label, grp in pos_bins.items():
        if grp:
            w = sum(1 for r in grp if r.trade.is_win)
            lines.append(f"| {label} | {len(grp)} | {w/len(grp)*100:.0f}% | "
                         f"{safe_mean([r.trade.pnl_usd for r in grp]):+.2f} |")
    lines.append("")

    lines += ["### 出场效率 (MFE / MAE)\n", "| 指标 | 全部 | 盈利单 | 亏损单 |", "| --- | --- | --- | --- |"]
    for label, field in [("平均MFE（持仓最大潜在收益）", "mfe_pct"),
                          ("平均MAE（持仓最大不利回撤）", "mae_pct"),
                          ("平均利润捕获率", "capture_pct")]:
        all_v  = [getattr(r, field) for r in rich]
        win_v  = [getattr(r, field) for r in wins]
        loss_v = [getattr(r, field) for r in loses]
        suffix = "%" if "pct" in field else ""
        lines.append(f"| {label} | {safe_mean(all_v):.1f}{suffix} "
                     f"| {safe_mean(win_v):.1f}{suffix} "
                     f"| {safe_mean(loss_v):.1f}{suffix} |")
    lines.append("")

    lines += ["### 反向指标检验\n"]

    lines.append(f"**卖出即起飞**（出场后价格继续运行 >1%）：{len(fly_after_exit)} 笔 / {n} 笔 "
                 f"（{len(fly_after_exit)/n*100:.0f}%）\n")
    if fly_after_exit:
        lines += ["| 标的 | 方向 | 入场时间 | 出场时间 | 实际盈亏 | 出场后继续运行 |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for r in sorted(fly_after_exit, key=lambda x: x.post_exit_pct, reverse=True):
            t = r.trade
            dir_label = "做多▲" if t.direction == "long" else "做空▼"
            lines.append(f"| {t.ticker} | {dir_label} | {t.date} {t.entry_time} "
                         f"| {t.exit_time} @ {t.exit_price:.2f} "
                         f"| {t.pnl_usd:+.2f} USD | +{r.post_exit_pct:.2f}% |")
        lines.append("")

    lines.append(f"**买入即巅峰**（MAE >1% 且最终盈亏 <0.5%）：{len(top_at_entry)} 笔 / {n} 笔 "
                 f"（{len(top_at_entry)/n*100:.0f}%）\n")
    if top_at_entry:
        lines += ["| 标的 | 方向 | 入场时间 | 出场时间 | MAE | 最终盈亏 |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for r in sorted(top_at_entry, key=lambda x: x.mae_pct, reverse=True):
            t = r.trade
            dir_label = "做多▲" if t.direction == "long" else "做空▼"
            lines.append(f"| {t.ticker} | {dir_label} | {t.date} {t.entry_time} "
                         f"| {t.exit_time} @ {t.exit_price:.2f} "
                         f"| -{r.mae_pct:.2f}% | {t.pnl_usd:+.2f} USD |")
        lines.append("")

    return "\n".join(lines)


def module3(rich: list[RichTrade]) -> str:
    n = len(rich)
    above_vwap = [r for r in rich if r.above_vwap]
    below_vwap = [r for r in rich if not r.above_vwap]
    above_ema  = [r for r in rich if r.above_ema20]
    below_ema  = [r for r in rich if not r.above_ema20]

    hi_vol  = [r for r in rich if r.rel_volume >= 1.5]
    mid_vol = [r for r in rich if 1.0 <= r.rel_volume < 1.5]
    low_vol = [r for r in rich if r.rel_volume < 1.0]

    def win_rate(grp: list[RichTrade]) -> str:
        if not grp:
            return "N/A"
        return f"{sum(1 for r in grp if r.trade.is_win)/len(grp)*100:.0f}%"

    def avg_pnl(grp: list[RichTrade]) -> str:
        if not grp:
            return "N/A"
        return f"{safe_mean([r.trade.pnl_usd for r in grp]):+.2f}"

    lines = ["## 3. 价格行为一致性 (Price Action Consistency)\n"]

    lines += ["### 趋势跟随度（入场时与均线关系）\n",
              "| 条件 | 笔数 | 胜率 | 平均盈亏 |", "| --- | --- | --- | --- |",
              f"| 入场价在 VWAP 上方 | {len(above_vwap)} | {win_rate(above_vwap)} | {avg_pnl(above_vwap)} |",
              f"| 入场价在 VWAP 下方 | {len(below_vwap)} | {win_rate(below_vwap)} | {avg_pnl(below_vwap)} |",
              f"| 入场价在 EMA20 上方 | {len(above_ema)} | {win_rate(above_ema)} | {avg_pnl(above_ema)} |",
              f"| 入场价在 EMA20 下方 | {len(below_ema)} | {win_rate(below_ema)} | {avg_pnl(below_ema)} |", ""]

    lines += ["### 波动率偏好（入场分钟相对成交量）\n",
              "| 成交量区间 | 笔数 | 胜率 | 平均盈亏 | 平均MFE |", "| --- | --- | --- | --- | --- |",
              f"| 高倍量 (≥1.5x) | {len(hi_vol)} | {win_rate(hi_vol)} | {avg_pnl(hi_vol)} | "
              f"{safe_mean([r.mfe_pct for r in hi_vol]):.2f}% |",
              f"| 中倍量 (1~1.5x) | {len(mid_vol)} | {win_rate(mid_vol)} | {avg_pnl(mid_vol)} | "
              f"{safe_mean([r.mfe_pct for r in mid_vol]):.2f}% |",
              f"| 低于均量 (<1x) | {len(low_vol)} | {win_rate(low_vol)} | {avg_pnl(low_vol)} | "
              f"{safe_mean([r.mfe_pct for r in low_vol]):.2f}% |", ""]

    vol_confirm = len(hi_vol)
    lines += [f"**成交量确认信号率**（入场分钟倍量≥1.5x）：{vol_confirm}/{n} 笔 "
              f"({vol_confirm/n*100:.0f}%)\n"]

    return "\n".join(lines)


def module4(rich: list[RichTrade]) -> str:
    wins  = [r for r in rich if r.trade.is_win]
    loses = [r for r in rich if not r.trade.is_win]

    hold_win  = [r.hold_minutes for r in wins  if not r.cross_day]
    hold_loss = [r.hold_minutes for r in loses if not r.cross_day]

    # 报复性交易检测
    revenge: list[tuple[RichTrade, RichTrade, float]] = []
    all_sorted = sorted(rich, key=lambda r: (r.trade.date, r.trade.entry_time))
    for i in range(1, len(all_sorted)):
        prev = all_sorted[i - 1]
        curr = all_sorted[i]
        if not prev.trade.is_win:
            prev_exit = datetime.strptime(
                f"{prev.trade.date} {prev.trade.exit_time}", "%Y-%m-%d %H:%M")
            curr_entry = datetime.strptime(
                f"{curr.trade.date} {curr.trade.entry_time}", "%Y-%m-%d %H:%M")
            gap = (curr_entry - prev_exit).total_seconds() / 60
            if 0 < gap < 15:
                revenge.append((prev, curr, gap))

    # 仓位一致性
    positions = [(r.trade.entry_price * r.trade.quantity) for r in rich]

    lines = ["## 4. 风险控制与心态画像 (Risk & Psychology)\n"]

    lines += ["### 止损果断性\n", "| 指标 | 盈利单 | 亏损单 | 差异 |", "| --- | --- | --- | --- |"]
    mw = safe_mean(hold_win)
    ml = safe_mean(hold_loss)
    lines += [
        f"| 平均持仓时长 | {mw:.1f}分钟 | {ml:.1f}分钟 | "
        f"{'亏损单拖延明显 ⚠️' if ml > mw * 1.5 else '差异正常 ✅'} |",
        f"| 最长持仓 | {max(hold_win, default=0):.0f}分钟 "
        f"| {max(hold_loss, default=0):.0f}分钟 | — |",
    ]
    if ml > mw * 1.5:
        lines.append(f"\n> ⚠️ **扛单风险**：亏损单平均持仓（{ml:.1f}分钟）是盈利单（{mw:.1f}分钟）的 "
                     f"{ml/mw:.1f}倍，存在不愿认亏的心理偏差。")
    else:
        lines.append(f"\n> ✅ 盈亏单持仓时长差异在合理范围，止损纪律尚好。")
    lines.append("")

    lines += ["### 报复性交易检测\n"]
    if revenge:
        lines.append(f"检测到 **{len(revenge)}** 笔潜在报复性交易（上笔亏损后 <15分钟再入场）：\n")
        lines += ["| # | 前笔亏损 | 盈亏 | 间隔 | 新入场 | 结果 |", "| --- | --- | --- | --- | --- | --- |"]
        for i, (prev, curr, gap) in enumerate(revenge, 1):
            lines.append(
                f"| {i} | {prev.trade.ticker} {prev.trade.entry_time}→{prev.trade.exit_time} "
                f"| {prev.trade.pnl_usd:+.2f} | {gap:.0f}分钟 "
                f"| {curr.trade.ticker} {curr.trade.entry_time} "
                f"| {curr.trade.pnl_usd:+.2f} |"
            )
    else:
        lines.append("✅ 未检测到明显报复性交易（所有亏损后再入场间隔均 ≥15 分钟）。")
    lines.append("")

    lines += ["### 仓位一致性\n",
              f"| 指标 | 值 |", f"| --- | --- |",
              f"| 平均单笔仓位 | {safe_mean(positions):,.0f} USD |",
              f"| 最大单笔仓位 | {max(positions, default=0):,.0f} USD |",
              f"| 最小单笔仓位 | {min(positions, default=0):,.0f} USD |",
              f"| 仓位标准差 | {statistics.stdev(positions) if len(positions) > 1 else 0:,.0f} USD |",
              ""]

    lines.append("### 连续亏损后的下一笔表现\n")
    consecutive_loss_follow = []
    for i in range(1, len(all_sorted)):
        if not all_sorted[i - 1].trade.is_win:
            consecutive_loss_follow.append(all_sorted[i])
    if consecutive_loss_follow:
        n_follow = len(consecutive_loss_follow)
        n_win = sum(1 for r in consecutive_loss_follow if r.trade.is_win)
        avg_p = safe_mean([r.trade.pnl_usd for r in consecutive_loss_follow])
        lines += [f"亏损后的下一笔：**{n_follow}** 笔，胜率 **{n_win/n_follow*100:.0f}%**，"
                  f"平均盈亏 **{avg_p:+.2f} USD**",
                  "",
                  f"> {'⚠️ 亏损后胜率偏低，情绪可能影响判断' if n_win/n_follow < 0.5 else '✅ 亏损后保持了较好的决策质量'}"]
    lines.append("")

    return "\n".join(lines)


# ── 主程序 ────────────────────────────────────────────────────

def main():
    if not TRANSACTION_FILE.exists():
        print(f"错误：找不到 {TRANSACTION_FILE}")
        return

    orders = load_orders()
    trades = pair_trades(orders)

    available = {
        t for t in set(tr.ticker for tr in trades)
        if (DATA_DIR / f"{t}.records").exists()
    }
    cache = {t: load_records(t) for t in available}
    valid = [tr for tr in trades if tr.ticker in available]

    rich: list[RichTrade] = []
    for tr in valid:
        r = enrich(tr, cache[tr.ticker])
        if r:
            rich.append(r)

    print("# 交易特性分析报告\n")
    print(f"> 数据覆盖：{len(rich)} 笔交易 | "
          f"标的：{', '.join(sorted(available))} | "
          f"时间跨度：{min(r.trade.date for r in rich)} ~ {max(r.trade.date for r in rich)}\n")
    print("---\n")
    print(module1(rich))
    print(module2(rich))
    print(module3(rich))
    print(module4(rich))


if __name__ == "__main__":
    main()
