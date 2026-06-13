---
tags:
  - ag-core
  - codegen
  - gendb
  - yaml
  - reference
---

# 表 YAML 定义格式详解

> 文件格式：`repository/yaml/{TableName}.yaml` | 中间产物，衔接 Excel 解析与 Go 代码生成

## 概述

表 YAML 是 `gen-go-db` 流水线的**中间数据格式**。由 `gen-go-db yaml` 从 Excel 模板生成，再由 `gen-go-db db` 消费生成 Go 代码。其设计目标是：

1. **可读性** — 人类可直接编辑，不受 Excel 模板约束
2. **确定性** — 使用 `yaml.MapSlice` 保证字段顺序固定
3. **自描述** — 包含表结构的全部元信息（列、主键、索引、约束、查询规则）

## 顶层结构

```yaml
table_name: TM_MEDIA_ACT       # ← 必填：数据库表名
columns:                       # ← 必填：列定义列表
  - { column_def }
  - { column_def }
primary_key:                   # ← 可选：主键列名列表
  - SEQ
constraints:                   # ← 可选：约束列表
  - { constraint_def }
  - { constraint_def }
indexes:                       # ← 可选：索引列表
  - { index_def }
  - { index_def }
self_query_rules:              # ← 可选：自定义查询规则
  QueryName:                   #   查询方法名（排序后输出）
    { query_def }
```

## 字段顺序保证

所有字段按固定顺序输出（由 `yaml/generator.go` 中的 `yaml.MapSlice` 控制）：

```
table_name → columns → primary_key → constraints → indexes → self_query_rules
```

每列属性固定顺序：`name → type → [length] → not_null → [default] → auto_increment → support_update → [description] → [tag]`

> `[]` 括起来的字段仅在**非空**时输出，空字符串或 `false` 不输出。  
> ⚠️ 例外：`self_query_rules` 中的 `dynamic_sql` 和 `sql_template` **总是输出**，非动态模板时值为 `false` 和 `""`。

## 列定义（columns）

### 必填字段

```yaml
- name: SEQ                    # 列名（全大写+下划线）
  type: int64                  # Excel 类型（映射到 Go 类型）
  not_null: true               # 是否必填（Y/N）
  auto_increment: true         # 是否自增（Y/N）
  support_update: false        # 是否支持 UPDATE 操作
```

### 可选字段

```yaml
- name: NAME
  type: string
  length: "30"                 # 长度（Excel 中的列长度，仅非空时输出）
  not_null: true
  default: "xxx"               # 默认值（仅非空时输出）
  auto_increment: false
  support_update: true
  description: 姓名             # 描述（仅非空时输出）
  tag: ///@create              # 特殊标记（仅非空时输出）
```

### 类型映射

YAML 中的 `type` 字段来自 Excel 原始填写值，在 Model 解析时通过 `getGoType()` 映射（`model/parser.go:301-324`）：

| YAML type | Go 类型 | 额外导入 |
|-----------|---------|---------|
| `int`, `int32`, `tinyint`, `smallint` | `int` | — |
| `int64`, `bigint` | `int64` | — |
| `float`, `float32`, `double`, `float64`, `decimal` | `float64` | — |
| `string`, `varchar`, `char`, `text` | `string` | — |
| `bool`, `boolean` | `bool` | — |
| `time`, `datetime`, `timestamp`, `date` | `time.Time` | `"time"` |

> `type` 字段直接透传 Excel 填写值，不做校验。`time` 类型需要确保 Excel 中填写的是 `time` 才能映射为 `time.Time`。

### Tag 标记

`tag` 字段影响生成的 GORM 标签。支持三种特殊前缀：

| Tag 值 | 效果 | 生成的 GORM 标签 |
|--------|------|-----------------|
| `///@create` | 标记为自动创建时间字段 | `AUTOCREATETIME` |
| `///@update` | 标记为自动更新时间字段 | `AUTOUPDATETIME` |
| `///@javaVersion` | 标记为乐观锁字段 | 不生成特殊标签，仅用于生成代码中的逻辑判断 |

Tag 判断使用 `strings.Contains()`，因此 `///@create` 可出现在 tag 值的任意位置。

> ⚠️ **`///@omitempty` 注意**：某些 Excel 模板的 Tag 列填写了 `///@omitempty`，但 Model 解析器**不读取此标记**——它既不会在 GORM 标签中生成 `omitempty`，也不会影响任何代码逻辑。此标记仅作为 Excel 中的提示信息使用，写入 YAML 的 `tag` 字段后会被**静默忽略**。

### Model 解析器实际消费的字段

对比 YAML 输出字段和 Model 解析器实际读取的字段：

