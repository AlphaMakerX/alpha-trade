# Week 1 任务

> 总结见 `summary.md`。

## 项目骨架
- [x] 目录结构、`pyproject.toml` 依赖
- [x] `config/settings.yaml` 配置、日志模块
- [x] `main.py` 命令行入口

## 数据层
- [x] Binance 拉取 OHLCV，支持 1m/5m/15m/1h/4h/1d
- [x] 增量拉取 + 历史缺口回补 + 限频重试
- [x] `upsert` 防重复
- [x] 数据清洗（去重、缺失、异常值）
- [x] PostgreSQL 存储（SQLAlchemy Core，TIMESTAMPTZ）
- [x] 数据质量检查（缺失/重复/异常价格/时区一致性）

## 策略
- [x] `ma_cross`（双均线交叉）
- [x] `rsi_revert`（RSI 均值回归）
- [x] `trend_breakout`（Donchian 突破 + ADX/成交量过滤）
- [x] `bollinger_revert`（布林带均值回归，仅震荡态）
- [x] `regime_switch`（按市场状态切换趋势/回归）
- [x] `trend_holding_v3`（趋势右尾持仓，当前主线）

## 回测与评估
- [x] 集成 Backtesting.py，统一回测口径（`finalize_trades`、commission、slippage）
- [x] `backtest` / `evaluate` / `search` / `walkforward` 命令（`--param` / `--pair`）
- [x] 全区间、年度、季度、成本压力测试报告（Markdown/CSV）
- [x] 通用风控基类（按止损距离定仓、ATR 跟踪止损、连亏冷却、时间止损、最大回撤熔断）
- [x] 扩展 BTC/ETH/SOL/BNB 的 1h/4h 数据，启动多资产基线

## 下一步
- [ ] 多资产、多周期完整验证矩阵
- [ ] 参数邻域稳定性验证
- [ ] 实盘信号一致性：`signal` 接入已验证参数与已闭合 K 线
