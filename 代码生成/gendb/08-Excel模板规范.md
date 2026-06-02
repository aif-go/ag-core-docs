---
tags:
  - ag-core
  - codegen
  - gendb
  - excel
  - template
  - reference
---

# Excel 模板规范

> 面向业务开发者：如何编写标准化的 Excel 表结构模板，供 `gen-go-db yaml` 解析。

## 概述

每个 sheet 对应一张数据库表。解析器按标记行切换区域，依次识别六大区域。

## ① 表头

| 表名 | |
|------|------|
| `表名` | `TM_USER` |

- **Sheet 名**：建议与表名一致
- **第一行**：声明表名

## ② 列定义区（标题行：`列名`）

| 列名 | 类型 | 长度 | 必填 | 默认值 | 自增 | 支持更新 | 描述 | Tag |
|------|------|------|------|--------|------|---------|------|-----|
| SEQ | int64 | | Y | | Y | N | 序列号 | |
| NAME | string | 30 | Y | | N | Y | 姓名 | |
| SEX | int | | N | 1 | N | Y | 1-男 2-女 | |
| CREATED_TIME | time | | N | | N | N | 创建时间 | `///@create` |
| LAST_MODIFIED_TIME | time | | N | | N | N | 更新时间 | `///@update` |

### 列说明

| 列 | 填写规则 |
|----|---------|
| 列名 | 大写字母+下划线，建议与数据库一致 |
| 类型 | 见下方类型对照表 |
| 长度 | 字符串类型时需要 |
| 必填 | `Y`=NOT NULL, `N`=允许 NULL |
| 默认值 | 不填则无默认值 |
| 自增 | `Y`=自增主键适用 |
| 支持更新 | `Y`=允许 UPDATE 修改此列 |
| 描述 | 业务含义 |
| Tag | `///@create` / `///@update` / `///@javaVersion` |

## ③ 主键区（标题行：`主键`）

| | |
|------|------|
| `PRIMARY_KEY` | `SEQ` |（可选第二主键）|

多个主键列依次写在后续列中。

## ④ 索引区（标题行：`索引`）

| | | |
|------|------|------|
| `INDEX1_TM_USER` | `NAME` | `ADDRESS` |
| `INDEX2_TM_USER` | `STATUS` | `CREATED_TIME` |

- 第一列为索引名，后续列为索引列
- **第一列是引导列**，自定义查询必须命中

## ⑤ 约束区（标题行：`约束`）

| | |
|------|------|
| `TM_USER_PHONE_UNIQUE` | `PHONE` |

- 约束会被作为**唯一索引**处理（`IsUnique: true`）

## ⑥ 自定义脚本区

定义在 `{sheetName}@` 命名的附属 sheet 中。

### 普通模式

| 方法名 | 查询字段 | 排序 | 条件 | SQL 参数 | 分页 |
|--------|---------|------|------|---------|------|
| FindByName | NAME,ADDRESS | | NAME = @Name | | Y |
| FindAll | * | SEQ DESC | | | N |

**条件语法：**
- `@` 前缀表示参数绑定，如 `@Name`、`@Age`
- 支持 AND/OR 嵌套和括号分组
- 支持操作符：`=`、`!=`、`>`、`<`、`>=`、`<=`、`in`、`not in`、`between`

### 动态模板模式

首行标记 `动态模版`。

| 方法名 | 查询字段 | SQL 模板 | 参数定义 | 排序 | 分页 |
|--------|---------|---------|---------|------|------|
| QueryByCondition | * | `SELECT * FROM TM_USER WHERE NAME = @Name AND AGE > @Age` | `Name,string,N;Age,int,N` | | Y |

**参数定义格式：** `属性名,类型,是否切片(Y/N)[,列名]`，分号分隔多个。

> ⚠️ SQL 模板中不允许出现 `1 = 1` 条件。

## 类型对照表

| Excel 类型 | Go 类型 |
|-----------|---------|
| `int64`、`bigint` | `int64` |
| `int`、`int32`、`tinyint`、`smallint` | `int` |
| `float`、`float32`、`double`、`float64`、`decimal` | `float64` |
| `string`、`varchar`、`char`、`text` | `string` |
| `bool`、`boolean` | `bool` |
| `time`、`datetime`、`timestamp`、`date` | `time.Time` |

## Tag 标记

| Tag | 效果 |
|-----|------|
| `///@create` | GORM 标签追加 `AUTOCREATETIME` |
| `///@update` | GORM 标签追加 `AUTOUPDATETIME` |
| `///@javaVersion` | 乐观锁标记 |
| `///@omitempty` | ⚠️ **无效标记，被解析器忽略** |

## 输出

每个 sheet 生成一个 YAML 文件：

```
{outputDir}/repository/yaml/{SheetName}.yaml
```

YAML 结构示例（`TM_USER.yaml`）：

```yaml
table_name: TM_USER
columns:
  - name: SEQ
    type: int64
    not_null: true
    auto_increment: true
    support_update: false
  - name: NAME
    type: string
    length: "30"
    not_null: true
    support_update: true
    description: 姓名
primary_key:
  - SEQ
indexes:
  - name: INDEX1_TM_USER
    columns: [NAME, ADDRESS]
self_query_rules:
  FindByName:
    select_fields: NAME,ADDRESS
    page: true
    dynamic_sql: false
    sql_template: ""
    where:
      operator: AND
      conditions:
        - expr: NAME = @Name
```

详细 YAML 格式说明见 [[03a-YAML定义格式详解|表 YAML 定义格式详解]]。

## 内部解析实现

| 组件 | 文件 | 职责 |
|------|------|------|
| 入口函数 | `yaml/generator.go:GenerateYAMLFromExcel` | 调度 Excel 解析 + YAML 写入 |
| Excel 解析 | `excel/parser.go:ParseExcel` | 按区域提取表结构 |
| WHERE 解析 | `excel/parser_where.go` | 条件字符串 → 嵌套条件树 |
| 序列化 | `yaml/generator.go:GenerateYAML` | ExcelInfo → yaml.MapSlice → YAML |