| YAML 字段 | 被 Model 解析器读取？ | 用途 |
|-----------|:-------------------:|------|
| `name` | ✅ | 列名、JSON tag 名 |
| `type` | ✅ | 映射为 Go 类型 |
| `tag` | ✅（仅 `///@` 前缀） | 标记自动时间、乐观锁 |
| `support_update` | ✅ | 生成 `AllowUpdateCols` |
| `length` | ❌ | 仅中间格式展示 |
| `not_null` | ❌ | 仅中间格式展示 |
| `default` | ❌ | 仅中间格式展示 |
| `description` | ❌ | 仅中间格式展示 |
| `auto_increment` | ❌ | 仅中间格式展示 |

> `length`、`not_null`、`default`、`description`、`auto_increment` 虽然写入 YAML 但不被后续 Model 生成器消费——它们主要作为**人工可读的元信息**保留在中间格式中。

## 主键（primary_key）

```yaml
primary_key:
  - SEQ                     # 主键列名（单主键）
  # - SEQ2                  # 可选：复合主键的第二列
```

- 值为字符串列表，每项是列名
- 不强制要求列在 `columns` 中存在（但生成 Model 时会找不到对应列类型）
- 解析时将对应列的 `IsPrimaryKey` 设为 `true`

## 约束（constraints）

约束被视为**唯一索引**处理，参与 GORM 标签的索引优先级计算：

```yaml
constraints:
  - name: TM_MEDIA_ACT_UNIUQE_1    # 约束名（对应数据库中唯一约束名）
    columns:                        # 约束列
      - CARDNO
      - BIZ_DATE
```

每个约束会被添加到 `IndexData` 切片中，`IsUnique` 设为 `true`，并参与列的 `IndexPriorities` 计算。

## 索引（indexes）

```yaml
indexes:
  - name: INDEX1_TM_MEDOA_ACT     # 索引名
    columns:                       # 索引列（顺序重要——第一列是引导列）
      - BIZ_DATE
      - ACTION_CD
  - name: INDEX2_TM_MEDIA_ACT
    columns:
      - ADDRESS
      - BIZ_DATE
```

索引影响三处代码生成：

1. **GORM 标签** — 每列的 `gorm` tag 中追加 `index:{Name},priority:{N}`
2. **IndexLeadingCols** — 生成 `IndexLeadingCols` 变量，用于 SQL 性能检查
3. **Index Guard** — 自定义查询的 WHERE 条件必须命中至少一个索引的**第一列**（引导列）

### 列的索引优先级

列 `BIZ_DATE` 同时出现在 `INDEX1`（priority 1）和 `INDEX2`（priority 2），其 GORM 标签为：

```
gorm:"column:BIZ_DATE;index:INDEX1_TM_MEDOA_ACT,priority:1;index:INDEX2_TM_MEDIA_ACT,priority:2"
```

## 自定义查询（self_query_rules）

### 普通模式

由 Excel 自定义脚本区的**普通模式**生成：

```yaml
self_query_rules:
  # 查询方法名（按 name 的字符串字典序排列）
  NoPageQuery:
    select_fields: CARDNO,APP_ID,NEW_CARDNO   # 查询字段，逗号分隔
    page: false                                # 是否分页查询
    dynamic_sql: false                         # 始终输出，非动态模板时为 false
    sql_template: ""                           # 始终输出，非动态模板时为空字符串
    where:                                     # WHERE 条件树（可选）
      operator: AND                            # 根操作符
      conditions:                              # 条件列表
        - expr: BIZ_DATE = @BizDate            # 叶子条件：表达式
        - expr: ACTION_CD = @ActionCd          # @ 前缀表示命名参数

  # 分页查询示例
  FindAllColsByPage:
    select_fields: "*"                         # "*" 表示查询全部字段
    page: true                                 # 生成分页 DAO 方法
    dynamic_sql: false
    sql_template: ""
    where:
      operator: AND
      conditions:
        - expr: ADDRESS = @Address
```

#### select_fields

| 值 | 效果 |
|----|------|
| `*` | 查询全部列，生成代码中用主结构体作为结果类型，不生成 `Res` 结构体 |
| `COL1,COL2,...` | 查询指定列，生成对应的 `{MethodName}Res` 结果结构体（仅含这些字段） |

#### page

| 值 | 效果 |
|:--:|------|
| `true` | DAO 方法支持分页，生成 `{MethodName}PageRes` 分页结果结构体，参数中包含 `db.Page` |
| `false` | DAO 方法返回列表（不分页） |

#### WHERE 条件树

支持**无限嵌套**的 AND/OR 逻辑树：

```yaml
self_query_rules:
  Xxxxx:
    select_fields: CARDNO,APP_ID,NEW_CARDNO
    page: true
    where:
      operator: OR                   # 根：OR
      conditions:
        - operator: AND              # 子节点：AND
          conditions:
            - expr: BIZ_DATE = @BizDate
            - expr: ACTION_CD = @ActionCd
        - operator: AND              # 子节点：AND
          conditions:
            - expr: ADDRESS = @Address
            - expr: BIZ_DATE in @BizDateSlice   # IN 查询，参数为切片类型
```

