---
tags:
  - ag-core
  - codegen
  - gendb
  - where
  - parser
  - lexer
  - architecture
---

# WHERE 条件解析器

> 文件：`tool/cmd/gen-go-db/excel/parser_where.go` | 将 SQL WHERE 条件字符串解析为嵌套条件树

## 概述

`parser_where.go` 实现了一个微型 SQL WHERE 条件解析器，包含**词法分析器（Lexer）**和**语法分析器（Parser）**，将用户在 Excel 中编写的条件字符串（如 `NAME = @Name AND (SEX = @Sex OR AGE > @Age)`）解析为嵌套的 `WhereClause` 树结构。

## 设计架构

```
输入: "NAME = @Name AND (SEX = @Sex OR AGE > @Age)"
                    │
                    ▼
         ┌──────────────────────┐
         │   Lexer 词法分析器     │
         │   NewLexer(input)     │
         │   NextToken() → Token │
         └──────────┬───────────┘
                    │ Token 流: Expr, AND, LParen, Expr, OR, Expr, RParen
                    ▼
         ┌──────────────────────┐
         │   Parser 语法分析器    │
         │   NewParser(lexer)    │
         │   Parse()            │
         └──────────┬───────────┘
                    │
                    ▼
         WhereClause{Operator: "AND",
           Conditions: [
             {Expr: "NAME = @Name"},
             {Operator: "OR",
               Conditions: [
                 {Expr: "SEX = @Sex"},
                 {Expr: "AGE > @Age"}
               ]
             }
           ]
         }
```

## 词法分析器 (Lexer)

### Token 类型

```go
// parser_where.go:10-18
type TokenType int
const (
    TokenTypeExpr   TokenType = iota // 表达式，如 "NAME = @Name"
    TokenTypeAND                     // AND 操作符
    TokenTypeOR                      // OR 操作符
    TokenTypeIN                      // IN 操作符
    TokenTypeNOTIN                   // NOT IN 操作符
    TokenTypeLParen                  // 左括号 (
    TokenTypeRParen                  // 右括号 )
)
```

### 实现：NextToken()

`NewLexer(input)` 将字符串转为 `[]rune`（支持中文），`NextToken()` 逐个扫描：

1. **跳过空白和逗号**（`parser_where.go:48-51`）
2. **匹配括号** — `(` → LParen, `)` → RParen
3. **匹配 AND** — 前后必须是边界（空格/字符串始末），避免匹配到 BETWEEN 中的 AND
4. **匹配 OR** — 同样检查边界
5. **匹配 NOT IN** — 优先于 IN，6 字符
6. **匹配 IN** — 2 字符
7. **默认作为表达式** — 直到遇到操作符/括号/结束

### 表达式中的特殊处理

在表达式内部，Lexer 会识别 `BETWEEN ... AND` 和 `IN (...)`：

```go
// parser_where.go:122-203
// BETWEEN: 遇到后标记 inBetween=true，内部 AND 跳过
// IN: 标记 inIn=true，括号内的内容作为表达式一部分
// 遇到括号时：inIn 模式下继续，非 inIn 模式则结束表达式
```

## 语法分析器 (Parser)

### 递归下降解析

```go
// parser_where.go:208-296
type Parser struct {
    lexer *Lexer
    curr  *Token
}

func (p *Parser) Parse() *WhereClause {
    return p.parseExpression()
}
```

`parseExpression()` 生成 `WhereClause`：

1. 调用 `parseCondition()` 解析第一个条件
2. 循环解析后续 token：遇到 AND/OR 时记录操作符，解析下一个条件
3. 返回组合后的 WhereClause

`parseCondition()` 处理两种类型：

- **括号嵌套**：遇到 LParen → 递归调用 `parseExpression()` → 消费 RParen
- **表达式**：遇到 Expr → 返回 `Condition{Expr: expr}`

### 嵌套条件树

```go
type WhereClause struct {
    Operator   string       // "AND" 或 "OR"
    Conditions []*Condition // 子条件列表
}

type Condition struct {
    Operator   string       // 嵌套时：逻辑操作符
    Conditions []*Condition // 嵌套条件
    Expr       string       // 叶子节点：条件表达式
}
```

## 示例解析过程

```
输入: "NAME = @Name AND (SEX = @Sex OR AGE > @Age)"

Token 序列:
  Expr("NAME = @Name") → AND → LParen → Expr("SEX = @Sex")
  → OR → Expr("AGE > @Age") → RParen

parseExpression() 第一步:
  parseCondition() → Condition{Expr: "NAME = @Name"}
  添加为第一个条件

parseExpression() 第二步:
  遇到 AND, clause.Operator = "AND"
  parseCondition() → 遇到 LParen
    递归 parseExpression():
      parseCondition() → Condition{Expr: "SEX = @Sex"}
      遇到 OR, clause.Operator = "OR"
      parseCondition() → Condition{Expr: "AGE > @Age"}
    返回 WhereClause{Operator: "OR", Conditions: [...]}
  消费 RParen
  返回 Condition{Operator: "OR", Conditions: [...]}

最终结果:
WhereClause{
  Operator: "AND",
  Conditions: [
    {Expr: "NAME = @Name"},
    {Operator: "OR",
      Conditions: [
        {Expr: "SEX = @Sex"},
        {Expr: "AGE > @Age"}
      ]
    }
  ]
}
```

## 入口函数

```go
// parser_where.go:298-311
func ParseWhereCondition(whereExpr string) *WhereClause {
    whereExpr = strings.TrimSpace(whereExpr)
    if whereExpr == "" { return nil }

    lexer := NewLexer(whereExpr)
    parser := NewParser(lexer)
    return parser.Parse()
}
```

## 调用方

| 调用方 | 位置 |
|--------|------|
| Excel 解析器（普通模式） | `excel/parser.go:processCustomScriptSheet` |
