# AGENT.md — KonceptOS v17 Simulation Framework

> 本文件是 coding agent（Claude Code / Codex）的指令集。
> 目标：在正式编程落地前，用 coding agent 模拟 KonceptOS 全流程，发现设计缺陷并迭代。
> Agent 在模拟阶段一人分饰多角：设计者、实现者、检查器、session 管理器。

---

## 1. 核心概念

### 1.1 一切都是类型

| 术语 | 含义 | 超图中的角色 |
|------|------|-------------|
| **属性类型** | 数据类型——在对象之间流动的值的契约 | 节点 |
| **对象类型** | 函数类型——接受若干属性、产出若干属性 | 超边（连接多个输入节点到多个输出节点）|

对象不发明运算——对象本身就是属性运算的定义。编程成功后，对象的实现就成为属性类型的已确认合法运算。

### 1.2 偏序与精化

所有类型构成偏序结构。子类型关系 `a <: A` 表示 a 满足 A 的所有约束，并附加更多约束。

**永远不规定粗类型等于哪些精化类型的总和。** 精化类型可以随时加入或删除。粗类型的实际内涵由被消费的精化类型自下而上反向定义。

### 1.3 四条自动推导规则

以下关系**不写入 graph.json**，由 checker 按需计算，放进 agent 推理上下文：

| # | 规则 | 表述 |
|---|------|------|
| 1 | **逆变** | 若 `a <: A`, `g: A → B`, 则 `g: a → B` |
| 2 | **积精化** | 若 `a <: A`, `b <: B`, 则 `(a, b) <: (A, B)` |
| 3 | **依值偏序** | `B(a) <: B`——若关系只涉及 B 无依值约束，则对任意 `B(a)` 都生效 |
| 4 | **消费驱动定义** | 被消费的精化类型反向定义粗类型的内涵 |

**重要**：使用依值类型、积类型等可构造出无数 trivial 的类型及其关系，不应全部存入超图。graph.json 只存储显式声明的关系。

### 1.4 自下而上原则

属性类型的值空间、运算、Laws 不是预先定义的：

```
阶段 1（只有壳）：名字 + 设计意图 + 偏序关系
阶段 2（实现中）：对象代码逐步确定属性的具体结构
阶段 3（已确认）：实现成功后，回填 valueSpace、confirmedOps、laws

实现失败 → 不回填，回滚，session 删除
```

### 1.5 时序：Event 类型与 .succ()

用 Event 类型表示时序。Event 有合法运算 `.succ()`，返回 Event。

- `e` 是一个 Event
- `e.succ()` 是下一个 Event
- `e.succ().succ()` 是再下一个 Event
- 以此类推——`.succ()` 可以任意链式调用

`velocity(e)` 和 `velocity(e.succ())` 是不同时刻的数据，不可混用。

TypeScript 实现方案：运行时 Event 类 + graph.json 中的 temporal 声明 + checker 验证时序因果性。

---

## 2. 项目结构

```
KonceptOS/
├── K/
│   ├── graph.json            ← 超图：拓扑 + 所有元数据（唯一真相源）
│   ├── defs/                 ← TypeScript 类型定义与函数签名
│   │   ├── raw_data.ts       ← 属性类型接口
│   │   ├── UpdateVelocity.ts ← 对象类型签名
│   │   └── ...
│   └── sessions/             ← 扁平 session tree（每个活跃/完成的 session 一个 JSON）
│       ├── s_root.json
│       ├── s_physics.json
│       └── ...
├── src/                      ← 实现代码（方程右边）
│   ├── _event.ts             ← Event 类（运行时时序支持）
│   ├── UpdateVelocity.impl.ts
│   └── ...
├── tools/
│   └── checker.ts            ← 形式检查 / 查询工具
├── AGENT.md                  ← 本文件
├── tsconfig.json
└── package.json
```

---

## 3. graph.json 规范

graph.json 是项目的超图表示——唯一的结构真相源。

