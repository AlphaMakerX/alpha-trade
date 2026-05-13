# Alpha Trade - 开发计划

## 概述

基于以太坊 USDT 量化交易系统架构，按 **数据层 → 策略层 → 回测层 → 优化层** 的顺序分阶段推进开发。

---

## Phase 1：项目基础搭建（第 1 周）

### 目标
搭建项目骨架，完成基础配置与开发环境。

### 任务清单
- [x] 初始化项目目录结构（data / strategies / backtest / config 等）
- [x] 编写 `pyproject.toml`，安装核心依赖（ccxt, pandas, numpy, ta, backtesting, psycopg2-binary, loguru, click）
- [x] 创建 `config/settings.yaml` 全局配置模板（交易所 API Key、数据库连接等）
- [x] 搭建日志模块（统一日志格式与级别管理）
- [x] 编写 `main.py` 程序入口，支持命令行参数

---

## Phase 2：数据采集与存储（第 2-3 周）

### 目标
完成 ETH/USDT K线数据的采集、清洗与持久化存储。

### 任务清单
- [x] 实现 `data/feeds/binance.py`，通过 Binance REST API 拉取 ETH/USDT OHLCV 数据（含 close_time、quote_asset_volume、number_of_trades、taker_buy 等完整字段）
- [x] 支持多时间粒度（1m / 5m / 15m / 1h / 4h / 1d）
- [x] 实现增量拉取逻辑，避免重复请求，处理 API 限频与重试
- [x] 实现 `data/feeds/cleaner.py`，完成去重、缺失值填充、异常值检测
- [x] 搭建 PostgreSQL 数据库，使用 SQLAlchemy Core 定义 K线数据表结构（支持多交易对、多时间粒度，open_time/close_time 使用 TIMESTAMPTZ）
- [x] 实现数据入库逻辑（ON CONFLICT DO NOTHING 防重复）
- [x] 编写数据采集的单元测试
- [ ] 支持多交易对批量拉取（当前仅支持单交易对 CLI 调用）

---

## Phase 3：策略开发（第 4-5 周）

### 目标
实现策略基类和第一个可运行的趋势跟踪策略。

### 任务清单
- [x] 实现 `strategies/base.py` 策略基类（继承 Backtesting.py Strategy）
- [x] 实现 `strategies/trend/ma_cross.py` 双均线交叉策略
- [x] 实现基础技术指标计算（使用 `ta` 库：SMA）
- [x] 策略信号输出标准化（通过 Backtesting.py 的 buy/position.close 驱动）
- [x] 编写策略的单元测试

---

## Phase 4：回测验证（第 6-7 周）

### 目标
基于 Backtesting.py 框架对策略进行历史数据验证。

### 任务清单
- [x] 集成 Backtesting.py 框架，封装统一的回测入口（`main.py backtest` 命令）
- [x] 将策略适配为 Backtesting.py 的 Strategy 子类
- [x] 配置回测参数（初始资金、手续费，从 settings.yaml 读取）
- [x] 从 PostgreSQL 读取历史数据，转换为回测所需格式
- [x] 使用历史数据对 MA 交叉策略完成首次回测验证
- [ ] 利用框架内置功能生成绩效报告与可视化图表

---

## Phase 5：策略迭代与优化（第 8 周+）

### 目标
基于回测结果优化策略，引入参数调优机制。

### 任务清单
- [x] 分析首次回测结果，识别策略弱点（交易过频、假信号多、无止损）
- [x] 实现网格搜索参数优化（`engine/backtest.py` 的 `run_optimize()`，基于 `Backtest.optimize()`）
- [x] 实现 Walk-Forward 分析，防止过拟合（`engine/backtest.py` 的 `run_walk_forward()`）
- [x] 实现动态止损（ATR 动态止损，替代固定比例止损）
- [ ] 新增第二个策略（如 RSI 均值回归），与 MA 交叉策略对比绩效
- [x] 样本外测试（2023-2024 vs 2025-2026 分段回测验证）

---

## 优先级说明

| 优先级 | 模块 | 原因 |
|-------|------|------|
| P0 | 数据采集 + 存储 | 一切策略的基础，没有数据无法进行任何后续工作 |
| P0 | 策略基类 + MA 交叉 | 最小可验证策略，快速跑通全流程 |
| P1 | 回测引擎 | 验证策略有效性的核心工具 |
| P2 | 参数优化 + 风控 | 在基础功能稳定后再引入 |
| P3 | 机器学习策略 | 高级功能，待基础框架成熟后探索 |

---

## 技术约定

- **Python 版本**：3.11+
- **代码规范**：PEP 8，使用 black 格式化
- **测试框架**：pytest
- **分支策略**：main（稳定）/ develop（开发）/ feature/*（功能分支）
- **数据存储**：PostgreSQL
- **回测框架**：Backtesting.py
