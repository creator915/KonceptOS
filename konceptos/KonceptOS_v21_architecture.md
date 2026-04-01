# KonceptOS v2.1 架构手册

## 启动方式

```bash
# 方式一：作为包运行
python -m konceptos
python -m konceptos --load state.json

# 方式二：直接运行
python main.py
python main.py --load state.json

# 环境变量
export OPENROUTER_API_KEY="sk-or-v1-..."
```

---

## 文件结构与职责

```
konceptos/
  __init__.py       2 行    包标记，版本号
  __main__.py      23 行    入口：解析命令行参数，创建 Engine/LLM，启动 REPL
  util.py          59 行    公共工具函数（不依赖其他模块）
  seed.py          69 行    种子接口和实现（不依赖其他模块）
  engine.py       422 行    K 引擎核心（依赖 util, seed）
  llm.py          161 行    LLM 调用和 prompt 模板（依赖 util）
  codegen.py      313 行    代码生成管线（依赖 util, engine 的类型）
  verify.py       186 行    验证和反馈（依赖 util, engine 的类型）
  cli.py          540 行    REPL 命令处理（依赖所有模块）
main.py             4 行    独立入口，转发到 __main__
```

### 依赖关系图

```
util.py ←── seed.py
   ↑           ↑
   ├── engine.py (依赖 util, seed)
   ├── llm.py    (依赖 util)
   ├── codegen.py(依赖 util, 读取 engine 实例)
   ├── verify.py (依赖 util, 读取 engine 实例)
   └── cli.py    (依赖全部，是唯一的集成点)
```

**规则：只有 cli.py 同时 import 所有模块。其他模块之间不互相 import（engine 不知道 codegen 存在，codegen 不知道 llm 存在）。**

---

## 各模块详细说明

### util.py — 公共工具

**改这个文件影响：所有模块。**

提供的东西：
- `VALID_I = {'0','R','W','RW'}` — I 值的合法集合
- `cc(text, *colors)` — ANSI 彩色输出
- `extract_json(text)` — 从 LLM 响应中提取 JSON
- `load_file(filepath)` — 加载文件（自动查 uploads 目录）
- `safe_name(name)` — 任意名字 → 合法 JS 标识符（支持中文）
- `safe_contract_name(name)` — 模块名 → PascalCase 契约名

**改动注意：** `VALID_I` 是全局常量，改它会影响所有 I 值校验。`safe_name` 的逻辑决定了生成代码中的变量名，改它要同步检查 codegen.py 的输出。

---

### seed.py — 种子

**改这个文件影响：engine.py（通过 SeedChain 调用），cli.py（seed 命令）。**

三个类：

```python
class Seed:           # 基类接口，所有方法返回 None
class JsonSeed(Seed): # JSON 文件实现，含 obj_tree/attr_tree/incidence_hints/conventions
class SeedChain(Seed):# 优先级链，按顺序查询多个种子
```

**交互契约：**
- `suggest_direction(obj_name, obj_desc, attr_name, attr_desc)` → `'0'|'R'|'W'|'RW'|None`
- `suggest_split(name, desc, kind)` → `[{name,desc},...]|None`
- `suggest_schema(attr_name, attr_desc)` → `str|None`

返回 `None` = "我不知道"，调用方会回退到下一个种子或 LLM。

**改动注意：** 要加新类型的种子（如 LLM 种子、代码分析种子），只需实现 `Seed` 接口并加到 `SeedChain` 中。不需要改 engine.py。

---

### engine.py — K 引擎

**改这个文件影响：cli.py 的所有命令，codegen.py 和 verify.py 读取 engine 实例。**

**这是核心，改动最需谨慎。**

核心数据结构（Engine 实例的属性）：

```python
e.objects     # {oid: {name, desc}}
e.attributes  # {aid: {name, desc}}
e.incidence   # {(oid,aid): '0'|'R'|'W'|'RW'}
e.schemas     # {aid: 'TypeScript type string'}
e.impls       # {module_name: [{code, comment, ts}, ...]}
e.dag         # DAG 实例（节点存储、边存储）
e.current_node# 当前 DAG 节点的 hash
e.dirty       # 是否有未 commit 的修改
e.seed        # 当前 JsonSeed
e.seed_chain  # SeedChain
```

