from dataclasses import dataclass

from indicators.snapshot import Snapshot

BIAS_LONG = "偏多"
BIAS_SHORT = "偏空"
BIAS_RANGE = "震荡"

LONG_THRESHOLD = 2
SHORT_THRESHOLD = -2

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_BULL_LOW = 50
RSI_BEAR_LOW = 30


@dataclass
class Vote:
    name: str
    score: int
    reason: str


@dataclass
class BiasResult:
    bias: str
    score: int
    votes: list[Vote]
    risks: list[str]


def _ma_vote(s: Snapshot) -> Vote:
    if s.price > s.ma_fast > s.ma_slow:
        return Vote("均线排列", 1, f"价 {s.price:.2f} > MA20 {s.ma_fast:.2f} > MA50 {s.ma_slow:.2f}，多头排列")
    if s.price < s.ma_fast < s.ma_slow:
        return Vote("均线排列", -1, f"价 {s.price:.2f} < MA20 {s.ma_fast:.2f} < MA50 {s.ma_slow:.2f}，空头排列")
    return Vote("均线排列", 0, f"价 {s.price:.2f} 与 MA20/MA50 缠绕，无明确排列")


def _higher_trend_vote(s: Snapshot) -> Vote:
    if s.higher_trend_ema is None:
        return Vote("4h趋势", 0, "4h EMA200 样本不足，趋势未知")
    if s.higher_close is None:
        return Vote("4h趋势", 0, "4h 收盘缺失，趋势未知")
    if s.higher_close > s.higher_trend_ema:
        return Vote("4h趋势", 1, f"4h 收盘 {s.higher_close:.2f} > EMA200 {s.higher_trend_ema:.2f}，大趋势向上")
    return Vote("4h趋势", -1, f"4h 收盘 {s.higher_close:.2f} < EMA200 {s.higher_trend_ema:.2f}，大趋势向下")


def _macd_vote(s: Snapshot) -> Vote:
    if s.macd_dif > s.macd_dea and s.macd_hist > 0:
        return Vote("MACD", 1, f"DIF {s.macd_dif:.2f} > DEA {s.macd_dea:.2f} 且柱 {s.macd_hist:.2f}>0，多头动能")
    if s.macd_dif < s.macd_dea and s.macd_hist < 0:
        return Vote("MACD", -1, f"DIF {s.macd_dif:.2f} < DEA {s.macd_dea:.2f} 且柱 {s.macd_hist:.2f}<0，空头动能")
    return Vote("MACD", 0, f"DIF {s.macd_dif:.2f} / DEA {s.macd_dea:.2f} 动能不明")


def _rsi_vote(s: Snapshot) -> Vote:
    if RSI_BULL_LOW <= s.rsi < RSI_OVERBOUGHT:
        return Vote("RSI", 1, f"RSI {s.rsi:.1f} 处于 50-70 偏强区间")
    if RSI_BEAR_LOW < s.rsi <= RSI_BULL_LOW:
        return Vote("RSI", -1, f"RSI {s.rsi:.1f} 处于 30-50 偏弱区间")
    return Vote("RSI", 0, f"RSI {s.rsi:.1f} 处于极值区，方向不计入（见风险）")


def _risks(s: Snapshot, votes: list[Vote]) -> list[str]:
    risks: list[str] = []
    if s.rsi >= RSI_OVERBOUGHT:
        risks.append(f"RSI {s.rsi:.1f} 超买（≥70），追高有回调风险")
    elif s.rsi <= RSI_OVERSOLD:
        risks.append(f"RSI {s.rsi:.1f} 超卖（≤30），抄底有继续下跌风险")

    if s.bb_pct >= 1:
        risks.append("价格触及/突破布林上轨，短期超买")
    elif s.bb_pct <= 0:
        risks.append("价格触及/跌破布林下轨，短期超卖")

    ma = next(v for v in votes if v.name == "均线排列")
    higher = next(v for v in votes if v.name == "4h趋势")
    if ma.score * higher.score < 0:
        risks.append("1h 均线方向与 4h 大趋势背离，信号可靠性下降")

    if s.volume_ma > 0 and s.volume < s.volume_ma * 0.7:
        risks.append("成交量明显萎缩（低于均量 30%），趋势动能不足")
    return risks


def classify_bias(snapshot: Snapshot) -> BiasResult:
    """打分制倾向分类：每个指标投 +1/-1/0，加总定档。结论由代码决定，可回测。"""
    votes = [
        _ma_vote(snapshot),
        _higher_trend_vote(snapshot),
        _macd_vote(snapshot),
        _rsi_vote(snapshot),
    ]
    score = sum(v.score for v in votes)

    if score >= LONG_THRESHOLD:
        bias = BIAS_LONG
    elif score <= SHORT_THRESHOLD:
        bias = BIAS_SHORT
    else:
        bias = BIAS_RANGE

    return BiasResult(
        bias=bias,
        score=score,
        votes=votes,
        risks=_risks(snapshot, votes),
    )
