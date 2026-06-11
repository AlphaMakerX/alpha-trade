from indicators.bias import BIAS_LONG, BIAS_RANGE, BIAS_SHORT, classify_bias
from indicators.snapshot import Snapshot


def make_snapshot(
    price,
    ma_fast,
    ma_slow,
    rsi,
    macd_dif,
    macd_dea,
    macd_hist,
    higher_close,
    higher_trend_ema,
    bb_pct=0.5,
    volume=1000.0,
    volume_ma=1000.0,
):
    return Snapshot(
        pair="ETH/USDT",
        timeframe="1h",
        as_of="2024-01-10 12:00:00",
        price=price,
        ma_fast=ma_fast,
        ma_slow=ma_slow,
        rsi=rsi,
        macd_dif=macd_dif,
        macd_dea=macd_dea,
        macd_hist=macd_hist,
        bb_upper=price + 50,
        bb_lower=price - 50,
        bb_pct=bb_pct,
        atr=10.0,
        volume=volume,
        volume_ma=volume_ma,
        higher_close=higher_close,
        higher_trend_ema=higher_trend_ema,
        recent_high=price + 20,
        recent_low=price - 20,
        recent_bars=[],
    )


def test_all_bullish_is_long():
    s = make_snapshot(
        price=110, ma_fast=105, ma_slow=100, rsi=60,
        macd_dif=2, macd_dea=1, macd_hist=1,
        higher_close=110, higher_trend_ema=100,
    )
    result = classify_bias(s)
    assert result.bias == BIAS_LONG
    assert result.score == 4


def test_all_bearish_is_short():
    s = make_snapshot(
        price=90, ma_fast=95, ma_slow=100, rsi=40,
        macd_dif=-2, macd_dea=-1, macd_hist=-1,
        higher_close=90, higher_trend_ema=100,
    )
    result = classify_bias(s)
    assert result.bias == BIAS_SHORT
    assert result.score == -4


def test_mixed_is_range():
    # 均线多头(+1) + 4h向下(-1) + MACD中性(0) + RSI偏弱(-1) = -1 -> 震荡
    s = make_snapshot(
        price=110, ma_fast=105, ma_slow=100, rsi=45,
        macd_dif=1, macd_dea=1, macd_hist=0,
        higher_close=90, higher_trend_ema=100,
    )
    result = classify_bias(s)
    assert result.bias == BIAS_RANGE


def test_overbought_rsi_flags_risk_and_no_direction_vote():
    s = make_snapshot(
        price=110, ma_fast=105, ma_slow=100, rsi=75,
        macd_dif=2, macd_dea=1, macd_hist=1,
        higher_close=110, higher_trend_ema=100,
    )
    result = classify_bias(s)
    rsi_vote = next(v for v in result.votes if v.name == "RSI")
    assert rsi_vote.score == 0
    assert any("超买" in r for r in result.risks)


def test_higher_trend_divergence_flags_risk():
    s = make_snapshot(
        price=110, ma_fast=105, ma_slow=100, rsi=60,
        macd_dif=2, macd_dea=1, macd_hist=1,
        higher_close=90, higher_trend_ema=100,
    )
    result = classify_bias(s)
    assert any("背离" in r for r in result.risks)


def test_missing_higher_ema_votes_zero():
    s = make_snapshot(
        price=110, ma_fast=105, ma_slow=100, rsi=60,
        macd_dif=2, macd_dea=1, macd_hist=1,
        higher_close=None, higher_trend_ema=None,
    )
    result = classify_bias(s)
    higher_vote = next(v for v in result.votes if v.name == "4h趋势")
    assert higher_vote.score == 0
