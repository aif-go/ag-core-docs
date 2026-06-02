---
tags:
  - ag-core
  - cli
  - gen-go-db
  - gendb
  - yaml
  - command
---

# gen-go-db yaml 命令详解

> 功能：解析 Excel 模板，生成 YAML 表结构定义文件

## 用途

将标准化的 Excel 表结构模板解析为结构化 YAML 文件。YAML 文件是 `gen-go-db` 流水线的**中间产物**，可直接人工编辑，也可作为 `gen-go-db db` 的输入。

## 命令格式

```bash
gen-go-db yaml -i <excel-path> -o <output-dir> [options]
```

## 参数清单

| 参数 | 缩写 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|:----:|--------|------|
| `--input` | `-i` | string | ✅* | — | Excel 文件路径（测试模式时可选） |
| `--output` | `-o` | string | ✅* | — | 输出基础目录（自动拼接 `repository/yaml/`） |
| `--table` | `-T` | string | ❌ | 全部表 | 指定表名，逗号分隔多个 |
| `--test` | `-t` | bool | ❌ | false | 测试模式，生成示例 YAML 不依赖输入文件 |

> `*` 测试模式（`-t`）下 `-i` 和 `-o` 可选。

## 使用示例

```bash
# 基本用法：单 Excel → 全部表
gen-go-db yaml -i ./模型模板.xlsx -o ./

# 指定表名：只生成 TM_USER
gen-go-db yaml -i ./模型模板.xlsx -o ./ -T TM_USER

# 多表：只生成 TM_USER 和 TM_ORDER
gen-go-db yaml -i ./模型模板.xlsx -o ./ -T "TM_USER,TM_ORDER"

# 测试模式：不依赖 Excel，生成示例供参考
gen-go-db yaml -t
```

## 输出

每个 sheet 生成一个 YAML 文件：

```
{outputDir}/repository/yaml/{SheetName}.yaml
```

## 更多参考

| 主题 | 文档 |
|------|------|
| Excel 模板填写规范 | [[../../代码生成/gendb/08-Excel模板规范\|Excel 模板规范]] |
| YAML 定义格式详解 | [[../../代码生成/gendb/03a-YAML定义格式详解\|表 YAML 定义格式详解]] |
| Excel 解析架构 | [[../../代码生成/gendb/01-Excel解析架构\|Excel 解析架构]] |
