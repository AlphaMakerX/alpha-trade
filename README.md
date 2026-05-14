# Alpha Trade

Alpha Trade 的目标是找到一个长期大概率能赚钱、风险可控、可以接入实盘信号的交易策略。

当前项目重点不是直接下单，而是把策略从想法验证到实盘准入的流程跑顺：

```text
拉取数据 -> 写策略 -> 回测 -> 稳定性评估 -> 参数优化 -> 样本外验证 -> 实盘信号
```

## 当前状态

当前主候选策略是 `regime_switch`：

- 趋势行情：走 Donchian 突破逻辑。
- 震荡行情：走 Bollinger + RSI 均值回归逻辑。
- 同一时间只允许一个持仓。
- 统一使用通用风控：仓位控制、冷却期、时间止损、ATR 跟踪止损、最大回撤熔断。

最新评估区间：

```text
策略: regime_switch
交易对: ETH/USDT
周期: 1h
区间: 2024-01-01 ~ 2025-01-01
```

| 指标 | 结果 |
| --- | ---: |
| Return | 6.05% |
| Buy & Hold | 45.86% |
| Sharpe | 0.76 |
| Max Drawdown | -4.07% |
| Trades | 45 |
| Profit Factor | 1.34 |

结论：`regime_switch` 有初步盈利能力，但高成本场景下边际偏薄，还不能直接实盘。下一步需要做 walk-forward、参数稳定性、多资产和多周期验证。

注意：`main.py signal` 目前还没有切到 `regime_switch`，实盘信号仍偏旧的 `MaCross` 逻辑。

## 项目结构

```text
config/        配置文件
data/          Binance 数据拉取和 PostgreSQL 存储
strategies/    策略代码
engine/        回测、优化、walk-forward、稳定性评估
analysis/      数据质量检查和报告生成
tests/         单元测试
docs/          架构、流程和优化计划
artifacts/     回测和评估报告输出
```

## 快速开始

安装依赖：

```bash
pip install -e .
```

如果没有本地配置文件，先复制模板：

```bash
cp config/settings.example.yaml config/settings.yaml
```

初始化数据库：

```bash
.venv/bin/python main.py initdb
```

拉取历史 K线：

```bash
.venv/bin/python main.py fetch -p ETH/USDT -t 1h -s 2024-01-01 -e 2025-01-01
```

运行测试：

```bash
.venv/bin/python -m pytest
```

## 常用命令

单次回测：

```bash
.venv/bin/python main.py backtest -s regime_switch -t 1h --start 2024-01-01 --end 2025-01-01
```

稳定性评估：

```bash
.venv/bin/python main.py evaluate -s regime_switch -t 1h --start 2024-01-01 --end 2025-01-01
```

参数优化：

```bash
.venv/bin/python main.py optimize -s regime_switch -t 1h --start 2024-01-01 --end 2025-01-01
```

Walk-forward：

```bash
.venv/bin/python main.py walkforward -s regime_switch -t 1h --start 2023-01-01 --end 2026-01-01 --train-months 12 --test-months 6
```

查看当前信号：

```bash
.venv/bin/python main.py signal -p ETH/USDT -t 1h
```

## 如何判断策略能不能实盘

一个策略至少要满足：

- 数据质量 OK，缺失 K线为 0。
- 交易次数足够，至少 30 笔；低频策略要单独说明。
- Profit Factor > 1。
- Sharpe 为正。
- 最大回撤可接受。
- 不只靠一个季度赚钱。
- 高成本压力测试后不能明显失效。
- Walk-forward 样本外不能持续亏损。
- 多资产、多周期不能全部失效。
- 实盘信号和回测信号在同一根历史 K线上一致。

不满足这些条件，只能继续研究，不能接入实盘。

## 报告输出

单次回测报告：

```text
artifacts/backtests/
```

稳定性评估报告：

```text
artifacts/evaluations/
```

## 文档

- [策略开发与实盘使用流程](docs/architecture.md)
- [优化计划 v2](docs/develop/plan-2.md)
- [目录结构](docs/project-structure.md)
