# KonceptOS 教程

本教程完整演示 KonceptOS 的工作流程：从需求文档构建应用、将可复用的领域知识提取为种子、再利用种子大幅降低第二个应用的构建成本。

读完后你将理解 K 如何演化、何时需要人工介入、以及为什么种子是这套方法的复利。

## 前置条件

- Python 3.8+
- OpenRouter API key（或修改 `LLM` 类以接入其他提供商）

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
python konceptos.py
```

---

## 第一部分 — 无种子构建

任何领域的第一个项目都是最难的。此时没有种子，每个分解决策都要从零做起。这很正常。目标不仅是交付项目，更是充分学习领域结构，以便下次编码复用。

以 2D 平台跳跃游戏（超级马里奥克隆）为贯穿示例。

### 步骤一：从需求文档提取 K₀

每个项目都从一份自然语言需求文档开始。不需要很正式——几页描述系统功能的文字就够了。

```
K[0|0]> llm analyze supermario_fca_spec.md
  22 obj, 9 attr
  K: |G|=22 |M|=9 RW=47 ?=0 |B|=52
```

LLM 读取文档，生成初始交叉表 K₀：22 个对象（模块/函数）、9 个属性（数据通道）、47 个 RW 格子。提示符 `K[22|47]` 实时显示两个关键数字：对象数量和剩余 RW 数量。

检查提取结果：

```
K[22|47]> ctx          # 查看交叉表
K[22|47]> st           # 状态摘要
K[22|47]> rw           # 列出所有 RW 格子
```

47 个 RW 格子意味着 47 处描述精度不足——某个模块被标记为对某通道既读又写，通常说明该通道把两种不同的数据流压缩在了一起。

### 步骤二：通过消解 RW 来演化 K

核心循环是词汇替换：用更精细的名字替换粗名字，重新填写关联值，重算概念格。

**拆分对象。** 从 RW 最多的对象开始：

```
K[22|47]> resolve obj F13
  brick  question_block  hidden_block  empty_block
```

`resolve` 命令让 LLM 将"方块系统"分解为子类型。LLM 可能建议太多或太少——用 `edit` 提示来修剪。此处四个子类型恰好覆盖领域语义。

关键原则：**按领域语义拆分，不按 R/W 方向拆分。** "方块系统"拆为砖块、问号块、隐藏块、空块——因为它们是游戏世界中不同的东西。拆成"方块读取器"和"方块写入器"毫无意义。

**拆分属性。** 拆对象后部分 RW 消失了，但有些残留是因为属性本身太粗：

```
K[25|50]> resolve attr D
  powerup_state  score  lives  timer
```

"游戏状态"原本是一个属性。拆为变身状态、计分、生命、计时后，旧的 RW 得到解释：方块*读取*变身状态（决定弹出什么道具），*写入*计分（被击碎时加分）。这是两条不同的数据流，被压缩在一个名字下。

**拆分物理：**

```
K[28|53]> resolve attr B
  position  velocity  collider
```

"空间物理"变为位置、速度、碰撞体——三个读写模式截然不同的通道。

### 步骤三：手动修正

LLM 有时会标错方向。将物理拆为 position、velocity、collider 后，LLM 把许多对象的 collider 标成了 RW。但碰撞体在初始化后不会改变——应该全部是 R。

```
K[28|58]> set F09 B_3 R      # 碰撞检测只读碰撞体
K[28|57]> set F11 B_3 R      # 怪物只读碰撞体
...
K[28|49]> compute
```

九处手动修正，每一处都基于领域知识："碰撞体是常量。"这是第二种演化驱动力——来自领域理解的自下而上反馈。`compute` 命令在修改后重算概念格。

### 步骤四：判断何时停止

K 不需要达到理论上的原子级 K\* 才能构建。问题在于当前的 K 是否捕获了足够的结构，使 LLM 能生成正确的代码。

实用启发式：如果剩余的 RW 格子位于歧义不影响实现的区域（例如一个 UI 元素同时读写显示缓冲），可以保留。如果 RW 格子位于架构边界（例如物理与渲染之间），则必须消解。

```
K[28|47]> build mario.html
```

`build` 命令将当前 K（对象、属性、关联表、种子约定）发送给 LLM，生成完整的可运行应用。

### 步骤五：测试与迭代

测试输出。如果有问题，修正通过 K 进行：

```
# 发现碰撞事件需要携带方向信息
K[28|47]> resolve attr col_ev
  col_type col_pos
