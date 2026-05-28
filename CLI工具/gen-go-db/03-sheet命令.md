---
tags:
  - ag-core
  - cli
  - gen-go-db
  - gendb
  - sheet
  - command
---

# gen-go-db sheet 命令详解

> 功能：将 Excel 模板中的自定义脚本部分拆分为独立的 sheet

## 用途

辅助工具。将一个 sheet 中自定义查询/脚本部分拆分到独立的 `{sheetName}@` sheet 中，方便 Excel 模板的组织和维护。

## 背景

在 Excel 模板中，表结构定义和自定义查询脚本通常放在同一个 sheet 中。`gen-go-db yaml` 要求自定义脚本放在 `{sheetName}@` 命名的独立 sheet 中。`gen-go-db sheet` 命令自动完成这个拆分操作。

## 命令格式

```bash
gen-go-db sheet -i <excel-path> -o <output-dir> [options]
```

## 参数清单

| 参数 | 缩写 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|:----:|--------|------|
| `--input` | `-i` | string | ✅ | — | Excel 文件路径 |
| `--output` | `-o` | string | ✅ | — | 输出目录 |
| `--keyword` | `-k` | string | ❌ | `自定义脚本名字` | 拆分关键字，匹配到该行的内容被拆分 |

## 使用场景

### 场景 1：将旧版模板拆分为标准格式

原始 Excel 中，`TM_USER` sheet 同时包含表结构定义和自定义脚本。运行拆分命令：

```bash
gen-go-db sheet -i ./旧版模板.xlsx -o ./拆分后
```

生成新的 Excel 文件，其中：
- `TM_USER` sheet → 仅保留表结构定义
- `TM_USER@` sheet → 包含拆分出的自定义脚本

### 场景 2：指定自定义关键字

如果模板中的自定义脚本行标记不是默认的 `自定义脚本名字`，可以用 `-k` 指定：

```bash
gen-go-db sheet -i ./模板.xlsx -o ./拆分后 -k "自定义规则"
```

## 拆分逻辑

```
输入 sheet: TM_USER
  ┌──────────────────────────────┐
  │ 表名    TM_USER               │
  │ 列名  类型  ...               │
  │ ...                          │
  │ 方法名字  查询字段  条件  ...   │  ← 从 "自定义脚本名字" 行开始
  │ FindByName  NAME  ...        │     后面的内容被拆分
  └──────────────────────────────┘
                │
                ▼
输出 sheet 1: TM_USER
  ┌──────────────────────────────┐
  │ 表名    TM_USER               │
  │ 列名  类型  ...               │
  │ ...                          │
  └──────────────────────────────┘

输出 sheet 2: TM_USER@
  ┌──────────────────────────────┐
  │ 方法名字  查询字段  条件  ...   │
  │ FindByName  NAME  ...        │
  └──────────────────────────────┘
```

## 使用流程

```bash
# 1. 拆分 Excel
gen-go-db sheet -i ./模型模板.xlsx -o ./拆分后

# 2. 用拆分后的 Excel 生成 YAML
gen-go-db yaml -i ./拆分后/模型模板.xlsx -o ./
```

## 内部实现

| 组件 | 文件 | 职责 |
|------|------|------|
| 入口 | `other/split_excel.go:SplitExcelByKeyword` | 按关键字拆分 sheet |