### 3.1 Schema

```jsonc
{
  "attributes": {
    "<attribute_id>": {
      "def": "defs/<attribute_id>.ts",
      "refines": ["<parent_id>"],           // 显式偏序（仅直接父类型）
      "intent": "设计意图（宁可冗余不可遗漏）",
      "valueSpace": null,                    // null = 待定; 实现后填充
      "confirmedOps": [],                    // 由成功实现自下而上确定
      "laws": [],                            // 由实现推导
      "status": "declared",                  // declared | implementing | confirmed
      "statusSession": null                  // 最近变更 status 的 session ID
    }
  },
  "objects": {
    "<object_id>": {
      "def": "defs/<object_id>.ts",
      "impl": null,                          // null | "src/X.impl.ts"
      "consumes": ["<attribute_id>"],        // 输入属性类型集合
      "produces": ["<attribute_id>"],        // 输出属性类型集合
      "intent": "设计意图（宁可冗余不可遗漏）",
      "temporal": null,                      // null | TemporalSpec（见 3.2）
      "preconditions": "",
      "postconditions": "",
      "status": "declared",
      "statusSession": null
    }
  }
}
```

### 3.2 temporal 字段

```jsonc
{
  "frameVar": "e",                           // 帧变量名
  "consumes": [                              // 数组——同一属性可出现多次（不同帧）
    { "attribute": "velocity", "frame": "e" },
    { "attribute": "acceleration", "frame": "e" }
  ],
  "produces": [
    { "attribute": "velocity", "frame": "e.succ()" }
  ]
}
```

**帧表达式语法**：

```
<frame_expr> ::= <frameVar>              // 基础：e
               | <frame_expr>.succ()     // 后继：e.succ(), e.succ().succ(), ...
```

`.succ()` 是 Event 类型的合法运算，可任意链式调用。不设人为限制。

**多帧输入示例**（平滑滤波器，需要当前帧和上一帧）：

```jsonc
{
  "frameVar": "e",
  "consumes": [
    { "attribute": "velocity", "frame": "e" },
    { "attribute": "velocity", "frame": "e.succ()" }
  ],
  "produces": [
    { "attribute": "smoothed_velocity", "frame": "e.succ()" }
  ]
}
```

### 3.3 状态转换

```
declared ──(session 开始实现)──→ implementing
implementing ──(实现成功 + checker 通过)──→ confirmed
implementing ──(session 失败/回滚)──→ [session 被删除, 状态恢复为 declared]
confirmed ──(祖先 session 回滚)──→ [级联删除, 状态恢复为 declared]
```

---

## 4. 命名规则与防冲突

### 4.1 命名约定

| 类别 | 格式 | 示例 |
|------|------|------|
| 属性类型 ID | `snake_case` | `raw_data`, `temperature`, `wind_speed` |
| 对象类型 ID | `PascalCase` | `WeatherProcessor`, `UpdateVelocity` |
| TS 定义文件 | 与 ID 同名 `.ts` | `raw_data.ts`, `UpdateVelocity.ts` |
| 实现文件 | ID + `.impl.ts` | `UpdateVelocity.impl.ts` |
| Session ID | `s_` + 描述性短名 | `s_root`, `s_weather_proc` |

属性 snake_case，对象 PascalCase——天然不冲突。

### 4.2 防冲突机制

1. **全局唯一命名空间**：attributes + objects 所有 ID 不允许重复。
2. **创建前必查**：添加新 ID 前检查 graph.json 中是否已存在。
3. **Checker 强制验证**：`validate` 包含唯一性检查。
4. **冲突时用限定名**：如 `weather_temperature` 而非 `temperature`。
5. **禁止重命名 confirmed 条目**：避免破坏引用链。
6. **Session 记录创建物**：graphDiff 明确记录哪些 ID 由本 session 创建，回滚时精确清理。

---

## 5. Session 管理

### 5.1 Session 状态