K[28|45]> compute
K[28|45]> diff 3 4          # 比较快照 3（修改前）和快照 4（修改后）
```

`diff` 命令精确显示哪些模块受影响、哪些模块可证明不受影响。只有受影响的模块需要重新生成。

### 第一个项目的经验

无种子构建中会浮现几个规律：

- LLM 的初始分解建议是起点，不是终点。大多数都需要 `edit`。
- 方向错误（把常量标为 RW）是 LLM 最常犯的错。领域知识能捕捉到它们。
- 将音频拆为 sfx/bgm、生命周期拆为 alive/spawn、物理拆为 position/velocity/collider——这些决策适用于*所有*2D 平台游戏，不仅仅是当前项目。
- 分解树（什么拆成什么）和方向提示（碰撞体永远是 R）是可复用的知识。

这就是种子的原材料。

---

## 第二部分 — 提取种子

第一个项目交付后，其 K 快照链包含了所有分解决策。种子将这些决策编码下来，以便在未来项目中重放。

### 种子包含什么

Level 2 种子（实践中的最佳平衡点）包含四样东西：

**1. 对象词表** — 该领域中模块的合法名称：

```json
{
  "obj_vocab": [
    "game_loop", "input_manager", "physics_engine",
    "collision_detector", "renderer", "player_character",
    "patrol_enemy", "collectible", "gui_hud"
  ]
}
```

**2. 属性词表** — 数据通道的合法名称：

```json
{
  "attr_vocab": [
    "position", "velocity", "collider", "sprite",
    "animation_state", "input_state", "score", "lives"
  ]
}
```

**3. 分解树** — 粗名字如何拆为细名字：

```json
{
  "obj_tree": {
    "entity": ["player_character", "enemy", "collectible"],
    "enemy": ["patrol_enemy", "flying_enemy", "stationary_enemy"]
  },
  "attr_tree": {
    "physics": ["position", "velocity", "collider"],
    "game_state": ["score", "lives"]
  }
}
```

**4. 关联方向提示** — 防止常见 LLM 方向错误的约束：

```json
{
  "incidence_hints": {
    "*|collider": "R",
    "renderer|position": "R",
    "renderer|sprite": "R",
    "input_manager|input_state": "W",
    "physics_engine|position": "W"
  }
}
```

通配符 `*|collider: R` 表示"无论什么对象，碰撞体永远是只读的。"仅这一条提示就避免了第一个项目中的九处手动修正。

### 约定（Conventions）

种子还可以携带**约定**——跨通道的值约束，LLM 在代码生成时必须遵守：

```json
{
  "conventions": [
    "JUMP REACHABILITY: max_jump_height = jump_speed^2 / (2 * gravity). Every platform must be reachable.",
    "UNIFORM GRAVITY: All entities use the same gravity constant.",
    "TWO-PLAYER CONTROLS: Use non-conflicting key sets (WASD + Arrow keys)."
  ]
}
```

约定在 `build` 时注入 LLM 提示。它们编码了领域物理和设计规则——如果没有约定，LLM 可能会生成跳不上去的平台。

### 保存种子

```
K[28|47]> seed save seed_2d_platformer.json
```

种子是 JSON 文件，可以纳入版本控制、分享、持续改进。

---

## 第三部分 — 使用种子构建

同一领域的第二个项目展示种子的回报。我们构建一个森林冰火人克隆——一个结构上不同的游戏（双人合作解谜平台），但与马里奥克隆共享相同的底层关注点维度。

### 步骤一：先加载种子，再分析

```
K[0|0]> seed load seed_2d_platformer.json
K[0|0]> llm analyze fireboy_spec.md
  18 obj, 9 attr
  K: |G|=18 |M|=9 RW=38 ?=0 |B|=44
