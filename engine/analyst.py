from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from openai import OpenAI

from data.storage.postgres import query_klines
from engine.data import HIGHER_TIMEFRAME, parse_utc_date
from indicators.bias import BiasResult, classify_bias
from indicators.snapshot import MA_SLOW_PERIOD, Snapshot, compute_snapshot
from utils.config import get_settings

MIN_BASE_BARS = MA_SLOW_PERIOD + 5
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

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


def _resolve_end(date: str | None) -> datetime | None:
    """把 YYYY-MM-DD 解析为当天 UTC 23:59:59，作为查询上界；None 表示最新。"""
    if date is None:
        return None
    return parse_utc_date(date) + timedelta(hours=23, minutes=59, seconds=59)


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


def _ask_llm(s: Snapshot, bias: BiasResult, cfg: dict) -> str:
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


def _render_markdown(s: Snapshot, bias: BiasResult, model: str, explanation: str) -> str:
    higher = (
        f"{s.higher_close:.2f}（EMA200 {s.higher_trend_ema:.2f}）"
        if s.higher_trend_ema is not None
        else "数据不足"
    )
    vote_rows = "\n".join(
        f"| {v.name} | {v.score:+d} | {v.reason} |" for v in bias.votes
    )
    risks = (
        "\n".join(f"- ⚠ {r}" for r in bias.risks) if bias.risks else "- 无"
    )
    return f"""# {s.pair} {s.timeframe} 看盘解读

- **数据截至**: {s.as_of}
- **模型**: {model}

## 倾向：{bias.bias}（打分 {bias.score:+d}）

| 指标 | 投票 | 说明 |
|---|---|---|
{vote_rows}

## 关键指标

| 项目 | 值 |
|---|---|
| 现价 | {s.price:.2f} |
| MA20 / MA50 | {s.ma_fast:.2f} / {s.ma_slow:.2f} |
| RSI(14) | {s.rsi:.1f} |
| MACD DIF/DEA/柱 | {s.macd_dif:.2f} / {s.macd_dea:.2f} / {s.macd_hist:.2f} |
| 布林上轨/下轨/位置 | {s.bb_upper:.2f} / {s.bb_lower:.2f} / {s.bb_pct:.0%} |
| ATR(14) | {s.atr:.2f} |
| 成交量 / 均量(20) | {s.volume:.0f} / {s.volume_ma:.0f} |
| 近{len(s.recent_bars)}根 高/低 | {s.recent_high:.2f} / {s.recent_low:.2f} |
| 4h 收盘 | {higher} |

## 风险提示

{risks}

## AI 解读（仅描述现状，非买卖建议）

{explanation}
"""


def _save_report(markdown: str, s: Snapshot) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = s.as_of[:13].replace(" ", "_").replace(":", "")
    filename = f"{s.pair.replace('/', '-')}_{s.timeframe}_{stamp}.md"
    path = REPORTS_DIR / filename
    path.write_text(markdown, encoding="utf-8")
    logger.info(f"报告已保存: {path}")
    return path


def analyze(pair: str, timeframe: str, end: str | None) -> str:
    """读 DB 行情 → 算指标 → 规则定倾向 → LLM 解读 → 存 md，返回 markdown 报告。

    end 为 YYYY-MM-DD，分析将站在该日当天结束;None 表示用最新数据。
    """
    end_dt = _resolve_end(end)
    base_df = query_klines(pair, timeframe, end=end_dt)
    if len(base_df) < MIN_BASE_BARS:
        raise RuntimeError(
            f"{pair} {timeframe} 数据不足（需 {MIN_BASE_BARS} 根，实际 {len(base_df)}），请先 fetch"
        )
    higher_df = query_klines(pair, HIGHER_TIMEFRAME, end=end_dt)

    snapshot = compute_snapshot(base_df, higher_df, pair, timeframe)
    bias = classify_bias(snapshot)
    cfg = _llm_config()
    explanation = _ask_llm(snapshot, bias, cfg)

    markdown = _render_markdown(snapshot, bias, cfg["model"], explanation)
    _save_report(markdown, snapshot)
    return markdown