Session 只有三种状态：

| 状态 | 含义 |
|------|------|
| `waiting` | 已创建，尚未开始工作 |
| `active` | 正在进行 |
| `finished` | 成功完成 |

**没有 "failed" 或 "rolled_back" 状态。** 如果 session 失败或需要回滚，它会被直接删除——连同其 session 文件。失败的尝试不留痕迹。

### 5.2 session.json 格式

```jsonc
{
  "id": "s_weather_proc",
  "parent": "s_root",                          // null 仅限根 session
  "children": ["s_extract_temp", "s_extract_wind"],
  "status": "active",                          // waiting | active | finished
  "task": "实现 WeatherProcessor: raw_data → temperature, wind, pm",

  "input": {
    "signatures": ["WeatherProcessor"],         // 本 session 负责的对象
    "context": ["raw_data", "temperature", "wind", "pm"]
  },

  "output": {
    "implementations": [],                      // 成功后填充
    "newSignatures": [],                        // 拆分时新增的子对象
    "newAttributes": [],                        // 新发现的中间属性类型
    "graphDiff": {                              // 对 graph.json 的修改记录
      "added": { "attributes": {}, "objects": {} },
      "modified": {
        "attributes": {},
        "objects": {}
      },
      "removed": { "attributes": [], "objects": [] }
    }
  }
}
```

**graphDiff.modified 格式**（存 before/after 对）：
```jsonc
"modified": {
  "attributes": {
    "temperature": {
      "before": { "status": "declared", "valueSpace": null },
      "after":  { "status": "confirmed", "valueSpace": { "celsius": "number" } }
    }
  }
}
```

### 5.3 回滚与删除

当 session 失败时：

```
1. 读取本 session 的 output.graphDiff
2. 递归处理：先回滚并删除所有子 session（深度优先）
3. 逆向应用 graphDiff：
   - added → 从 graph.json 删除
   - modified → 用 before 值覆盖
   - removed → 重新加入
4. 删除本 session 创建的实现文件（src/*.impl.ts）
5. 删除本 session 创建的定义文件（仅 graphDiff.added 中的）
6. 删除本 session 文件（sessions/s_xxx.json）
```

回滚完成后，这个 session 不存在了——没有 "rolled_back" 状态，没有残留文件。

### 5.4 Session 生命周期

```
1. 创建 session.json（status: waiting）
2. 开始工作（status: active）
3. 判断任务复杂度：
   a. 能一次性完成 → 路径 A（直接实现）
   b. 需要拆分 → 路径 B（开子 session）
   c. 无法完成 → 路径 C（上报 + 删除）
```

**路径 A：直接实现**

```
1. 将涉及的对象/属性 status → implementing（记入 graphDiff）
2. 编写 TypeScript 实现 → src/<ObjectId>.impl.ts
3. 运行 checker validate
4. 通过：
   a. 自下而上回填属性类型（valueSpace, confirmedOps, laws）
   b. 更新 graph.json（impl, status → confirmed）
   c. 记录 graphDiff
   d. session.status → finished
5. 不通过：
   a. 如果可修复 → 修改实现，重新检查
   b. 如果不可修复 → 路径 C
```

**路径 B：拆分**

```
1. 设计子结构：
   a. 把粗对象拆成多个细对象
   b. 可能引入中间属性类型
   c. 更新 graph.json（新签名 status: declared）
   d. 创建 defs/*.ts
   e. 记录 graphDiff
2. 运行 checker validate（拆分后 produce/consume 是否平衡）
3. 提取依赖关系，按拓扑排序
4. 为每个细对象创建子 session（status: waiting）
5. 按顺序执行子 session：
   - 无依赖的优先
   - 依赖最复杂的优先（早暴露设计问题）
6. 每个子 session 完成后运行 checker validate
7. 某个子 session 失败：
   → 该子 session 被删除（5.3 流程）
   → 父 session 尝试解决（见 6.3 Obstacle 处理）
   → 如果无法解决 → 父 session 自身也走路径 C
8. 所有子 session finished → 父 session.status → finished
```

