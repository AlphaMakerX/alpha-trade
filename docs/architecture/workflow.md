# 策略开发与实盘流程

目标：找到一个长期大概率赚钱、风险可控、可实盘的策略。一条主线：

```text
拉数据 → 写策略 → 回测 → 评估稳定性 → 优化参数 → 样本外验证 → 接入实盘信号
```

不要只追求某次回测收益高。能实盘的策略必须证明它不是因为数据缺失、参数过拟合、成本低估或某个特殊行情窗口才赚钱。

> 各策略最新结论与实盘准入标准见 `strategy-status.md`；研究方法论见 `../concept/strategy-research.md`。

## 正确顺序

```text
默认参数回测 → 分段评估(年度/季度) → 成本压力测试
→ 参数优化 → walk-forward → 多资产/多周期验证 → 实盘信号
```

不要一上来就跑大网格优化，那样很容易找到只适合历史数据的参数。

## 两条铁律

1. **先确认数据完整**：回测前查缺失/重复/时区(UTC)/异常 OHLC/非正成交量，有问题不能静默进入结论。
2. **策略必须带风控**：复用 `BaseStrategy` 的通用风控（按止损距离定仓、`risk_per_trade`、`max_position_pct`、冷却期、时间止损、ATR 跟踪止损、最大回撤熔断），不要每个策略重写一套。

## 命令速查

| 命令 | 用途 | 产物 |
| --- | --- | --- |
| `fetch` | 拉取 K 线入库（增量 + 缺口回补） | — |
| `backtest` | 单次回测，快速看某段表现 | `artifacts/backtests/` |
| `evaluate` | 全区间 + 年度/季度 + 成本压力测试 | `artifacts/evaluations/` |
| `optimize` | 网格搜索参数（仅候选，不能直接上线） | — |
| `walkforward` | 样本外验证，识别过拟合 | — |
| `search` | 候选粗筛（训练段遍历 + 尾部样本外复测） | `artifacts/searches/` |
| `best-signal` | 用最优策略 trend_holding_v3 判断当前买卖点（实时、只看闭合 K 线） | — |
| `signal` | ma_cross 旧基线买卖信号（对照） | — |
| `analyze` | 规则定倾向 + 策略买卖点 + LLM 看盘解读 | `reports/` |

示例：

```bash
.venv/bin/python main.py evaluate -s trend_holding_v3 -t 1h --start 2023-01-01 --end 2026-01-01
.venv/bin/python main.py walkforward -s trend_holding_v3 -t 1h --start 2023-01-01 --end 2026-01-01 --train-months 12 --test-months 6
```

## 看回测看哪些指标

Return / Buy & Hold / Cash Benchmark(空仓固定 0%) / Sharpe / Max Drawdown / Trades / Win Rate / Profit Factor / Commissions，外加数据质量（缺失、重复、异常 K 线）。

成本压力测试覆盖 `commission` 与 `slippage` 各 0.05% / 0.10% / 0.20%。
