# KonceptOS 命令指南

## 安装 / 启动

```bash
# 安装到全局（项目目录下执行一次）
pip install -e .

# 启动 KonceptOS
konceptos <command> [args]
```

---

## K 编辑

```bash
konceptos add obj <id> <name> [desc]       # 添加对象（模块）
konceptos add attr <id> <name> [desc]      # 添加属性（数据通道）
konceptos set <obj> <attr> <0|R|W|RW>      # 设置关联值
konceptos row <obj> <val1,val2,...>        # 批量设置某行的关联值
konceptos del obj|attr <id>                # 删除对象或属性
konceptos schema <attr_id> <typedef>       # 为属性设置 TypeScript 类型
konceptos schema --auto [attr_id|all]      # LLM 自动生成类型定义
konceptos convention [text...]             # 设置全局约定
```

---

## 查看

```bash
konceptos ctx                              # 显示上下文矩阵（K 鸟瞰图）
konceptos st                               # 显示状态（对象数、RW 数、合约覆盖）
konceptos rw                               # 显示所有 RW（读写）单元
konceptos flows                            # 显示数据流
konceptos order                            # 显示执行顺序（拓扑排序）
konceptos conflicts                        # 显示时序冲突
konceptos groups                           # 显示编码分组
konceptos lat                              # 显示概念格层次
konceptos concept <n>                       # 显示第 n 个概念详情
konceptos ts                               # 显示 TypeScript 类型签名
konceptos framework                        # 显示生成的 framework.js
```

---

## DAG（版本历史）

```bash
konceptos commit [desc]                    # 提交当前状态到 DAG
konceptos goto <hash>                      # 跳转到指定节点
konceptos undo                             # 回退到父节点
konceptos dag                              # 列出所有节点
konceptos path                             # 显示从根到当前节点的路径
konceptos diff <a> <b>                     # 比较两个节点的差异
```

---

## Seed（先验知识）

```bash
konceptos seed show                         # 显示当前 seed 摘要
konceptos seed load <f>                     # 从文件加载 seed
konceptos seed save <f>                     # 保存 seed 到文件
konceptos seed tree                         # 显示对象/属性树
konceptos seed conv                         # 显示约定列表
konceptos seed set obj|attr <parent> <c1> <c2>...   # 添加拆分规则
```

---

## Resolve（拆分）

```bash
konceptos resolve obj|attr <id>             # 拆分指定对象或属性
konceptos evolve [n] [--all]                # 自动迭代拆分（默认 1 次）
```

---

## 实现 & 验证

```bash
konceptos impl gen <module> [comment]       # LLM 生成模块实现
konceptos impl list [module]                # 列出已实现的模块
konceptos impl show <module> <n>            # 显示第 n 个实现代码
konceptos ready                             # 显示实现覆盖率
konceptos verify                            # 交叉验证所有实现是否符合 K 合约
konceptos assemble [name]                    # 组装（LLM 决定格式），输出 {name}_{hash}.html 或 {name}_{hash}/
```

---

## LLM

```bash
konceptos llm analyze <file>               # 从规格文档提取 K（G、M、I）
konceptos llm chat <msg>                    # 直接与 LLM 对话
```

---

## Build

```bash
konceptos build [output.html]              # 全量构建（一次性 LLM 生成）
```

---

## 文件

```bash
konceptos save <f>                         # 保存 DAG 到文件
konceptos open <f>                          # 打开 DAG 文件
konceptos export <f.md>                     # 导出为 Markdown 规格
konceptos compute                           # 重新计算概念格
konceptos --help                            # 显示帮助
```

---

## 工作流示例

```bash
# 1. 从需求提取 K
konceptos llm analyze spec.md

# 2. 拆分 RW 单元
konceptos resolve obj module1
konceptos evolve 3

# 3. 生成类型定义
konceptos schema --auto

# 4. 生成模块实现
konceptos impl gen ModuleA

# 5. 验证
konceptos verify

# 6. 组装
konceptos assemble output   # LLM 决定格式，输出 output_{hash}.html 或 output_{hash}/
```

---

## 核心概念速查

- **G (Objects)** = 模块，负责执行操作
- **M (Attributes)** = 数据通道，模块间传递的数据
- **I (Incidence)** = 关联值：`0`=无、`R`=读、`W`=写、`RW`=读写
- **RW 单元** = 需要被拆分的多 writer 冲突单元
- **K = (G, M, I)** = 形式概念分析三元组
- **DAG** = 内容寻址的版本历史图
- **Seed** = 先验知识，引导 LLM 拆分决策
- **Workspace** = `./.konceptos/workspace.json`，自动持久化所有状态