**路径 C：失败上报**

```
1. 整理失败原因（缺什么？为什么做不到？建议方向？）
2. 执行回滚（5.3 流程）——本 session 被删除
3. 将失败信息传递给父 session 的上下文
4. 父 session 决定如何处理
```

---

## 6. 工作流

### 6.1 启动

用户给出项目目标后：

```
1. 初始化项目目录结构
2. 创建 K/graph.json（空图）
3. 创建 K/sessions/s_root.json（status: active）
4. 设计顶层签名：
   a. 识别粗属性类型（数据通道）
   b. 识别粗对象类型（处理单元）
   c. 写入 graph.json（status: declared）
   d. 创建对应 defs/*.ts
5. 运行 checker validate
6. 按 Session 生命周期继续
```

### 6.2 实现一个对象类型

```
1. 读取 graph.json 中该对象的信息（consumes, produces, temporal, intent）
2. 读取相关属性类型的当前状态（可能只有 intent，无 valueSpace）
3. 如果需要时序信息，调用 checker query temporal 确认帧流
4. 编写 TypeScript 实现：
   a. 创建 src/<ObjectId>.impl.ts
   b. 实现函数逻辑
   c. 如有时序，使用 Framed<T> 包装 + Event.succ() 推进
5. 运行 checker validate
6. 通过 → 自下而上回填：
   a. 根据实现确认属性的 valueSpace
   b. 将本对象加入属性的 confirmedOps
   c. 从实现中推导 laws（如果有不变量）
   d. 更新 graph.json
7. 不通过 → 分析并修复或上报
```

### 6.3 Obstacle 处理

```
子 session 失败并被删除 → 父 session 收到失败信息

父 session 的处理步骤：
1. 分析失败原因（缺什么数据？类型冲突？不可能实现？）
2. 检查自己的作用域：
   a. 自己的输入中是否包含缺失数据？
   b. 其他子 session 的产出是否有所需数据？
   c. 能否通过偏序关系推导？（调用 checker query 辅助）
3. 如果能解决：
   → 修改拆分方案（补传数据 / 新增子 session）
   → 更新 graph.json + checker validate
   → 创建新的子 session 重试
4. 如果不能解决：
   → 父 session 自身也失败
   → 执行回滚（5.3）——父 session 被删除
   → 继续上报给祖父 session
5. 到达根 session 仍无法解决：
   → 报告给用户，请求人工介入或修改 spec
```

### 6.4 修改传导

当属性类型定义被修改时：

```
1. 查找 graph.json 中引用该属性的所有对象（consumes/produces）
2. 对每个受影响的 confirmed 对象：
   a. 检查实现是否仍满足新约束
   b. 满足 → 不动
   c. 不满足 → status 改为 declared，开新 session 重新实现
3. 运行 checker validate
```

---

## 7. 时序类型实现

### 7.1 运行时 Event 类

```typescript
// src/_event.ts
export class Event {
  constructor(public readonly step: number) {}
  succ(): Event { return new Event(this.step + 1) }
  equals(other: Event): boolean { return this.step === other.step }
  toString(): string { return `Event(${this.step})` }
}

export interface Framed<T> {
  data: T
  event: Event
}
```

### 7.2 签名定义示例

```typescript
// defs/UpdateVelocity.ts
import type { Framed } from '../src/_event'
import type { Velocity } from './velocity'
import type { Acceleration } from './acceleration'

export type UpdateVelocity = (
  vel: Framed<Velocity>,
  acc: Framed<Acceleration>
) => Framed<Velocity>
```

graph.json 中的 temporal 字段提供帧语义（checker 读取此字段，不解析 TS）。

### 7.3 实现示例

