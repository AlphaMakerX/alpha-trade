# 项目目录结构

```text
alpha-trade/
├── config/              # 配置：settings.yaml（费率、滑点、风控）、logging.yaml
├── data/
│   ├── feeds/           # binance.py 拉取 + cleaner.py 清洗
│   └── storage/         # postgres.py 读写 / database.py 连接 / models.py 表定义
├── indicators/          # snapshot.py 指标快照 + bias.py 打分定方向
├── strategies/          # base.py 基类(含通用风控) + registry.py 注册表
│   ├── trend/           # ma_cross, trend_breakout, trend_holding_v3
│   ├── mean_revert/     # rsi_revert, bollinger_revert
│   └── composite/       # regime_switch
├── engine/              # 回测与信号的核心
├── analysis/            # data_quality 数据质量, bias_eval 倾向回测, report 报告
├── utils/               # config 配置加载, logger 日志
├── tests/               # 单元测试
└── main.py              # CLI 入口
```

## 各层职责

- **data/** — 从 Binance 拉 OHLCV（1m/5m/15m/1h/4h/1d），增量拉取 + 缺口回补，清洗去重后存 PostgreSQL。
- **indicators/** — `snapshot.py` 在全量序列上算 MA/RSI/MACD/布林/ATR 等并取最后一根；`bias.py` 按固定规则给指标投票，得出偏多/偏空/震荡。
- **strategies/** — 所有策略继承 `base.py`，复用通用风控（按止损距离定仓、ATR 跟踪止损、冷却、时间止损、最大回撤熔断），只负责产信号。`registry.py` 统一注册。
- **engine/** — `backtest` 回测、`evaluation` 分段+成本压力、`search` 候选搜索、`factory` 注入风控参数、`params` 参数解析、`data` 加载、`signal` 实盘信号、`analyst` LLM 看盘。
- **analysis/** — `data_quality` 检查缺失/重复/异常；`bias_eval` 回测 bias 方向预测力；`report` 生成报告。

## 产物目录

回测/评估/搜索报告写到 `artifacts/`；看盘报告写到 `reports/`。