核心方法分组：

| 方法组 | 方法 | 改动影响 |
|-------|------|---------|
| K 操作 | `add_obj, add_attr, set_i, del_obj, del_attr, set_schema` | cli 的编辑命令 |
| 查询 | `rw_count, rw_cells, coverage, get_row, get_col, contract_for, writers_of, readers_of` | codegen, verify, cli 的显示命令 |
| FCA | `compute, _intent, _extent` | cli 的 lat/groups 命令 |
| 一致性 | `check_consistency` | cli 的 st 命令，verify |
| 时序 | `build_order_graph, detect_temporal_conflicts, topo_sort` | codegen 的 assemble, cli 的 order/conflicts |
| 数据流 | `dataflows, coding_groups` | cli 的 flows/groups 命令 |
| 精化 | `resolve` | cli 的 resolve/evolve 命令 |
| DAG | `commit, goto_node` | cli 的 commit/goto/undo |
| 序列化 | `save_dag, load_dag, load_v09, export_spec` | cli 的 save/open/export |

**改动注意：**

- `contract_for(oid)` 返回 `{reads:[...], writes:[...], readwrites:[...]}` — codegen.py 和 verify.py 都依赖这个格式。改返回格式要同步改它们。
- `topo_sort()` 现在有环时会附加剩余模块（而非丢弃）。返回 `(order_list, has_cycle)`。codegen.py 的 assemble 依赖这个行为。
- `check_consistency()` 现在包含多写者检测（MULTI_W）。返回字符串列表。
- `resolve()` 现在返回 `new_ids` 列表。cli.py 显示它们。

---

### llm.py — LLM 调用

**改这个文件影响：cli.py 的 llm/resolve/evolve/impl/schema auto 命令。**

**不影响 engine.py、codegen.py、verify.py。**

配置（文件顶部）：

```python
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY","")
OPENROUTER_MODEL = "anthropic/claude-opus-4.6"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
```

方法清单：

| 方法 | 用途 | 调用者 |
|------|------|--------|
| `ask(system, user, max_tokens)` | 底层 API 调用 | 所有其他 LLM 方法 |
| `is_error(response)` | 检测错误响应 | cli.py |
| `extract_gm(text)` | 从需求文档提取 K₀ | cli: `llm analyze` |
| `judge_batch(pairs, context)` | 批量判断 I 值方向 | engine: `resolve` |
| `ask_expansion(name, desc, kind, vocab)` | 建议拆分方案 | cli: `resolve` |
| `suggest_schemas(attrs_info, conventions)` | 建议 schema | cli: `schema auto` |
| `build_module(...)` | 生成单模块 impl | cli: `impl` |
| `build_full(spec, conventions)` | 旧版全量生成 | cli: `build` |

**改动注意：**

- `build_module` 的签名现在接收 `contract_code` 和 `framework_excerpt` 两个参数——这些由 codegen.py 生成，在 cli.py 中组装后传入。要改 prompt 模板只需改这个文件。
- `extract_gm` 的 system prompt 已经包含"属性是数据通道"的教育。要改 K₀ 提取质量，改这里的 prompt。
- 所有 LLM 方法的错误响应以 `(HTTP`、`(err`、`(API` 开头。`is_error()` 检查这个前缀。

---

### codegen.py — 代码生成管线

**改这个文件影响：cli.py 的 impl/assemble/framework 命令。**

**不影响 engine.py、llm.py、verify.py。**

这是 v2.0 完全缺失、v2.1 新增的关键模块。

三个核心函数：

