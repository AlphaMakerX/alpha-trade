# 高年化候选搜索记录

日期：2026-05-14

## 目的

本次搜索目标是尽可能在现有策略库中找到高年化候选，但不直接接入实盘信号。搜索结果只用于研究和后续验证。

重点判断口径：

- 先看样本外表现，不看单次全区间收益。
- 高年化候选必须同时关注最大回撤、交易次数、Profit Factor 和 Sharpe。
- 交易次数太少的结果不能视为有效候选。
- 训练段差、样本外好的参数要额外警惕，可能只是近期行情适配。

## 数据范围

| 项目 | 值 |
| --- | --- |
| Pair | `ETH/USDT` |
| Timeframe | `1h` |
| Requested range | `2023-01-01 ~ 2026-05-14` |
| Actual range | `2023-01-01 00:00:00+00:00 ~ 2026-05-13 01:00:00+00:00` |
| Train range | `2023-01-01 00:00:00+00:00 ~ 2025-07-10 00:00:00+00:00` |
| Out-of-sample range | `2025-07-10 01:00:00+00:00 ~ 2026-05-13 01:00:00+00:00` |
| Rows | `29473` |
| Data quality | `WARN` |

数据质量警告：

- 缺失 `1` 根 `1h` K线。
- `1` 行非正成交量。
- 本地末根 K线早于请求结束时间。

这些问题不影响本次粗筛结论，但任何候选进入最终验证前必须先补齐并复查数据。

## 搜索命令

第一轮全策略搜索：

```bash
.venv/bin/python main.py search -s all -t 1h \
  --start 2023-01-01 --end 2026-05-14 \
  --top 50 \
  --oos-ratio 0.25 \
  --min-train-trades 30 \
  --min-test-trades 8 \
  --max-drawdown 35 \
  --min-profit-factor 1.05 \
  --min-sharpe 0.2
```

随后对主要策略分别做全参数样本外复测：

```bash
.venv/bin/python main.py search -s ma_cross -t 1h \
  --start 2023-01-01 --end 2026-05-14 \
  --top 200 \
  --oos-ratio 0.25 \
  --min-train-trades 10 \
  --min-test-trades 5 \
  --max-drawdown 40 \
  --min-profit-factor 1.0 \
  --min-sharpe 0.0
```

同样口径复测：

- `regime_switch`
- `trend_breakout`
- `bollinger_revert`
- `rsi_revert`

## 主要结论

现有策略库没有找到“非常高年化且样本外稳”的候选。

当前最好的候选来自 `ma_cross`，样本外年化约 `11.80%`，但训练段为负，说明它更像近期行情适配，不应直接作为实盘参数。

| Rank | Strategy | OOS Ann. Return | OOS Return | Sharpe | Max DD | Trades | Profit Factor | Params |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `ma_cross` | `11.80%` | `9.87%` | `0.86` | `-7.00%` | 50 | 1.25 | `fast=40, slow=50, trend=200, atr=20, atr_mult=1.5` |
| 2 | `ma_cross` | `9.90%` | `8.29%` | `0.80` | `-7.60%` | 50 | 1.26 | `fast=40, slow=50, trend=200, atr=12, atr_mult=1.5` |
| 3 | `ma_cross` | `9.89%` | `8.28%` | `0.92` | `-4.42%` | 48 | 1.25 | `fast=40, slow=50, trend=200, atr=20, atr_mult=2.0` |
| 4 | `ma_cross` | `9.81%` | `8.21%` | `0.79` | `-7.58%` | 50 | 1.27 | `fast=40, slow=50, trend=200, atr=16, atr_mult=1.5` |
| 5 | `ma_cross` | `9.74%` | `8.16%` | `1.02` | `-4.39%` | 47 | 1.28 | `fast=40, slow=50, trend=200, atr=12, atr_mult=2.0` |

策略级最好结果：

| Strategy | Best OOS Ann. Return | Sharpe | Max DD | Trades | Profit Factor | Assessment |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `ma_cross` | `11.80%` | `0.86` | `-7.00%` | 50 | 1.25 | 当前唯一值得继续验证的高年化候选，但训练段亏损 |
| `trend_breakout` | `5.25%` | `0.51` | `-6.83%` | 54 | 1.34 | 收益偏低，暂不作为高年化主线 |
| `regime_switch` | `3.47%` | `0.45` | `-5.44%` | 39 | 1.12 | 更偏低回撤，不适合当前高年化目标 |
| `bollinger_revert` | `2.10%` | `0.62` | `-1.04%` | 5 | 1.40 | 交易太少，只能作为补充观察 |
| `rsi_revert` | 无有效候选 | - | - | - | - | 样本外基本 0 到 1 笔交易 |

## 风险判断

`ma_cross` 最优候选存在明显稳定性风险：

- 第一名训练段年化约 `-9.68%`，训练段 Sharpe 约 `-1.45`。
- 训练段差、样本外好，说明参数可能只是适配 2025-07 之后行情。
- `fast=40, slow=50` 的快慢线距离很近，容易在震荡市频繁交易。
- 现有数据只覆盖 `ETH/USDT 1h`，没有多资产、多周期验证。

因此，本次搜索结果不能直接用于实盘，只能作为后续验证候选。

## 结果文件

| Run | Summary CSV |
| --- | --- |
| All strategies | `artifacts/searches/20260514-153136_all_ETH-USDT_1h_2023-01-01_2026-05-14_summary.csv` |
| `ma_cross` | `artifacts/searches/20260514-153434_ma_cross_ETH-USDT_1h_2023-01-01_2026-05-14_summary.csv` |
| `regime_switch` | `artifacts/searches/20260514-155049_regime_switch_ETH-USDT_1h_2023-01-01_2026-05-14_summary.csv` |
| `trend_breakout` | `artifacts/searches/20260514-155431_trend_breakout_ETH-USDT_1h_2023-01-01_2026-05-14_summary.csv` |
| `bollinger_revert` | `artifacts/searches/20260514-155729_bollinger_revert_ETH-USDT_1h_2023-01-01_2026-05-14_summary.csv` |
| `rsi_revert` | `artifacts/searches/20260514-160025_rsi_revert_ETH-USDT_1h_2023-01-01_2026-05-14_summary.csv` |

## 下一步

1. 补齐 `ETH/USDT 1h` 数据缺口，并重新确认数据质量为 OK。
2. 给 `search` 增加样本外复测进度日志，避免长时间无输出。
3. 支持将候选参数传入 `evaluate` 和 `walkforward`，不要只评估策略默认参数。
4. 对前 3 个 `ma_cross` 候选做 walk-forward：
   - `train-months=12`
   - `test-months=3`
   - 观察每个窗口是否持续有效。
5. 如果 walk-forward 不稳定，停止继续扩大现有参数网格，转向新策略开发：
   - 更激进的趋势持仓策略。
   - 突破后加仓或 pyramiding。
   - ATR/波动率分位数过滤。
   - 多资产轮动。
   - 高周期趋势确认。


