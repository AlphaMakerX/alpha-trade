# AGENTS.md
Global Rules:  
G1: 不要加兜底策略，实在需要则要求人工确认。  
G2: 首次实现函数时，函数入参不要有可选参数，实在需要则要求人工确认。  
G3: 永远不要主动清理或删除 DB schema / migration / 表定义，除非用户明确要求。  
G4: 禁止使用 `console.log/info/warn/error` 打印日志，统一使用 `createLogger`（基于 pino）。`packages/backend` 从 `infrastructure/observability/logger.ts` 导入；`packages/db` 自带 pino 实例；脚本通过 `await import("../packages/backend/src/index.ts")` 获取 `createLogger`。客户端（浏览器）代码和测试文件不受此规则约束。  

Backend Rules:  
B1: 在请求网关时，通过 header 透传 entity id，方便 mock entity 的生命周期。  
B2. 对于 mapper 方法，优先有 tx:Transaction 入参，方便集成事务。  
B3. 对于调用到 mapper 方法的 service 或函数，也需要优先有 tx:Transaction 入参，方便集成事务。  
B4. 涉及实体类状态转换的所有操作，优先封装为服务，方便后续其它实体类整合，也方便加锁及测试。  
B5. 同一操作中涉及多个表写入时，要优先考虑包裹事务。  
B6. 结算（`scans.billing_status` / `scan_billing_tasks` / `billing_ledger_entries` 相关写入）只能经 `ScanLifecycleService.finalizeBillingStatus`。Application 层其它 use case 通过注入 service 调用，不直接调 domain entity 的 `markCharge*` 方法或 billing repo 的 scan 维度写入方法。  
B7. Scan 状态推进（`running` / `canceling` / `completed` / `failed` / `canceled` / `stopped`）只能经 `ScanLifecycleService` 的对应方法（`transitionScanToRunning` / `transitionScanToCanceling` / `finalizeScanAsCompleted` / `finalizeScanAsFailed` / `finalizeScanAsCanceled` / `finalizeScanAsStopped`）。Application 层其它 use case 通过注入 service 调用，不直接调 domain entity 的 `mark*` 方法。`setEngineJobId` 也由 `transitionScanToRunning` 内部完成，caller 不再独立调用。  
B8. `scan_events` 表已停用，禁止新增 `recordEvent` / `recordEventIfAbsent` 调用。如需记录运维信息，使用结构化日志（`console.info(JSON.stringify({ event: "scan.xxx", ... }))`）替代；callback 通道已下线，AIFlow 终态由 `scan-lifecycle-settle` cron 通过 `ScanLifecycleService` 统一推进。  
B9. Scan 预留扣费（`reserveScanCharge` / `assertCanStartScan`）只能经 `ScanLifecycleService` 的对应方法。Application 层其它 use case 通过注入 service 调用；不再存在独立的 `BillingUsageChargePort`。只读的账户余额快照用 `readCreditsSnapshotFromRepository(scanBillingRepository, userId)`（位于 `domain/value-objects/billing/credits-snapshot.ts`），不走 `ScanLifecycleService`。  

## Frontend Rules
1. 单个文件严禁超过 300 行。若接近上限，必须进行组件拆分或逻辑抽离
2. 严格区分 状态组件 (Logic/State) 与 UI 组件 (Presentational)
3. 不要在组件内部定义辅助函数或复杂的配置对象
4. 所有的魔法值、配置项、API 路径必须定义为常量 (Constants)
5. 按功能领域拆分 Context，禁止“万能 Context”, 就近 Provider 原则，避免不必要的全局污染与重渲染
6. useEffect 必须补全 deps。非原始类型依赖需使用 useMemo/useCallback 稳定引
7. 每个 Hook 和组件只专注于一个功能点
8. 所有的监听、订阅、定时器必须在 useEffect 的 Cleanup 函数中销毁

## 类型安全

- **禁止使用 `any` 类型。** 用具体类型、泛型、`unknown` 或类型守卫替代。

