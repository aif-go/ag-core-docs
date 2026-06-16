---
tags:
  - ag-core
  - codegen
  - gendb
  - model
  - template
  - architecture
---

# Model 代码生成引擎

> 文件：`tool/cmd/gen-go-db/model/` (`parser.go` + `template.go` + `generator.go`) | YAML 定义 → Go ORM Model 代码

## 概述

Model 代码生成引擎将 YAML 表结构定义文件解析为 Go 结构体代码，包含表模型、主键类型、ORM 标签、辅助方法以及自定义查询参数/结果结构体。

## 职责链

```
YAML 文件
  │
  ▼
model/parser.go: ParseYAML()
  │  类型映射 + GORM tag 生成 + 索引/约束处理 + 自定义查询解析
  │  → table.TableData
  ▼
model/generator.go: GenerateModel()
  │  索引安全检查 (checkQueryArgsIndexes)
  │  → 调用 GetModelTemplate()
  ▼
model/template.go: GetModelTemplate()
  │  字符串拼接 → 完整 .go 文件
  ▼
repository/model/{table}_model.go
```

## 一、YAML 解析器（model/parser.go）

### ParseYAML 流程

```go
// model/parser.go:15-285
func ParseYAML(yamlPath string, moduleName string) (*table.TableData, error)
```

1. 读取 YAML 文件 → `yaml.Unmarshal` 到 `map[interface{}]interface{}`
2. 提取 `table_name` → `ToCamelCase()` 转换为 Go 结构体名
3. 遍历 `columns` → 生成 `ColumnData` 切片
4. 处理 `indexes` + `constraints` → 更新 `IndexData` 和列的 `IndexPriorities`
5. 处理 `primary_key` → 设置 `IsPrimaryKey` 标志
6. 生成 GORM 标签（`generateGormTag`）
7. 处理 `self_query_rules` → 解析 WHERE 条件，生成 `QueryData`
8. 返回 `TableData`

### 类型映射

```go
// model/parser.go:301-324
func getGoType(sqlType string) string
```

| Excel 类型 | Go 类型 |
|-----------|---------|
| `int`, `int32`, `tinyint`, `smallint` | `int` |
| `int64`, `bigint` | `int64` |
| `float`, `float32`, `double`, `float64`, `decimal` | `float64` |
| `string`, `varchar`, `char`, `text` | `string` |
| `bool`, `boolean` | `bool` |
| `time`, `datetime`, `timestamp`, `date` | `time.Time` |

`time.Time` 类型自动添加 `"time"` 到导入包列表。

### Tag 处理

```go
// model/parser.go:67-77
if strings.Contains(tag, "///@create") {
    col.IsAutoCreate = true      // → GORM AUTOCREATETIME
}
if strings.Contains(tag, "///@update") {
    col.IsAutoUpdate = true      // → GORM AUTOUPDATETIME
}
if strings.Contains(tag, "///@javaVersion") {
    col.IsJavaVersion = true     // → 乐观锁标记
}
```

### GORM 标签生成

```go
// model/parser.go:430-458
func generateGormTag(col *table.ColumnData, indexes []table.IndexData) string
```

组合规则：

```
column:{Name};[primaryKey];[not null];[AUTOCREATETIME];[AUTOUPDATETIME];[index:{Name},priority:{N}]
```

示例：`column:SEQ;primaryKey;not null`
示例：`column:NAME;index:INDEX1_TM_USER,priority:1`

### WHERE 条件解析

YAML 中的 WHERE 条件通过 `conditonwhere.ParseWhereCondition()` 解析（从 `contribute/agdb/conditonwhere` 搬入的自包含包 `tool/cmd/gen-go-db/conditonwhere/`），然后通过 `extractWhereFields()` 递归提取所有列名和操作符：

```go
// model/parser.go:371-386
func extractWhereFields(condition *conditonwhere.MaskWhereCondition,
    fields *[]string, whereColFields *[]table.WhereColField)
```

`parseWhereExpr()` 解析单个表达式，提取列名、操作符和 `@` 参数名：

```go
// model/parser.go:389-427
// 支持操作符（按长度降序优先匹配）:
// !=, not in, in, =, >, <, >=, <=, between
```

IN / NOT IN 操作符自动标记 `IsSlice=true`。

