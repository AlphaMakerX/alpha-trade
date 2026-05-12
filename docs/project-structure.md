# Alpha Trade - 项目目录结构

## 目录总览

```
alpha-trade/
├── config/                     # 配置文件
│   ├── settings.yaml           # 全局配置（交易所 API、费率、滑点等）
│   ├── logging.yaml            # 日志配置
│   └── pairs.yaml              # 交易对配置（ETH/USDT 等）
│
├── data/                       # 数据层
│   ├── feeds/                  # 数据源接口
│   │   ├── base.py             # 数据源基类
│   │   ├── binance.py          # Binance API 数据源
│   │   ├── okx.py              # OKX API 数据源
│   │   ├── csv_feed.py         # CSV 文件数据源
│   │   └── onchain.py          # 链上数据（Etherscan / Alchemy）
│   ├── storage/                # 数据存储
│   │   ├── postgres.py         # PostgreSQL 历史数据存储
│   │   ├── redis_cache.py      # Redis 实时数据缓存
│   │   └── models.py           # 数据模型（ORM）
│   └── sample/                 # 示例数据（用于开发和测试）
│       └── eth_usdt_1h.csv
│
├── strategies/                 # 策略层
│   ├── base.py                 # 策略基类（定义 on_bar / on_tick 接口）
│   ├── trend/                  # 趋势跟踪策略
│   │   ├── ma_cross.py         # 均线交叉策略
│   │   ├── macd_trend.py       # MACD 趋势策略
│   │   └── bollinger_break.py  # 布林带突破策略
│   ├── mean_revert/            # 均值回归策略
│   │   ├── rsi_revert.py       # RSI 超买超卖策略
│   │   └── bollinger_revert.py # 布林带回归策略
│   ├── momentum/               # 动量策略
│   │   └── volume_break.py     # 成交量突破策略
│   └── ml/                     # 机器学习策略
│       └── lstm_predict.py     # LSTM 预测策略
│
├── indicators/                 # 技术指标 & 因子
│   ├── technical.py            # 技术因子（MA, EMA, RSI, MACD, ATR, 布林带）
│   ├── onchain.py              # 链上因子（活跃地址、Gas 费、大额转账）
│   ├── sentiment.py            # 情绪因子（恐惧贪婪指数、社交提及量）
│   └── composite.py            # 多因子合成（加权打分、归一化、阈值过滤）
│
├── engine/                     # 回测引擎
│   ├── backtest.py             # 回测主循环（逐 Bar 回放）
│   ├── broker.py               # 模拟经纪商（撮合、滑点模拟）
│   ├── portfolio.py            # 持仓管理 & 资金管理
│   ├── order.py                # 订单模型（限价、市价、止损）
│   └── risk.py                 # 风控模块（仓位限制、最大回撤熔断）
│
├── analysis/                   # 绩效分析
│   ├── metrics.py              # 绩效指标（年化收益、夏普、最大回撤、胜率、盈亏比）
│   ├── report.py               # 报告生成（HTML / PDF）
│   ├── plot.py                 # 可视化（K线 + 信号标注、资金曲线、回撤图）
│   └── validation.py           # 防过拟合验证（Walk-Forward、交叉验证、参数稳健性）
│
├── utils/                      # 工具函数
│   ├── logger.py               # 日志工具
│   ├── time_utils.py           # 时间处理
│   └── math_utils.py           # 数学工具
│
├── notebooks/                  # Jupyter Notebooks（研究探索）
│   ├── data_explore.ipynb      # 数据探索
│   └── strategy_research.ipynb # 策略研究
│
├── tests/                      # 单元测试
│   ├── test_engine.py          # 回测引擎测试
│   ├── test_strategies.py      # 策略测试
│   ├── test_indicators.py      # 指标计算测试
│   └── test_data_feeds.py      # 数据源测试
│
├── docs/                       # 文档
│   ├── architecture.md         # 系统架构
│   └── project-structure.md    # 目录结构（本文件）
│
├── main.py                     # 入口：运行回测
├── pyproject.toml              # 项目依赖与元数据
├── .gitignore
├── LICENSE
└── README.md
```

## 模块职责

### data/ — 数据层

负责从交易所 API、链上数据源获取数据，经清洗后存入 PostgreSQL（历史）和 Redis（实时）。数据源通过基类抽象，方便扩展新交易所。

支持粒度：1m / 5m / 15m / 1h / 4h / 1d

### strategies/ — 策略层

所有策略继承 `base.py` 基类，实现统一接口：
- `on_bar(bar)` — 每根 K 线触发
- `generate_signal()` — 生成买卖信号

策略按类型分子目录，只关心信号生成，不关心撮合执行。

### indicators/ — 因子体系

独立于策略的因子计算模块，可被多个策略复用：
- 技术因子：MA, EMA, RSI, MACD, ATR, 布林带
- 链上因子：活跃地址数、Gas 费变化率、大额转账频率
- 情绪因子：恐惧贪婪指数、社交媒体提及量
- 合成：多因子加权打分 → 归一化 → 阈值过滤

### engine/ — 回测引擎

核心回测循环：`加载历史数据 → 逐 Bar 回放 → 策略生成信号 → 风控检查 → 模拟撮合 → 记录交易`

- `broker.py` 模拟真实交易环境（手续费、滑点）
- `risk.py` 执行风控规则（仓位限制、回撤熔断）

### analysis/ — 绩效分析

回测完成后统一分析：

| 指标 | 参考基准 |
|------|---------|
| 年化收益率 | > 买入持有 |
| 夏普比率 | > 1.5 |
| 最大回撤 | < 20% |
| 胜率 | > 50% |
| 盈亏比 | > 1.5 |

`validation.py` 提供防过拟合检验（Walk-Forward、多交易对交叉验证）。

## 数据流

```
交易所 API / 链上数据
        │
        ▼
   data/feeds/          ← 数据采集
        │
        ▼
   data/storage/        ← 清洗 & 存储
        │
        ▼
   indicators/          ← 因子计算
        │
        ▼
   strategies/          ← 信号生成
        │
        ▼
   engine/              ← 回测撮合
        │
        ▼
   analysis/            ← 绩效评估 & 可视化
```
