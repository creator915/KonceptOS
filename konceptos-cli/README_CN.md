# KonceptOS CLI

> K -> K* 通过词汇替换 + 重描述。基于形式概念分析(FCA)的概念演化 CLI 工具。

KonceptOS 是一个基于**形式概念分析 (FCA)** 的命令行工具，通过迭代消解压缩伪影 (RW 单元)，将初始概念上下文 K 演化为精化上下文 K\*，最终从规格说明中生成可运行的应用程序。

## 安装

```bash
npm install -g konceptos-cli
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KONCEPTOS_API_KEY` | - | LLM API 密钥（使用 LLM 功能时必需） |
| `KONCEPTOS_MODEL` | `glm-5` | 模型名称 |
| `KONCEPTOS_URL` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | API 地址 |

## 核心概念

- **K = (G, M, I)**：形式上下文，包含对象 (G)、属性 (M)、关联 (I)
- **关联值**：`0`（无关联）、`R`（读）、`W`（写）、`RW`（读写 = 压缩伪影）
- **K\***：目标精化上下文，所有 RW 单元均已消解
- **种子 (Seed)**：预定义的分解规则、约定和词汇提示
- **消解/演化**：将压缩的概念展开为更细粒度的子概念

## 典型工作流

```bash
# 1. 从文档中提取对象、属性和关联
konceptos llm analyze 需求文档.txt

# 2. 查看状态
konceptos st

# 3. 消解所有 RW 压缩
konceptos evolve all

# 4. 生成应用
konceptos build app.html
```

## 命令参考

### 基础操作

```bash
konceptos add obj <id> <名称> [-d 描述]    # 添加对象
konceptos add attr <id> <名称> [-d 描述]   # 添加属性
konceptos set <对象id> <属性id> <0|R|W|RW> # 设置关联值
konceptos row <对象id> <值列表>            # 批量设置一行（逗号分隔）
konceptos del obj|attr <id>               # 删除对象/属性
konceptos bind <属性id> <技术>             # 绑定属性到具体技术
konceptos convention [文本...]             # 设置/查看约定规则
```

### 查看

```bash
konceptos ctx          # 上下文表格（关联矩阵）
konceptos st           # 状态总览
konceptos rw           # 查看 RW 单元列表
konceptos flows        # 数据流（W -> R）
konceptos groups       # 按概念分组
konceptos lat          # 概念格
konceptos concept <n>  # 查看第 n 个概念详情
konceptos hist         # 操作历史
```

### 种子 (Seed)

```bash
konceptos seed                                       # 查看种子信息
konceptos seed load <文件>                            # 加载种子 JSON
konceptos seed save <文件>                            # 保存种子
konceptos seed tree                                  # 查看分解树
konceptos seed conv                                  # 查看种子约定
konceptos seed set obj <父级> <子级1> <子级2> ...      # 定义对象分解
konceptos seed set attr <父级> <子级1> <子级2> ...     # 定义属性分解
```

### LLM

```bash
konceptos llm analyze <文件>   # 从文档中提取 G、M、I
konceptos llm ask              # 交互式填充未知关联（手动 + LLM）
konceptos llm chat <消息>      # 与 FCA 助手对话
```

### 消解与演化

```bash
konceptos resolve obj <id>     # 展开对象（优先查种子，无则问 LLM）
konceptos resolve attr <id>    # 展开属性（优先查种子，无则问 LLM）
konceptos evolve               # 自动消解 1 个 RW 单元
konceptos evolve <n>           # 自动消解 n 轮
konceptos evolve all           # 持续消解直到 K* 或无法继续
```

### 构建

```bash
konceptos build [输出文件.html]   # 从 FCA 规格生成可运行的 HTML 应用
```

### 快照与系统

```bash
konceptos snaps                # 快照列表
konceptos diff <a> <b>         # 对比两个快照
konceptos rollback <n>         # 回滚到指定快照
konceptos compute              # 重新计算概念格
konceptos save <文件>           # 保存状态到文件
konceptos open <文件>           # 从文件加载状态
konceptos export <文件>         # 导出 FCA 规格为 Markdown
```

## 数据存储

状态存储在当前工作目录的 `.konceptos/state.json` 中，每次执行命令时自动读写。

## 许可证

MIT
