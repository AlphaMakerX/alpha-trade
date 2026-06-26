# 看盘出建议：脚本怎么跑

目标：用现有脚本，对「今天 ETH 该怎么看」给出有依据的判断。三步走。

## 1. 先更新数据

```bash
.venv/bin/python main.py fetch -p ETH/USDT -t 1h -s 2026-06-01
```

增量拉取到最新（已有部分自动跳过、有缺口自动回补）。

## 2. 看盘：现在偏多还是偏空

```bash
.venv/bin/python main.py analyze -p ETH/USDT -t 1h          # 最新
.venv/bin/python main.py analyze -p ETH/USDT -t 1h -d 2026-06-01  # 站在历史某日
```

输出：**倾向（偏多/偏空/震荡）+ 打分明细 + 关键价位（压力/支撑）+ 风险提示 + AI 解读**，并存到 `reports/`。
原理见 `../concept/analyze_module.md`。

## 3. 策略信号：有没有买卖点

```bash
.venv/bin/python main.py signal -p ETH/USDT -t 1h
```

输出：**买入 / 卖出 / 持有**。
> 注意：`signal` 当前基于 `ma_cross` 策略逻辑，不是主线 `trend_holding_v3`。其它策略暂无现成实时信号入口。

## 怎么综合读

- `analyze` = 对**现状的描述**，不是预测；「偏多」不等于接下来一定涨。
- `signal` = **策略层的买卖点**。
- 两者一致 → 依据更强；矛盾 → 保持谨慎。
- 最终决策在你手里，脚本只提供依据。

## 一句话

> 先 `fetch` 更新数据 → `analyze` 看现在什么状态 → `signal` 看策略要不要动手。
