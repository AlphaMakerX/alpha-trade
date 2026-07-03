# Week 3 任务（学习并验证 Momentum 因子）

> 计划与范围见 `summary.md`。标的 ETH/USDT 1h；因子 `mom_N = close_t/close_{t-N} - 1`；验证复用 `bias-eval` 口径。

## Day 1：理论基础
- [x] 写 `docs/concept/momentum-factor.md`：时序 vs 截面动量、加密动量强的原因、失效场景（反转 / 拥挤 / 成本吞噬）
- [x] 明确本周只做**时序动量、单标的 ETH**，写清因子定义与验证口径
- [x] 验证：文档能说清「为什么动量可能有效」和「什么时候失效」

## Day 2：实现因子 + 实验框架
- [x] `indicators/momentum.py` 实现 `momentum(close, period)` 纯函数，返回过去 N 根收益列
- [x] 仿 `analysis/bias_eval.py` 新建 `analysis/momentum_eval.py`：每根 K 线算因子 → 分位分层统计其后 horizon 根 forward-return + IC + 无条件 baseline
- [x] `main.py` 加 `momentum-eval` 命令（`--pair` / `--start` / `--end` / `--periods` / `--horizons` / `--quantiles`），复用 `engine.data` 取数
- [x] 写单测（固定输入固定输出，覆盖因子计算、forward-return 对齐、防未来函数、IC 方向）
- [x] 验证：`tests/test_momentum_eval.py` 6 项通过，全量 61 通过；真实 ETH 数据端到端跑通

## Day 3：多窗口参数稳定性
- [ ] 对 ETH 1h 跑 5/10/20/30/60 日（120/240/480/720/1440 根）动量
- [ ] 输出各窗口的 IC / 分层收益 / 上涨概率，看是否随窗口平滑变化
- [ ] 验证：结论不依赖单一窗口——若各窗口忽正忽负，判为不稳定并记录

## Day 4：预测力验证（不看回测收益）
- [ ] forward-return by horizon：因子分位（如 5 层）后各层平均收益是否单调
- [ ] 计算 IC（因子值与 forward-return 的秩相关）均值与 IR，对比 baseline
- [ ] 分年 / walk-forward 稳定性：预测力是否只在某段区间成立
- [ ] 验证：明确回答「ETH 1h 上 Momentum 有无预测力、哪个窗口最稳」

## Day 5：成本验证 + 总结
- [ ] 把因子转成最简信号（多头 / 多空），接入现有回测的 commission + slippage
- [ ] 对比零成本 vs 现实成本下因子是否仍有效（成本敏感度）
- [ ] 更新 `summary.md`：写入实证结论、Momentum 优缺点与失效条件
- [ ] 验证：给出扣成本后的明确结论，而非「能跑就行」

## 下一步（视结论）
- [ ] 若有效：并入策略线做完整多资产 / 多周期验证
- [ ] 若无效：记录失效原因，作为后续因子筛选的反例