```

分析前先加载种子。LLM 现在可以访问来自第一个项目的词表、分解树和方向提示。

### 步骤二：种子引导下的演化

消解对象和属性时，`resolve` 优先查种子的分解树。如果存在匹配的规则，直接应用，无需调用 LLM：

```
K[18|38]> resolve attr B
  position velocity collider       # 来自种子，无需 LLM 调用
```

种子知道"物理"应拆为 position、velocity 和 collider。这个决策在马里奥项目中需要反复思考，现在是自动的。

方向提示也同时生效：collider 被自动设为 R，避免了上次需要九处手动修正的方向错误。

### 步骤三：领域特有的补充

种子处理通用的 2D 平台结构。剩下的是游戏特有的内容：元素免疫（火/水/毒）、开关与门、可推动的箱子。这些需要种子中没有的新对象和属性：

```
K[22|30]> add attr element_type
K[22|30]> add obj switch_mechanism
K[23|28]> set switch_mechanism element_type R
```

种子不消除领域特有的工作——它消除的是重复通用工作。

### 步骤四：构建

```
K[25|18]> build fireboy.html
```

RW 数量下降更快（38 → 18，对比第一个项目同阶段的 47 → 47），需要的手动修正更少，分解步骤因为种子提供了词表而减少了判断负担。

### 种子带来了什么变化

具体而言，种子贡献了：

- **零次 LLM 调用**——匹配分解树的部分（物理、音频、生命周期、游戏状态）直接展开。
- **零次手动方向修正**——被方向提示覆盖的通道（碰撞体、渲染器输入、input_state）自动正确。
- **跨项目一致的命名**——`position` 而不是 `pos` 或 `location` 或 `coordinates`，因为词表约束了 LLM 的选择。
- **约定强制执行**——生成的代码遵守跳跃可达公式、使用不冲突的双人按键绑定，因为约定被注入了构建提示。

第一部分中耗费八个步骤和九处手动修正的结构性决策，现在自动完成。开发者的注意力集中在真正新的东西上：元素机制、合作解谜设计、开关-门联动。

---

## 第四部分 — 演化循环详解

本节展开第一到第三部分快速略过的机制。

### 阅读交叉表

`ctx` 命令显示核心数据结构：

```
         pos  vel  col  spr  anim input score lives
physics   W    R    R    0    0    0     0     0
renderer  R    0    R    R    R    0     0     0
input     0    0    0    0    0    W     0     0
player    R    W    R    R    R    R     W     0
enemy     R    W    R    R    R    0     0     0
hud       0    0    0    0    0    0     R     R
```

每行是一个模块，每列是一个数据通道。R 表示该模块从该通道读取；W 表示写入。这张表*就是*系统的架构。

### 概念格揭示了什么

修改后运行 `compute` 重算概念格 B(K)。每个概念 (A, B) 是交叉表中的一个极大矩形：A 是一组共享 B 中所有属性的模块。

```
K[25|18]> lat
  Concept 0: ({physics, renderer, player, enemy}, {pos, col})
  Concept 1: ({player, enemy}, {pos, vel, col, spr, anim})
  Concept 2: ({renderer}, {pos, col, spr, anim, camera})
  ...
```

概念 0 表示：physics、renderer、player 和 enemy 都与 position 和 collider 交互——它们必须就这两个通道的数据格式达成一致。这是从表中机械推导出的接口契约。

### 从表中推导数据流

`flows` 命令推导数据流图：

```
K[25|18]> flows
  input_state:  input_manager → player
  velocity:     player → physics, enemy → physics
  position:     physics → renderer, physics → collision_detector
  score:        player → hud