```python
generate_framework_js(engine) → str
# 从 K 机械生成 framework.js，包含：
#   - ChannelStore 运行时（state.read/write/has）
#   - 通道名常量（CH_POSITION = 'position'）
#   - 通道 schema 注释
#   - 模块契约声明（CONTRACTS 对象）
#   - 通道初始化函数（initChannels）
#   - 瓦片编码常量
#   - conventions 注释

generate_impl_context(engine, oid) → str
# 为一个模块生成框架上下文摘要，注入 impl 的 LLM prompt：
#   - state.read/write API 说明
#   - 该模块可访问的通道列表和 schema
#   - 契约声明
#   - 模块接口形状（init/update/render）

assemble_html(engine, impl_selection=None) → (html_str, issues_list)
# 完整的组装管线：
#   1. 生成 framework.js
#   2. 对每个模块（按 topo 排序），选择 impl 并剥离 TS 语法
#   3. 生成 game loop（ALL_MODULES 数组 + gameInit/gameUpdate/gameRender）
#   4. 生成 bootstrap 代码
#   5. 拼入 HTML
```

辅助函数：

```python
generate_contract_code(engine, oid) → str    # 单模块契约文本
_strip_ts_syntax(code) → str                 # 剥离 import/export/类型注解
_default_for_schema(schema) → str            # 从 schema 推导 JS 默认值
_js_array(list) → str                       # Python 列表 → JS 数组字面量
```

**改动注意：**

- `generate_framework_js` 是**整个管线的核心**。它生成的 ChannelStore 是运行时的基础。改 state.read/write 的行为会影响所有 impl。
- `_strip_ts_syntax` 是脆弱的正则替换。如果 LLM 生成了复杂的 TypeScript 语法（泛型、枚举、命名空间），这里可能剥离不干净。需要逐步增强。
- `assemble_html` 中模块变量名的约定是 `mod_` + `safe_name(module_name)`。如果某个 impl 的代码中没有定义这个变量名，game loop 会用空桩替代。
- 瓦片编码常量（TILES 对象）目前是硬编码的。应该从 conventions 中提取。这是一个待改进点。

---

### verify.py — 验证与反馈

**改这个文件影响：cli.py 的 verify/assemble 命令。**

**不影响 engine.py、llm.py、codegen.py。**

检查函数：

| 函数 | 检查什么 | 严重性 |
|------|---------|--------|
| `check_multi_writers(engine)` | 同一通道有多个 W 写者 | error（除非 schema 已是 Record） |
| `check_contract_violations(engine)` | impl 代码中 state.read/write 了契约外的通道 | error |
| `check_init_conflicts(engine)` | 多个模块在 init 中写同一通道 | warning |
| `check_method_signatures(engine)` | init/update/render 方法名不统一 | warning |
| `verify_all(engine)` | 运行上述所有检查 | — |

返回 `Issue` 对象列表：

```python
class Issue:
    severity  # 'error' | 'warning' | 'info'
    module    # 模块名或 None（全局问题）
    message   # 描述
    suggestion# 建议的 K 修改（可选）
```

**改动注意：**

- `check_contract_violations` 使用正则匹配 `state.read('...')` 和 `state.write('...')`。如果 impl 代码使用了变量间接访问（如 `const ch='position'; state.read(ch)`），检测不到。需要更强的分析。
- `check_init_conflicts` 通过追踪 `init`/`setup`/`initialize` 方法体内的 `state.write` 来检测。大括号计数是简单启发式，嵌套函数可能误判。
- 要加新的检查项，只需写一个 `check_xxx(engine) → [Issue]` 函数并加到 `verify_all` 中。

---

### cli.py — REPL

**改这个文件影响：用户交互。**

**这是集成点，import 所有其他模块。**

改动 cli.py 不会影响其他模块的逻辑。cli.py 的职责是：
1. 解析用户输入
2. 调用 engine/llm/codegen/verify 的方法
3. 格式化输出

命令与模块的映射：

| 命令 | 调用模块 |
|------|---------|
| `add/del/set/row` | engine |
| `ctx/st/rw/flows/order/conflicts/groups/lat/concept` | engine + 显示函数 |
| `ts` | engine.contract_for + util.safe_contract_name |
| `framework` | codegen.generate_framework_js |
| `seed *` | seed |
| `llm analyze/chat` | llm |
| `resolve/evolve` | llm.ask_expansion + engine.resolve |
| `impl` | codegen.generate_impl_context + llm.build_module |
| `verify` | verify.verify_all |
| `assemble` | verify.verify_all + codegen.assemble_html |
| `build` | llm.build_full（旧版） |
| `commit/goto/undo/dag/path/diff` | engine.DAG |
| `save/open/export` | engine 序列化 |
| `schema auto` | llm.suggest_schemas |

