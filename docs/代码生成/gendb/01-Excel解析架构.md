---
tags:
  - ag-core
  - codegen
  - gendb
  - excel
  - parser
  - architecture
---

# Excel 解析架构

> 文件：`tool/cmd/gen-go-db/excel/parser.go` + `excel.go` | 将 Excel 模板解析为结构化表信息

## 概述

Excel 解析器负责读取标准化 Excel 模板，按区域标记**逐行解析**，提取表结构信息（列定义、主键、索引、约束、自定义查询规则）。

## 数据模型

定义在 `excel/excel.go`：

```go
// ExcelInfo 单张表的结构信息
type ExcelInfo struct {
    Name        string                    // 表名（来自 sheet 名）
    Columns     []*ColumnInfo             // 列定义列表
    PrimaryKey  []string                  // 主键列名列表
    Constraints []*ConstraintInfo         // 约束列表
    Indexes     []*IndexInfo              // 索引列表
    SelfQueries map[string]*SelfQueryInfo // 自定义查询映射（方法名 → 查询定义）
}

// ColumnInfo 单列定义
type ColumnInfo struct {
    Name          string // 列名
    Type          string // Excel 类型（如 int64, string, time）
    Length        string // 长度（如 "20", "100"）
    NotNull       bool   // 是否必填
    Default       string // 默认值
    AutoIncrement bool   // 是否自增
    SupportUpdate bool   // 是否支持更新
    Description   string // 描述
    Tag           string // 特殊标记（///@create 等）
}

// ConstraintInfo 约束定义（唯一索引）
type ConstraintInfo struct {
    Name    string   // 约束名
    Columns []string // 约束列列表
}

// IndexInfo 索引定义
type IndexInfo struct {
    Name    string   // 索引名
    Columns []string // 索引列列表
}

// SelfQueryInfo 自定义查询定义
type SelfQueryInfo struct {
    SelectFields    string        // 查询字段（"*" 或逗号分隔）
    Where           *WhereClause  // WHERE 条件树
    Page            bool          // 是否需要分页
    DynamicTemplate bool          // 是否动态 SQL 模板模式
    Order           string        // 排序条件
    WhereParams     []*WhereParam // 动态模板参数
    SqlTemplate     string        // 动态 SQL 模板
}
```

## 区域解析器

`parser.go` 中的 `ParseExcel()` 按固定顺序识别 Excel 行中的区域标记：

```
每一行的 row[0] 决定当前区域：
────────────────────────────────────────────────────
"表名"        → 设置 table.Name = row[1]
"列名"        → 进入列定义区
"主键"        → 进入主键区
"约束"        → 进入约束区
"索引"        → 进入索引区
"方法名字"    → 进入自定义查询区（由附属 sheet 处理）
```

### 状态切换

```go
inColumns := false
inPrimaryKey := false
inConstraints := false
inIndexes := false

// 每遇到标记行切换状态：
row[0] == "列名"  → inColumns=true, 其他 false
row[0] == "主键"  → inPrimaryKey=true, 其他 false
// ...以此类推
```

### 列定义解析

每行数据格式：`列名 | 类型 | 长度 | 必填(Y/N) | 默认值 | 自增(Y/N) | 支持更新(Y/N) | 描述 | Tag`

```go
// parser.go:108-121
column := &ColumnInfo{
    Name:          row[0],
    Type:          row[1],
    Length:        row[2],
    NotNull:       row[3] == "Y",
    Default:       row[4],
    AutoIncrement: row[5] == "Y",
    SupportUpdate: row[6] == "Y",
    Description:   row[7],
    Tag:           row[8],
}
```

### 主键解析

```go
// parser.go:125-133
// row[0] == "PRIMARY_KEY" 时解析后续列
// 遍历 row[1:] 获取多主键
```

### 索引/约束解析

```go
// parser.go:152-169
// row[0] = 索引名，row[1:] = 列列表
// 跳过 "自定义脚本名字" 标记行
```

## 自定义脚本解析

自定义查询定义在 `{sheetName}@` 命名附属 sheet 中，由 `processCustomScriptSheet()` 处理。

### 普通模式

```go
// parser.go:202-214
query := &SelfQueryInfo{
    SelectFields: row[1],
    Page:         row[7] == "Y",
}
whereExpr := row[4]
query.Where = ParseWhereCondition(whereExpr)
```

| Excel 列 | 索引 | 说明 |
|----------|------|------|
| 方法名 | row[0] | 查询方法名 |
| 查询字段 | row[1] | 逗号分隔或 `*` |
| 排序 | row[2] | 排序条件 |
| 条件 | row[4] | WHERE 表达式（如 `NAME = @Name`） |
| SQL 参数 | row[5] | 可选参数描述 |
| 分页 | row[7] | `Y`/空 |

### 动态模板模式

首行标记为 `动态模版` 时进入此模式。

```go
// parser.go:229-248
query := &SelfQueryInfo{
    SelectFields:    row[1],
    SqlTemplate:     row[2],
    Page:            row[5] == "Y",
    Order:           row[4],
    DynamicTemplate: true,
}
query.WhereParams = processWhereParam(query.SqlTemplate, row[3], table)
```

参数定义格式：`属性名,类型,是否切片(Y/N)[,列名]`，分号分隔多个参数。

`processWhereParam()` 自动从 SQL 模板中提取 `@ParamName` 占位符，未显式指定类型的参数从列名驼峰匹配。

> **安全限制**：SQL 模板中不允许出现 `1 = 1` 条件（`parser.go:255-257`）。

## 调用关系

```
ParseExcel(filePath)
  │
  ├── 遍历每个 sheet
  │     ├── 跳过 @custom 后缀 sheet
  │     ├── 逐行解析：识别区域 → 提取数据
  │     └── processCustomScriptSheet()
  │           ├── 普通模式 → ParseWhereCondition()
  │           │     调用 excel/parser_where.go
  │           └── 动态模板模式 → processWhereParam()
  │                 正则提取 @Param → 匹配列类型
  │
  └── 返回 map[sheetName]*ExcelInfo
```
