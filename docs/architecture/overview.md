# 架构总览

ETH/USDT 量化回测系统。一条主线：

```text
拉数据 → 写策略 → 回测 → 评估稳定性 → 优化参数 → 样本外验证 → 接入实盘信号
```

## 分层

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 数据 | `data/` | 从 Binance 拉 K 线，清洗后存 PostgreSQL；查缺失/重复/异常 |
| 指标 | `indicators/` | 把 K 线压成指标快照，按规则打分定方向（看盘用） |
| 策略 | `strategies/` | 继承 `base.py`（含通用风控），只产信号 |
| 引擎 | `engine/` | 回测、评估、优化、搜索、实盘信号、LLM 看盘 |
| 分析 | `analysis/` | 数据质量检查、bias 回测、报告生成 |

## 数据流

```text
Binance API → data/feeds → data/storage(PostgreSQL)
                                  │
                          ┌───────┴───────┐
                          ▼               ▼
                    indicators/       strategies/
                    (看盘打分)         (交易信号)
                          │               │
                          ▼               ▼
                      engine/analyst   engine/backtest
                      (LLM 解读)        (回测撮合)
                                          │
                                          ▼
                                      analysis/(评估报告)
```

## 文档索引

| 文档 | 内容 |
| --- | --- |
| `project-structure.md` | 真实目录结构与模块职责 |
| `daily-advice.md` | **怎么跑脚本给出今天的投资建议**（fetch → analyze → signal） |
| `workflow.md` | 策略开发到实盘的完整流程 + 评估命令 |
| `strategy-status.md` | 各策略最新验证结论 + 实盘准入标准 |