---

## 修改指南

### "我想改 LLM 的 prompt"

只改 `llm.py`。每个 prompt 是一个独立方法。改 `extract_gm` 的 system prompt 影响 K₀ 提取质量。改 `build_module` 的 prompt 影响 impl 生成质量。不需要改其他文件。

### "我想改生成的 framework 代码"

只改 `codegen.py` 的 `generate_framework_js()`。这个函数的输出是一个 JS 字符串，会被 `assemble_html` 直接嵌入 HTML。同时检查 `generate_impl_context()` 是否与 framework 一致——这个函数生成的是 impl prompt 中的框架摘要。

### "我想加新的验证规则"

只改 `verify.py`。写一个 `check_xxx(engine) → [Issue]` 函数，然后在 `verify_all` 中加一行 `issues.extend(check_xxx(engine))`。

### "我想加新的 REPL 命令"

只改 `cli.py`。在 `run_repl` 的 while 循环中加 `elif cmd=='xxx':` 分支。如果新命令需要新的引擎功能，在 engine.py 加方法。

### "我想改 K 的数据模型"

改 `engine.py`。注意以下下游影响：
- `contract_for()` 的返回格式被 codegen.py 和 cli.py 使用
- `check_consistency()` 的返回格式被 cli.py 的 `st` 命令使用
- `topo_sort()` 的返回格式被 codegen.py 的 `assemble_html` 使用
- DAG 序列化格式变化会导致旧的 .json 文件不兼容

### "我想支持多文件项目输出"

改 `codegen.py`。加一个 `assemble_project(engine, output_dir)` 函数，用 `coding_groups()` 分组输出多个 .js 文件 + 一个 index.html。不需要改 engine.py。在 cli.py 加一个命令入口。

### "我想接入 tsc 编译验证"

在 `verify.py` 中加 `check_with_tsc(engine, output_dir)` 函数。先调 `codegen.assemble_project()` 生成 .ts 文件，再 `subprocess.run(['npx','tsc','--noEmit'])`，解析 stderr 输出为 Issue 列表。在 cli.py 的 `verify` 命令中调用。

---

## 管线流程图

```
用户输入需求文档
    ↓
llm.extract_gm()          → K₀ (G, M, I)
    ↓
手动/自动 resolve          → K 精化 (RW → R/W/0)
    ↓
engine.check_consistency() → 告警（R_no_W, MULTI_W）
    ↓
schema 声明/自动           → 三个条件满足
    ↓
codegen.generate_framework_js(engine) → framework.js 代码
    ↓
codegen.generate_impl_context(engine, oid) → prompt 上下文
    ↓
llm.build_module(..., framework_excerpt) → impl 代码
    ↓
verify.verify_all(engine)  → 问题列表
    ↓                           ↓ 有 error
    ↓ 无 error                  → 修改 K (fork) 或重新 impl
    ↓
codegen.assemble_html(engine) → 可运行 HTML
```

**v2.0 断裂的地方（现在已修复）：**
- `generate_framework_js` 不存在 → 现在存在
- `generate_impl_context` 不存在 → 现在存在，注入 impl prompt
- `verify_all` 不存在 → 现在存在，assemble 前自动运行
- `assemble_html` 只做文本拼接 → 现在包含 framework + ChannelStore + game loop

---

## 仍待解决的问题

以下问题在 v2.1 中**未修复**，需要后续迭代：

1. **tsc 编译验证未集成** — verify.py 只做正则扫描，不调 tsc
2. **impl prompt 生成 JS 而非 TS** — 为浏览器兼容，当前指示 LLM 生成纯 JS。长期应生成 TS + 编译
3. **per-entity 通道的框架支持** — framework.js 的 ChannelStore 不区分全局通道和 per-entity 通道
4. **跨帧边标记** — topo_sort 无法区分帧内依赖和跨帧反馈
5. **种子中文匹配** — 仍用子串匹配
6. **新格子默认 RW** — 未实现 LLM 批量初始假说
7. **impl 分批分层生成** — 未实现
8. **阶段自动转化** — 未实现
