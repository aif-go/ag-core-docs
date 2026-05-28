---
tags:
  - ag-core
  - ag-ext
  - config
  - flatten
---

# 配置展开 — GetFlattenedMap

> 文件：`ag/ag_ext/util.go`

## 职责

将嵌套的 `map[string]any` 展开为扁平的 `map[string]any`，key 使用点号分隔。用于配置文件加载阶段（YAML/JSON 的 `map` 结构 → CLI 友好的扁平 key）。

## API

```go
func GetFlattenedMap(source interface{}) (map[string]interface{}, error)
```

## 展开规则

```yaml
# 展开前（YAML 嵌套）
app:
  name: my-service
  server:
    port: 8080
  datasource:
    mysql:
      url: jdbc:mysql://localhost:3306/db
```

```go
// 展开后
map[string]any{
    "app.name":                "my-service",
    "app.server.port":         8080,
    "app.datasource.mysql.url": "jdbc:mysql://localhost:3306/db",
}
```

## 数组展开

```yaml
app:
  nodes:
    - host: node1
      port: 8080
    - host: node2
      port: 8081
```

```go
// 展开后
map[string]any{
    "app.nodes[0].host": "node1",
    "app.nodes[0].port": "8080",
    "app.nodes[1].host": "node2",
    "app.nodes[1].port": "8081",
}
```

## 类型处理

| 输入类型 | 输出方式 |
|----------|----------|
| `string` | 原值 |
| `map[string]any` / `map[any]any` | 递归展开，key 拼接 |
| `[]any` | 按 `[index]` 展开 |
| 其他类型 + 非 nil | `fmt.Sprintf("%v", v)` |
| nil | 空字符串 |

## 递归深度控制

通过环境变量 `FLATTENED_MAP_MAX_DEPTH` 控制最大递归深度（默认 100）：

```bash
export FLATTENED_MAP_MAX_DEPTH=50
```

## 调用方

| 调用者 | 用途 |
|--------|------|
| `ag_conf.LoadConfigFile` | 将 YAML/JSON 配置文件展开为扁平属性源 |