## Working Principles
- **Simplicity First**: 用最少代码解决问题。不要臆造需求, 不要为不可能发生的场景写错误处理, 若写了 200 行而 50 行就够，就重写,不要有fallback，一定要有需要人工判断
- **Think Before Coding**: 不允许做沉默的假设。遇到不确定的地方必须先问，给出多种理解让用户选择，不能自己猜测一个条件就往下写。
- **Surgical Changes**: 只改任务要求的部分，不碰其他代码，不顺手重构，不改项目的命名风格。
- **Goal-Driven Execution**: 把指令转为可验证的成功标准，先写测试再写实现，跑通了再交付。

## Project Info
- docs/project-info.md

## 1. 先想清楚再写代码

**不要臆测。不要掩饰困惑。把取舍摊开来说。**

在实现之前：
- 明确写出你的假设；不确定就问。
- 若有多种理解，列出来，不要悄悄选一种。
- 若有更简单做法，说出来；该反对时要敢于反对。
- 若有不清楚之处，先停下；点明哪里困惑；再问。

## 2. 简单优先

**用最少代码解决问题。不要臆造需求。**

- 不要超出用户要求加功能。
- 不要为只用一次的代码抽象。
- 不要加未被要求的灵活性或可配置性。
- 不要为不可能发生的场景写错误处理。
- 不要写无用的 fallback 兜底策略。有错直接抛出来，不要用 `?? ""` 或 `|| defaultValue` 悄悄吞掉。只在该值确实可能缺失时才兜底。
- 若写了 200 行而 50 行就够，就重写。

自问：“资深工程师会不会觉得过度复杂？”若是，就简化。

## 3. 外科手术式修改

**只动必须动的。只收拾自己造成的烂摊子。**

编辑既有代码时：
- 不要顺手改进相邻代码、注释或格式。
- 不要重构没坏的东西。
- 匹配既有风格，即便你本人会换一种写法。
- 若发现无关的死代码，可以提一句，不要擅自删。

当你的改动产生孤立代码时：
- 删掉因你的改动而变得未使用的 import、变量、函数。
- 不要删除本来就存在的死代码，除非用户明确要求。

检验标准：每一行改动都应能直接追溯到用户的请求。

## 4. 目标驱动执行

**定义成功标准。循环直到验证通过。**

把任务变成可验证的目标：
- “加校验” → “为非法输入写测试，再让测试通过”
- “修 bug” → “写能复现的测试，再让测试通过”
- “重构 X” → “重构前后测试都通过”

对多步骤任务，先给一个简短计划：

```text
1. [步骤] → 验证：[检查项]
2. [步骤] → 验证：[检查项]
3. [步骤] → 验证：[检查项]
```

清晰的成功标准让你能独立迭代；含糊的标准（“能跑就行”）会不断需要澄清。

若这些准则在起作用，你会看到：diff 里不必要改动更少、因过度复杂而重写的次数更少，以及澄清问题出现在实现之前而不是犯错之后。

## Key Patterns

- **Frontend state**: zustand for complex/shared state, React context for simple sharing
- **API requests**: TanStack Query (react-query)
- **Testing**: Node.js native test runner (`.test.mjs` files), not Jest/Vitest
- **E2E**: Playwright with role-based projects (visitor, normal-user, admin-user)
- **Formatting**: Prettier (semi, double quotes, 2-space tabs, trailing commas, 100 char width)
- **Commits**: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`)
- **String constants**: use named constants, not string literals scattered in code
- **Progressive rule loading**: read `AGENTS.md` first, load `docs/*.md` only as needed

## Environment

- `APP_ENV` selects environment: `local`, `dev`, `production`
- Environment files: `.env`, `.env.dev`, `.env.prod`, `.env.example`
- External services: AIFlow (scan engine), Aliyun OSS (storage), MoonPay (billing), Slack
- GitHub App auth split: user sign-in OAuth vs App installation (separate callbacks)

