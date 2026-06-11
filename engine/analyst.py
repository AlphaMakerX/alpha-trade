import pandas as pd
from loguru import logger
from openai import OpenAI

from data.storage.postgres import query_klines
from engine.data import HIGHER_TIMEFRAME
from indicators.bias import BiasResult, classify_bias
from indicators.snapshot import MA_SLOW_PERIOD, Snapshot, compute_snapshot
from utils.config import get_settings

MIN_BASE_BARS = MA_SLOW_PERIOD + 5

_SYSTEM_PROMPT = (
    "你是一名加密货币行情解读助手。你的唯一职责是把已经算好的技术指标和"
    "“倾向结论”用简洁的中文解释清楚——为什么是这个倾向、关键支撑/压力位在哪、"
    "有哪些风险。\n"
    "硬性规则：\n"
    "1. 倾向（偏多/偏空/震荡）由系统规则算出，你绝对不能修改或推翻它，只能解释它。\n"
    "2. 这是对当前现状的描述，不是对未来价格的预测。不要给出买卖指令或目标价。\n"
    "3. 只依据提供的指标数据，不要编造未提供的信息。\n"
    "4. 输出控制在 200 字以内，分点说明。"
)


def _llm_config() -> dict:
    cfg = get_settings().get("llm")
    if not cfg:
        raise RuntimeError("缺少 llm 配置段，请在 config/settings.yaml 添加 llm")

    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "")
    base_url = cfg.get("base_url", "")
    if not api_key or "${" in api_key:
        raise RuntimeError("LLM api_key 未配置，请在 .env 设置 OPENAI_API_KEY")
    if not model or "${" in model:
        raise RuntimeError("LLM model 未配置，请在 .env 设置 LLM_MODEL（gateway 实际模型名）")
    if not base_url or "${" in base_url:
        raise RuntimeError("LLM base_url 未配置")
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "temperature": float(cfg.get("temperature", 0.3)),
    }


def _format_votes(bias: BiasResult) -> str:
    lines = [f"  倾向: {bias.bias}（打分 {bias.score:+d}）", "  打分明细:"]
    for v in bias.votes:
        lines.append(f"    [{v.score:+d}] {v.name}: {v.reason}")
    if bias.risks:
        lines.append("  风险提示:")
        lines.extend(f"    ⚠ {r}" for r in bias.risks)
    else:
        lines.append("  风险提示: 无")
    return "\n".join(lines)


def _build_user_prompt(s: Snapshot, bias: BiasResult) -> str:
    recent = "\n".join(
        f"  {b.open_time} O{b.open:.2f} H{b.high:.2f} L{b.low:.2f} C{b.close:.2f} V{b.volume:.0f}"
        for b in s.recent_bars
    )
    higher = (
        f"4h收盘={s.higher_close:.2f} 4h-EMA200={s.higher_trend_ema:.2f}"
        if s.higher_trend_ema is not None
        else "4h趋势数据不足"
    )
    return (
        f"交易对 {s.pair} {s.timeframe}，截至 {s.as_of}\n"
        f"现价={s.price:.2f}\n"
        f"MA20={s.ma_fast:.2f} MA50={s.ma_slow:.2f}\n"
        f"RSI(14)={s.rsi:.1f}\n"
        f"MACD: DIF={s.macd_dif:.2f} DEA={s.macd_dea:.2f} 柱={s.macd_hist:.2f}\n"
        f"布林: 上轨={s.bb_upper:.2f} 下轨={s.bb_lower:.2f} 位置={s.bb_pct:.0%}\n"
        f"ATR(14)={s.atr:.2f}\n"
        f"成交量={s.volume:.0f} 均量(20)={s.volume_ma:.0f}\n"
        f"近{len(s.recent_bars)}根区间: 高={s.recent_high:.2f} 低={s.recent_low:.2f}\n"
        f"{higher}\n"
        f"系统已判定倾向: {bias.bias}（打分 {bias.score:+d}）\n"
        f"风险标记: {('；'.join(bias.risks)) or '无'}\n\n"
        f"近期K线:\n{recent}"
    )


def _ask_llm(s: Snapshot, bias: BiasResult) -> str:
    cfg = _llm_config()
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    logger.info(f"调用 LLM 解读 ({cfg['model']})...")
    resp = client.chat.completions.create(
        model=cfg["model"],
        temperature=cfg["temperature"],
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(s, bias)},
        ],
    )
    return resp.choices[0].message.content.strip()


def analyze(pair: str, timeframe: str) -> str:
    """读 DB 行情 → 算指标快照 → 规则定倾向 → LLM 解读，返回可打印文本。"""
    base_df = query_klines(pair, timeframe)
    if len(base_df) < MIN_BASE_BARS:
        raise RuntimeError(
            f"{pair} {timeframe} 数据不足（需 {MIN_BASE_BARS} 根，实际 {len(base_df)}），请先 fetch"
        )
    higher_df = query_klines(pair, HIGHER_TIMEFRAME)

    snapshot = compute_snapshot(base_df, higher_df, pair, timeframe)
    bias = classify_bias(snapshot)
    explanation = _ask_llm(snapshot, bias)

    return "\n".join(
        [
            f"\n{'=' * 44}",
            f"  {pair} {timeframe} 看盘解读",
            f"  时间: {snapshot.as_of}",
            f"{'=' * 44}",
            _format_votes(bias),
            f"{'-' * 44}",
            "  AI 解读（仅描述现状，非买卖建议）:",
            explanation,
            f"{'=' * 44}\n",
        ]
    )
