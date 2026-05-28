---
tags:
  - ag-core
  - codegen
  - gendb
  - yaml
  - architecture
---

# YAML 生成器

> 文件：`tool/cmd/gen-go-db/yaml/generator.go` | 将 ExcelInfo 结构序列化为 YAML 定义文件

## 概述

YAML 生成器接收 `excel.ParseExcel()` 返回的 `map[string]*ExcelInfo`，将每张表的定义信息序列化为 YAML 文件，存放在 `repository/yaml/` 目录下。YAML 文件是 Excel 模板和 Go 代码生成之间的**中间产物**。

## 职责链

```
Excel 模板 → excel.ParseExcel() → map[string]*ExcelInfo
                                       │
                                       ▼
                              yaml.GenerateYAMLFromExcel()
                                       │
                            ┌──────────┴──────────┐
                            │  每张表一个 YAML 文件  │
                            ▼                     ▼
                     repository/yaml/TM_USER.yaml
                     repository/yaml/TM_ORDER.yaml
```

## 入口：GenerateYAMLFromExcel

```go
// yaml/generator.go:60-119
func GenerateYAMLFromExcel(inputFile string, outputDir string, testMode bool, tableName string) error
```

| 参数 | 说明 |
|------|------|
| `inputFile` | Excel 文件路径 |
| `outputDir` | 输出基础目录（自动拼接 `repository/yaml/`） |
| `testMode` | 测试模式，生成示例 TM_TEST 表 |
| `tableName` | 指定表名过滤（逗号分隔） |

流程：

1. 创建输出目录 `{outputDir}/repository/yaml/`
2. 调用 `excel.ParseExcel(inputFile)` 解析 Excel
3. 按 `tableName` 过滤（支持逗号分隔多个表）
4. 每张表调用 `GenerateYAML(table, yamlPath)`

## 序列化：GenerateYAML

```go
// yaml/generator.go:304-451
func GenerateYAML(table *excel.ExcelInfo, outputPath string) error
```

使用 `yaml.MapSlice`（而非 `map[string]interface{}`）保证 YAML 输出字段的**固定顺序**。

### 输出结构

```yaml
table_name: TM_TEST          ← 表名（最上方）
columns:                     ← 列定义（固定顺序）
  - name: SEQ
    type: int64
    not_null: true
    auto_increment: true
    support_update: false
primary_key:                 ← 主键（如有）
  - SEQ
constraints:                 ← 约束（如有，按 name 排序）
  - name: TM_TEST_UNIUQE_1
    columns: [PHONE]
indexes:                     ← 索引（如有，按 name 排序）
  - name: INDEX1_TM_TEST
    columns: [NAME, ADDRESS]
self_query_rules:            ← 自定义查询（如有，按 name 排序）
  FindAllColsByPage:
    select_fields: "*"
    page: true
    where:
      operator: AND
      conditions:
        - expr: "ADDRESS = @Address"
```

### 字段顺序保证

每个块内使用 `yaml.MapSlice` 严格控制 key 顺序：

```go
// yaml/generator.go:306-343
data := yaml.MapSlice{}
data = append(data, yaml.MapItem{Key: "table_name", Value: table.Name})

// 列定义顺序固定
columnData := yaml.MapSlice{}
columnData = append(columnData, yaml.MapItem{Key: "name", Value: col.Name})
columnData = append(columnData, yaml.MapItem{Key: "type", Value: col.Type})
if col.Length != "" {
    columnData = append(columnData, yaml.MapItem{Key: "length", Value: col.Length})
}
columnData = append(columnData, yaml.MapItem{Key: "not_null", Value: col.NotNull})
// ...
```

### WHERE 条件序列化

`generateWhereCondition()` 递归将 `Condition` 树序列化为 YAML：

```go
// yaml/generator.go:41-57
func generateWhereCondition(cond *excel.Condition) yaml.MapSlice {
    condData := yaml.MapSlice{}
    if cond.Expr != "" {
        condData = append(condData, yaml.MapItem{Key: "expr", Value: cond.Expr})
    }
    if cond.Operator != "" {
        condData = append(condData, yaml.MapItem{Key: "operator", Value: cond.Operator})
        // 递归处理嵌套条件
        for _, subCond := range cond.Conditions {
            subConditions = append(subConditions, generateWhereCondition(subCond))
        }
    }
    return condData
}
```

### 自定义查询排序

为保证 YAML 输出确定性，查询名按字典序排序：

```go
// yaml/generator.go:378-384
queryNames := make([]string, 0, len(table.SelfQueries))
for name := range table.SelfQueries {
    queryNames = append(queryNames, name)
}
sort.Strings(queryNames)
```

## 测试数据生成

`generateTestData()` 创建一个 `TM_TEST` 示例表，含全类型列、主键、约束、索引和 4 个自定义查询，用于 `-t` 测试模式。

## YAML 文件命名规则

```
repository/yaml/{sheetName}.yaml
```