```typescript
// src/UpdateVelocity.impl.ts
import type { UpdateVelocity } from '../K/defs/UpdateVelocity'

export const updateVelocity: UpdateVelocity = (vel, acc) => {
  if (!vel.event.equals(acc.event)) {
    throw new Error(`Event mismatch: vel=${vel.event}, acc=${acc.event}`)
  }

  return {
    data: {
      vx: vel.data.vx + acc.data.ax,
      vy: vel.data.vy + acc.data.ay,
    },
    event: vel.event.succ(),
  }
}
```

### 7.4 Checker 的时序验证

Checker 从 graph.json 的 temporal 字段读取帧规约，验证：

1. 帧表达式语法合法（符合 `<frameVar>(.succ())*` 格式）
2. 时序因果性：所有输出帧深度 ≥ 所有输入帧深度（不能输出到"过去"）
3. temporal 中引用的属性必须存在于 graph.json
4. temporal 中的属性集合应覆盖对象的 consumes/produces

---

## 8. Checker 使用

### 8.1 命令

```bash
# 全量形式检查（每次修改 graph.json 后必须运行）
npx ts-node tools/checker.ts validate

# 按需查询：逆变推导
npx ts-node tools/checker.ts query contravariant --object <ObjectId> --input <AttributeId>

# 按需查询：精化覆盖
npx ts-node tools/checker.ts query coverage --attribute <AttributeId>

# 按需查询：时序一致性
npx ts-node tools/checker.ts query temporal --object <ObjectId>

# 按需查询：积精化
npx ts-node tools/checker.ts query product --attributes <AttrId1> <AttrId2>
```

### 8.2 validate 检查清单

| # | 检查项 | 级别 | 说明 |
|---|--------|------|------|
| 1 | Produce/Consume 平衡 | ERROR | 每个被 consume 的属性，至少有一个对象 produce 它或其超类型 |
| 2 | 偏序 DAG | ERROR | refines 关系无环 |
| 3 | 精化覆盖 | ERROR | 产出者必须覆盖消费者需要的精化子集 |
| 4 | 帧一致性 | ERROR | temporal 声明的帧流因果合法 |
| 5 | 命名唯一性 | ERROR | 全局命名空间无重复 |
| 6 | 引用完整性 | ERROR | 所有 refines/consumes/produces 指向已存在 ID |
| 7 | 孤立类型 | WARN | produce 但未 consume |
| 8 | 实现对应 | WARN | impl 字段与文件系统一致 |
| 9 | 元数据完整性 | WARN | 每条目有 def 和非空 intent |

### 8.3 使用时机

- **每次修改 graph.json 后**：运行 `validate`
- **设计签名时**：`query contravariant` 确认连接合法
- **拆分任务时**：`query coverage` 确认覆盖
- **实现时序对象时**：`query temporal` 确认帧流

---

## 9. 测试

编程完成后，根据设计意图和类型约束生成测试：

```
1. 属性的 laws → property-based test
   例：magnitude(velocity) >= 0

2. 对象的签名 → 接口测试
   例：UpdateVelocity 接受 Framed<Velocity> 必须返回 Framed<Velocity>

3. 时序约束 → 序列测试
   例：output.event.step === input.event.step + 1

4. Produce/consume 链 → 集成测试
   例：ProducerA → AttributeX → ConsumerB 数据流通

测试根据签名和意图编写，不根据源代码——测试的是契约，不是实现细节。
```

---

## 附录 A：graph.json 空模板

```json
{
  "attributes": {},
  "objects": {}
}
```

## 附录 B：session.json 模板

```json
{
  "id": "",
  "parent": null,
  "children": [],
  "status": "waiting",
  "task": "",
  "input": {
    "signatures": [],
    "context": []
  },
  "output": {
    "implementations": [],
    "newSignatures": [],
    "newAttributes": [],
    "graphDiff": {
      "added": { "attributes": {}, "objects": {} },
      "modified": { "attributes": {}, "objects": {} },
      "removed": { "attributes": [], "objects": [] }
    }
  }
}
```