## 二、Model 生成器（model/generator.go + template.go）

### GenerateModel

```go
// model/generator.go:11-26
func GenerateModel(data *table.TableData, outputPath string) error
```

1. `checkQueryArgsIndexes(data)` — 索引安全检查
2. `GetModelTemplate(data)` — 生成完整代码
3. `os.WriteFile(outputPath, modelCode)`

### 索引安全检查（index guard）

```go
// model/generator.go:28-94
func checkQueryArgsIndexes(data *table.TableData) error
```

校验每个自定义查询的 WHERE 条件：

1. **优先检查主键** — 如果 WHERE 字段命中主键列，通过
2. **检查索引引导列** — 未命中主键时，检查是否包含任意索引的第一列
3. **复合主键规则** — 如果命中非第一个主键但未命中第一个，给出警告
4. **未命中报错** — 阻止生成，防止全表扫描

### 模板结构（GetModelTemplate）

`model/template.go:594-667` 按顺序拼接代码片段：

```go
func GetModelTemplate(tableData *table.TableData) string {
    // 1. package model
    // 2. import 语句（自动判断需要导入的包）
    // 3. 主结构体
    // 4. 主键类型
    // 5. TableName() 方法
    // 6. Clone() 方法
    // 7. ListZeroValueCols() 方法
    // 8. ToString() 方法
    // 9. AllowUpdateCols 变量
    // 10. IndexLeadingCols 变量
    // 11. 自定义查询代码（Arg 结构体 + With 方法 + Res 结构体）
    // 12. WhereDataToYAMLCache + init() 函数
}
```

### 各生成函数

| 函数 | 生成内容 | 行号 |
|------|---------|------|
| `generateStruct` | 主结构体，含 GORM + JSON 标签 | `template.go:60-74` |
| `generatePrimaryKeyType` | 单主键类型别名 / 多主键结构体 | `template.go:77-105` |
| `generateTableNameMethod` | `TableName()` 返回表名 | `template.go:108-116` |
| `generateCloneMethod` | `Clone()` 逐字段复制 | `template.go:119-137` |
| `generateListZeroValueColsMethod` | 按主键/索引/特殊列/普通列分层检查零值 | `template.go:193-281` |
| `generateToStringMethod` | `ToString()` 格式化输出 | `template.go:284-295` |
| `generateAllowUpdateCols` | 支持更新的列名列表变量 | `template.go:298-312` |
| `generateIndexLeadingCols` | 索引前导列列表（用于 SQL 性能检查） | `template.go:315-336` |

### 自定义查询代码生成

`generateQueryCode()` 遍历所有 `SelfQueries`，为每个查询生成：

| 函数 | 生成内容 |
|------|---------|
| `generateQueryArgStruct` | 查询参数结构体（含 FieldMask + 可选 Page） |
| `generateWithMethods` | 链式 With 方法（setter + FieldMask.Set） |
| `generateConvertToMapMethod` | 参数转 map |
| `generateQueryResStruct` | 查询结果结构体（非 `*` 查询时） |
| `generatePageResStruct` | 分页结果结构体 |

### 导入项自动管理

`generateImports()` 按需生成导入语句：

```go
// template.go:24-57
// 基础: "fmt"
// HasPage → db "github.com/aif-go/ag-core/contribute/agdb/gormdb"
// HasSelfQuery → "github.com/aif-go/ag-core/contribute/agdb/conditonwhere"
// WhereDataToYAMLCache → "gopkg.in/yaml.v2"
// time.Time 列 → "time"
```

## 渲染数据结构

`table.TableData` 是模板渲染的完整数据上下文（`table/table.go`）：

```go
type TableData struct {
    ModuleName        string              // go.mod 模块名
    TableName         string              // 数据库表名
    StructName        string              // Go 结构体名（大驼峰）
    Columns           []ColumnData        // 列定义
    PrimaryKeys       []string            // 主键列表
    Indexes           []IndexData         // 索引列表
    SelfQueries       []QueryData         // 自定义查询
    HasPage           bool                // 是否有分页查询
    HasSelfQuery      bool                // 是否有自定义查询
    AllowUpdateCols   []string            // 支持更新的列
    ModelTemplateData *ModelTemplateData  // 导入包信息
}
```
