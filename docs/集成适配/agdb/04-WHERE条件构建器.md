---
tags:
  - ag-core
  - agdb
  - conditonwhere
  - where
  - fieldmask
  - architecture
---

# WHERE 条件构建器

> 路径：`conditonwhere/`

提供两套 WHERE 条件构建机制：**WhereClauseBuilder（V2 链式 API）** 和 **FieldMask（动态字段过滤）**。

```
conditonwhere/
├── where_clause_builder.go         # V2 链式 WHERE 构建器（主推）
├── where_clause_builder_test.go    # 测试
├── where_builder_v2_test.go        # V2 测试
├── where_builder_v2_example.go     # V2 示例
├── where_builder_index_test.go     # 索引测试
├── fieldmask.go                    # FieldMask + MaskWhereCondition
├── build_where.go                  # NhWhere 高性能正则过滤
├── where.go                        # (已废弃)
└── condition.go                    # (已废弃)
```

---

## WhereClauseBuilder（V2 链式 API）

> 推荐使用。文件：`where_clause_builder.go`

一个**链式调用的 WHERE 条件构建器**，支持嵌套分组和多操作符。

### 操作符

```go
// where_clause_builder.go:14-24
SQLOpEq      SQLOperator = "="
SQLOpNeq     SQLOperator = "!="
SQLOpGt      SQLOperator = ">"
SQLOpLt      SQLOperator = "<"
SQLOpGte     SQLOperator = ">="
SQLOpLte     SQLOperator = "<="
SQLOpIn      SQLOperator = "in"
SQLOpNotIn   SQLOperator = "not in"
SQLOpBetween SQLOperator = "between"
```

### 链式 API

```go
// where_clause_builder.go:104-248
builder.Eq(field, value)        // =
builder.Neq(field, value)       // !=
builder.Gt(field, value)        // >
builder.Lt(field, value)        // <
builder.Gte(field, value)       // >=
builder.Lte(field, value)       // <=
builder.In(field, values...)    // IN
builder.NotIn(field, values...) // NOT IN
builder.Between(field, min, max) // BETWEEN
builder.Or()                    // 下一个条件为 OR
builder.And()                   // 下一个条件为 AND
```

### 嵌套分组

```go
builder.BeginGroup()     // 开始一个组
    // ... 组内条件
builder.EndGroup()       // 结束当前组

// 便捷方法
builder.AndGroup(conds...)   // AND 分组
builder.OrGroup(conds...)    // OR 分组
builder.Group(conds...)      // 通用分组
```

### 完整示例

```go
// where_clause_builder.go 中的模式
builder := NewWhereClauseBuilder()
sql, args, err := builder.
    Eq("status", 1).
    Or().
    BeginGroup().
        Gte("amount", 100).
        Lt("amount", 500).
    EndGroup().
    Build()
// sql:  "status = ? OR (amount >= ? AND amount < ?)"
// args: [1, 100, 500]
```

### 构建原理

`Build()` 递归调用 `buildWhereCondition()`，对每个 `WhereCondition` 节点：

1. 如果是纯嵌套组（无 Field，有 Children）→ 调用 `buildNestedGroup()`，始终用括号包裹
2. 如果有 Field → 调用 `buildSingleCondition()` 生成 `column OP ?`
3. 如果有 Children → 递归构建子条件，用每个子条件的 Logic 连接

**括号策略**（`needParentheses` 行 451-464）：
- 仅当**同时存在 OR 和 AND** 时才加括号保证优先级
- 避免不必要的括号（如单一条件或相同运算符时不加）

---

## FieldMask — 动态字段过滤

> 文件：`fieldmask.go`

类似 MyBatis 的 `<if test="xxx != null">` 动态条件过滤机制。

### 基本用法

```go
// fieldmask.go:73-82
type FieldMask struct {
    fields map[string]bool
}

fm := NewFieldMask()
fm.Set("OrderId")           // 标记 OrderId 已设置
fm.Set("MerchantId")        // 标记 MerchantId 已设置

// 从全局配置中获取方法对应的 WHERE 条件，按 FieldMask 过滤
sql, err := fm.BuildWhereFromConfig("FindByOrder", conditionMap)
// 只生成 OrderId 和 MerchantId 的条件
```

### MaskWhereCondition — 树状条件结构

```go
// fieldmask.go:11-15
type MaskWhereCondition struct {
    Operator   string              // AND / OR
    Conditions []MaskWhereCondition // 子条件（嵌套）
    Expr       string              // 叶子节点：表达式，如 "ORDER_ID = @OrderId"
}
```

支持树状嵌套的 WHERE 条件结构：

```json
{
  "operator": "AND",
  "conditions": [
    { "expr": "ORDER_ID = @OrderId" },
    { "expr": "MERCHANT_ID = @MerchantId" },
    { "expr": "STATUS = @Status" },
    {
      "operator": "OR",
      "conditions": [
        { "expr": "AMOUNT >= @MinAmount" },
        { "expr": "AMOUNT <= @MaxAmount" }
      ]
    }
  ]
}
```

### 过滤逻辑

`FilterMaskWhereCondition`（行 196-244）：
1. 叶子节点（有 `Expr`）→ 提取参数名 → 检查 FieldMask 是否设置
2. 非叶子节点 → 递归过滤所有子条件
3. 所有子条件都被过滤掉 → 返回 nil
4. **最终生成 WHERE SQL**：`GenerateWhereSQL()` 递归展开为 `(... AND ... OR ...)`

### 全局配置注册

```go
// fieldmask.go:47-69
var WhereConfigMap = struct {
    sync.RWMutex
    data map[string]*MaskWhereCondition
}{}

func RegisterWhereConfig(methodName string, whereData *MaskWhereCondition)
func GetWhereConfig(methodName string) (*MaskWhereCondition, bool)
```

**线程安全**：读写锁保护，并发安全。

### BuildWhereSQL — 简单列表构建

```go
// fieldmask.go:250-259
func BuildWhereSQL(conditions []string, operator string) string
// 输入: ["ORDER_ID = @OrderId", "MERCHANT_ID = @MerchantId"]
// 输出: WHERE (ORDER_ID = @OrderId AND MERCHANT_ID = @MerchantId)
```

---

## NhWhere — 高性能 WHERE 过滤

> 文件：`build_where.go`

用于**对入参级别的 WHERE 字符串进行字段级过滤**：

```go
// build_where.go:66-140
func NewWhere(where string, fieldMask *FieldMask) (string, error)
```

**输入输出示例**：
```
输入: "a = @a and (b = @b or c = @c)"
FieldMask: {a: true, b: true}
输出: "a = @a and (b = @b)"       // c 被过滤掉
```

**性能优化**：
- `sync.Once` 初始化预编译正则（避免 `init()` 开销）
- 单次 `FindAllStringSubmatchIndex` 扫描提取所有条件单元
- 使用 `strings.Builder` 构建新条件（避免字符串拼接）
- 轻量清理：去多余空格、去空括号、清理连续逻辑运算符

### ValidateLeadingCol — 索引前导列校验

```go
// fieldmask.go:298-311
func ValidateLeadingCol(sql string, leadingCols []string) bool
```

检查 SQL 中是否包含索引前导列，用于**避免全表扫描**。如果未包含任何前导列，说明这个查询可能会走全表扫描，应该拦截或告警。