```

写者产生数据，读者消费数据。完整的数据流从 I 中直接读出，无需额外规约。

### 从表中推导执行顺序

写者必须在读者之前执行：

```
input_manager（写 input_state）
  → player（读 input_state，写 velocity）
    → physics（读 velocity，写 position）
      → renderer（读 position）
      → collision_detector（读 position）
```

无偏序关系的模块可以并行执行。偏序图中的环表示帧边界——不是错误，因为游戏循环本身就是跨帧的反馈回路。

### 驱动演化的三种力

**自上而下的精细化：** 种子或领域知识说"物理应拆为 position、velocity、collider"。应用规则，重填 I，重算。

**自下而上的反馈：** 实现碰撞检测时发现碰撞事件需要携带方向信息。这意味着 `collision_event` 应拆为 `collision_type` 和 `collision_direction`。修改 K，运行 `diff`，仅重新构建受影响的模块。

**横向发现：** 实现敌人渲染时发现需要一个"压扁进度"通道用于踩踏动画。将该属性加入 K，设置关联值，重算。新的契约涌现：踩踏处理器和敌人渲染器必须就压扁进度的格式达成一致。

三种力在开发过程中交替出现。K 的演化与编码不是前后两个阶段——它们是交织在一起的。

---

## 第五部分 — 种子生命周期

种子随使用而改进。演进轨迹：

**t=0** — 没有种子。手动构建第一个项目，从零做每一个分解决策。这是投资。

**t=1** — 从第一个项目的 K 快照链提取 Level 2 种子。种子捕获了分解树、方向提示和约定。同领域的后续项目从此起步。

**t=5** — 经过五个项目后，种子趋于稳定。边界情况已被遇到并编码。词表足够全面。方向提示覆盖了所有常见的方向错误。

**t=20** — 种子成熟。它以机器可读的格式编码了多年的领域经验。同领域的新项目只需添加项目特有的部分，通用结构已完全自动化。

仓库中附带的 `seed_2d_platformer.json` 大约处于 t=2 阶段——从两个项目（Mario 和 Fireboy）中提取，覆盖了核心平台跳跃结构，但尚未处理所有边界情况。

---

## 快速参考

| 阶段 | 做什么 | 命令 |
|------|--------|------|
| 启动 | 加载种子（如有），分析需求 | `seed load`, `llm analyze` |
| 检查 | 审查交叉表和 RW 格子 | `ctx`, `st`, `rw` |
| 演化 | 拆分对象和属性以消解 RW | `resolve obj`, `resolve attr` |
| 修正 | 修复 LLM 方向错误 | `set`, `row` |
| 验证 | 重算概念格，审查契约 | `compute`, `lat`, `flows` |
| 构建 | 生成应用 | `build` |
| 测试 | 发现问题，修改 K，diff，重建 | `set`, `compute`, `diff`, `build` |
| 提取 | 保存种子供未来项目使用 | `seed save` |

---

## 常见陷阱

**按 R/W 方向而非领域语义拆分。** 把"方块系统"拆成"方块读取器"和"方块写入器"会得到两个没有领域含义的对象。应该拆为砖块、问号块、隐藏块——游戏世界中真实存在的东西。

**盲目信任 LLM 的方向标注。** LLM 会把运行时常量（碰撞体、地图数据、关卡结构）标为 RW。每次 `resolve` 后检查 `rw`，手动修正。

**过度消解。** 不是每个 RW 格子都需要在 `build` 前消解。如果歧义在当前抽象层级不影响代码正确性，可以保留，以后再细化。

**不使用种子。** 如果你在同一领域构建第二个项目却不使用第一个项目的种子，你就在重复劳动。即使是 Level 1 种子（仅词表）也能防止命名漂移。

**忽略约定。** 没有约定的种子生成的代码能编译但不能工作——跳不上去的平台、穿不过去的通道、冲突的按键绑定。约定不是可选的润色，而是领域物理。