条件节点类型：

| 节点 | 包含字段 | 说明 |
|------|---------|------|
| **叶子** | `expr` | 条件表达式，如 `COL = @Param` |
| **分支** | `operator` + `conditions` | 逻辑组，子节点可以是叶子或分支 |

**命名参数规则：**

- 以 `@` 开头，如 `@Name`、`@BizDate`
- 参数名自动驼峰转换：`BIZ_DATE` → `BizDate`、`ACTION_CD` → `ActionCd`
- `IN`、`NOT IN` 操作符后的参数自动标记为切片类型 `[]Type`
- 支持 `!=`、`=`、`>`、`<`、`>=`、`<=`、`in`、`not in`、`between` 操作符

### 动态模板模式

由 Excel 自定义脚本区的**动态模板模式**生成：

```yaml
self_query_rules:
  QueryByCondition:
    select_fields: "*"
    page: true
    dynamic_sql: true                          # 标记为动态 SQL
    sql_template: >
      SELECT * FROM TM_USER
      WHERE NAME = @Name AND AGE > @Age         # 完整 SQL 模板
    Where_params:                              # 参数定义列表
      - colname: NAME                          # 数据库列名
        paraname: Name                         # Go 字段名
        slice: false                           # 是否为切片
        type: string                           # Go 类型
      - colname: AGE
        paraname: Age
        slice: false
        type: int
```

#### 字段说明

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `select_fields` | ✅ | 同普通模式 |
| `page` | ✅ | 同普通模式 |
| `dynamic_sql` | ✅ | 必须为 `true` |
| `sql_template` | ✅ | 完整 SQL 语句，`@Param` 为参数占位符 |
| `Where_params` | ✅ | 参数定义列表 |

**Where_params 结构：**

| 子字段 | 必填 | 说明 |
|--------|:----:|------|
| `colname` | ✅ | 数据库列名（全大写+下划线） |
| `paraname` | ✅ | Go 字段名（驼峰，对应 `With` 方法参数名） |
| `slice` | ✅ | 是否切片（`IN` 查询时为 `true`） |
| `type` | ✅ | Go 类型（`string`、`int`、`time.Time` 等） |

## 完整示例

一个含有全部可选项的真实 YAML（来自 `TM_MEDIA_ACT.yaml`）：

```yaml
table_name: TM_MEDIA_ACT
columns:
  - name: SEQ
    type: int64
    not_null: true
    auto_increment: true
    support_update: false
  - name: CARDNO
    type: string
    length: "19"
    not_null: true
    auto_increment: false
    support_update: true
    description: 卡号
  - name: CREATED_TIME
    type: time
    not_null: false
    auto_increment: false
    support_update: true
    description: 创建时间
    tag: ///@create               # 自动创建时间
  - name: LAST_MODIFIED_TIME
    type: time
    not_null: false
    auto_increment: false
    support_update: true
    description: 最后更新时间
    tag: ///@update               # 自动更新时间
  - name: JPA_VERSION
    type: int
    not_null: true
    auto_increment: false
    support_update: true
    description: JPA_VERSION      # 乐观锁
primary_key:
  - SEQ
constraints:
  - name: TM_MEDIA_ACT_UNIUQE_1
    columns:
      - CARDNO
      - BIZ_DATE
indexes:
  - name: INDEX1_TM_MEDOA_ACT
    columns:
      - BIZ_DATE
      - ACTION_CD
  - name: INDEX2_TM_MEDIA_ACT
    columns:
      - ADDRESS
      - BIZ_DATE
self_query_rules:
  NoPageQuery:
    select_fields: CARDNO,APP_ID,NEW_CARDNO
    page: false
    where:
      operator: AND
      conditions:
        - expr: BIZ_DATE = @BizDate
        - expr: ACTION_CD = @ActionCd
  Xxxxx:
    select_fields: CARDNO,APP_ID,NEW_CARDNO
    page: true
    where:
      operator: OR
      conditions:
        - operator: AND
          conditions:
            - expr: BIZ_DATE = @BizDate
            - expr: ACTION_CD = @ActionCd
        - operator: AND
          conditions:
            - expr: ADDRESS = @Address
            - expr: BIZ_DATE in @BizDateSlice
```

## 人工编辑建议

YAML 文件设计为**可直接人工编辑**，常见场景：

1. **调整查询字段** — 修改 `select_fields` 值即可
2. **添加条件** — 在 `where.conditions` 下追加 `{expr: "COL = @Param"}`
3. **修改分页** — 切换 `page: true/false`
4. **添加动态 SQL** — 在已有 YAML 中追加 `dynamic_sql` + `sql_template` + `Where_params` 块

> 注意：重新运行 `gen-go-db yaml` 会覆盖 YAML 文件。如有人工编辑，建议只编辑 YAML 后单独运行 `gen-go-db db`。
