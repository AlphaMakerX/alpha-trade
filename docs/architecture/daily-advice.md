# 看盘出建议：脚本怎么跑

目标：用现有脚本，对「今天 ETH 该怎么看」给出有依据的判断。

## 最快：只看最优策略买卖点

只想知道**当前是否触发买卖点**，跑这一条就够 —— 自带实时拉数据，无需先 fetch：

```bash
.venv/bin/python main.py best-signal -p ETH/USDT -t 1h
```

用最优策略 `trend_holding_v3`，只在**已闭合 K 线**上评估，输出买入 / 平仓 / 无信号，并列出每个入场/出场条件是否满足。

---

想看完整盘面，走下面三步。

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

输出：**倾向（偏多/偏空/震荡）+ 打分明细 + 关键价位 + 风险提示 + 最优策略买卖点 + AI 解读**，并存到 `reports/`。
报告里的「策略信号」一节就是 `trend_holding_v3` 的买卖点评估，和 `best-signal` 同一套逻辑。原理见 `../concept/analyze_module.md`。

## 3.（可选）旧基线对照

```bash
.venv/bin/python main.py signal -p ETH/USDT -t 1h
```

输出 `ma_cross`（旧基线）的买入 / 卖出 / 持有，仅作对照。

## 怎么综合读

- `analyze` 倾向 = 对**现状的描述**，不是预测；「偏多」不等于接下来一定涨。
- `best-signal` = **最优策略的买卖点**，是动手依据。
- 两者一致 → 依据更强；矛盾 → 保持谨慎。
- 最终决策在你手里，脚本只提供依据。

## 一句话

> 快速看：`best-signal` 一条搞定。
> 完整看：`fetch` 更新 → `analyze` 看状态（已含策略买卖点）。
