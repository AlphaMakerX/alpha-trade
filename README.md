# Alpha Trade

以太坊 USDT 量化交易系统 — 策略开发与回测验证。

## 核心流程

```
数据采集 → 因子计算 → 策略信号 → 回测撮合 → 绩效分析
```

## 项目结构

```
config/        配置文件
data/          数据采集与存储
indicators/    技术 / 链上 / 情绪因子
strategies/    交易策略
engine/        回测引擎
analysis/      绩效分析与可视化
notebooks/     研究探索
tests/         单元测试
```

## 快速开始

```bash
pip install -e .
python main.py
```

## 文档

- [系统架构](docs/architecture.md)
- [目录结构](docs/project-structure.md)