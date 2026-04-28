# KonceptOS v17

一个类型论驱动的编程框架。用类型的偏序结构自动组织代码的通信、分发和时序。

当前阶段：**设计验证**——用 coding agent（Claude Code / Codex）模拟全流程，在实际编码前发现并修正设计缺陷。

---

## 核心思想

### 一切都是类型

程序由两种类型构成：

- **属性类型**（数据）——在对象之间流动的值的契约。超图中的**节点**。
- **对象类型**（函数）——接受若干属性作为输入，产出若干属性作为输出。超图中的**超边**。

整个程序就是一张超图：节点是数据，超边是函数。

### 类型匹配 = 自动通信

不需要手动接线。如果对象 A produce 类型 T，对象 B consume 类型 T' 且 T 是 T' 的子类型，则 A 和 B 自动连接。

### 偏序与精化

所有类型构成偏序。`temperature <: raw_data` 表示温度数据满足原始数据的所有约束，并附加更多。

关键原则：**永远不规定粗类型等于哪些精化类型的总和。** 粗类型的内涵由被消费的精化类型自下而上反向定义——编程设计从上到下，类型定义从下到上。

### 四条推导规则

显式声明的关系存入超图。以下关系由 checker 按需推导，不存储：

1. **逆变**：若 `a <: A` 且 `g: A -> B`，则 `g: a -> B`
2. **积精化**：若 `a <: A` 且 `b <: B`，则 `(a, b) <: (A, B)`
3. **依值偏序**：`B(a) <: B`——不涉及依值约束的关系对所有 B(a) 生效
4. **消费驱动定义**：被消费的精化类型反向定义粗类型

由于依值类型和积类型能构造出无数 trivial 关系，推导结果只在需要时计算，不写入超图。

### 时序

用 Event 类型的 `.succ()` 运算表达时序。`velocity(e)` 和 `velocity(e.succ())` 是不同时刻的数据，类型系统保证不可混用。`.succ()` 可任意链式调用——`e.succ().succ().succ()` 仍然是合法的 Event。

---

## 超图 (graph.json)

项目的唯一结构真相源。一个 JSON 文件，记录所有属性类型（节点）和对象类型（超边）的拓扑关系与元数据。

每个属性类型记录：偏序关系（refines）、设计意图（intent）、值空间（valueSpace，初始为空，实现后回填）、已确认运算（confirmedOps）、不变量（laws）。

每个对象类型记录：消费/产出的属性（consumes/produces）、设计意图、时序规约（temporal）、前后置条件、实现文件路径。

所有条目共享一个全局命名空间（属性 snake_case，对象 PascalCase），checker 强制验证唯一性。

完整 schema 见 [AGENT.md 第 3 节](AGENT.md#3-graphjson-规范)。

---

## Session Tree

开发过程组织为树状结构。每个 session 是一个任务单元——有输入（任务描述 + 相关签名）和输出（实现 + 对超图的修改记录）。

### 生命周期

Session 只有三种状态：**waiting**（已创建）、**active**（进行中）、**finished**（完成）。

没有 "failed" 状态。如果一个 session 失败，它的所有修改被回滚，然后它被直接删除——不留痕迹。

### 三条路径

1. **直接实现**——任务够小，直接写 TypeScript 实现，通过 checker 后标记完成。
2. **拆分**——任务太大，拆成多个子对象，每个对应一个子 session，按依赖关系排序执行。
3. **失败上报**——遇到无法解决的障碍（缺数据、类型冲突、spec 遗漏），回滚并将信息传递给父 session。

### Obstacle 逐级上报

子 session 不自己全局搜索解决方案。它回滚、删除自身、将问题交给父 session。父 session 在自己的作用域尝试解决（补传数据、调整拆分方案）。解决不了就继续上报。到根 session 仍然无法解决，请求人工介入。

这是概率论证：越近的祖先在拆分时看过越相关的上下文，越可能有答案。

---

## Checker

形式检查工具 (`tools/checker.ts`)，确保超图的结构正确性。**只读**——不修改 graph.json。

### 验证 (validate)

每次修改超图后必须运行：

```bash
npx ts-node tools/checker.ts validate
```

检查项（ERROR 级别）：
- Produce/Consume 平衡——每个被消费的属性必须有产出者
- 偏序 DAG——refines 无环
- 精化覆盖——产出者覆盖消费者需要的全部精化子集
- 帧因果性——输出帧不能早于输入帧
- 命名唯一性——全局无重复 ID
- 引用完整性——所有引用指向已存在的 ID

检查项（WARN 级别）：
- 孤立类型——有产出无消费
- 实现文件对应——impl 字段与文件系统一致
- 元数据完整性——每个条目有定义文件和设计意图

### 查询 (query)

按需计算推导关系，不存储结果：

```bash
# 逆变：某对象能否合法接受某属性类型？
npx ts-node tools/checker.ts query contravariant --object <id> --input <id>

# 覆盖：某属性的哪些精化类型被消费？产出者是否覆盖？
npx ts-node tools/checker.ts query coverage --attribute <id>

# 时序：某对象的帧流是否因果合法？
npx ts-node tools/checker.ts query temporal --object <id>

# 积精化：两个属性的积类型在偏序中的位置？
npx ts-node tools/checker.ts query product --attributes <id1> <id2>
```

---

## 自下而上

这是贯穿整个框架的核心原则，值得单独强调。

一开始我们**不知道**属性类型的具体值空间、合法运算和不变量。我们只知道名字和设计意图。

然后我们用对象（函数）去连接这些属性。如果编程成功——函数跑通了——那么这些函数本身就成为了属性类型的已确认合法运算。值空间、Laws 从实现中自然浮现。

如果编程失败——发现某个函数根本不可能实现——那就回滚，汇报问题，让上级决定是调整设计还是换一条路。

不预设。不猜。让代码告诉你类型是什么。

---

## 模拟方式

当前阶段不构建真正的引擎。做法：

1. 将 `AGENT.md` 放入项目根目录作为 coding agent 的指令集
2. 给 agent 一个具体的项目目标（如"写一个天气数据处理 pipeline"）
3. Agent 按 AGENT.md 的指引自行创建超图、session、类型定义和实现
4. Agent 每步都运行 `checker validate` 确保形式正确
5. 观察 agent 的行为，发现框架设计中的问题，迭代修正

目标是在写出真正的 KonceptOS 引擎之前，用模拟把设计问题找出来。

---

## 文件结构

```
KonceptOS/
├── AGENT.md          ← Coding agent 指令集
├── README.md         ← 本文件（供人阅读）
├── tools/
│   └── checker.ts    ← 形式检查工具
├── package.json
└── tsconfig.json
```

以下目录由 agent 在模拟过程中自动创建：

```
├── K/
│   ├── graph.json    ← 超图
│   ├── defs/         ← TypeScript 类型定义与函数签名
│   └── sessions/     ← Session tree
└── src/              ← 实现代码
```

---

## 理论背景

- **Curry-Howard 同构**：签名 = 类型 = 命题。实现 = 居民 = 证明。开发 = 逐个构造证明。
- **eval / curry 对偶**：LLM 写代码时用 eval 视角（函数作用于数据），运行时引擎用 curry 视角（数据到来时凝固函数）。
- **依值类型**：一个签名 `update : (e:E) -> velocity(e) -> velocity(e.succ())` 覆盖无穷多帧，但只需写一次。
- **形式验证方向**（待定）：考虑用 pi-演算或 session type 做通信正确性的形式验证。

详细理论见 [KonceptOS v17 设计文档](./docs/KonceptOS_v17.md)。
