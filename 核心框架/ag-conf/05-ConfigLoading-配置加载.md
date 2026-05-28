---
tags:
  - ag-core
  - ag-conf
  - config-loading
  - reader
---

# 配置加载

> 对应文件：`local.go`、`reader/`

## 加载流程

```
LoadLocalConfig(env)
   │  (sync.Once 保证只加载一次)
   ▼
doLoadLocalConfig(env)
   │
   ├── 获取 app.conf 路径
   │   ├── 优先从属性源读取 app.conf 配置值
   │   └── 未配置则默认：可执行文件同目录下的 app.yml
   │
   ├── 检查路径类型
   │   ├── 目录 → LoadConfigDir（当前仅返回错误，待实现）
   │   └── 文件 → LoadConfigFile
   │
   ▼
LoadConfigFile(env, appConfFile)
   │
   ├── 读取文件内容 (os.ReadFile)
   ├── 根据后缀选择 Reader（yaml/json/properties/toml）
   ├── Reader 解析为 map[string]any
   ├── 展开为扁平 map (GetFlattenedMap)
   │   例: {db: {host: localhost}} → {"db.host": "localhost"}
   └── 注册为属性源 [LOCAL]-文件路径
   │
   ▼
DecryptLocalConfig(env)
   └── 遍历 LOCAL 属性源，解密 {cipher} 前缀的值
```

## 配置文件名

```go
// 默认查找顺序：
app.conf 配置值（可自定义）
  └── 未配置则默认：可执行文件同目录下的 app.yml

// 支持的格式：
app.yml
app.yaml
app.json
app.properties
app.toml
```

## Reader 插件体系

```go
// reader/reader.go - Reader 注册表
var Readers = map[string]Reader{
    "yaml":       yaml.Read,
    "yml":        yaml.Read,
    "json":       json.Read,
    "properties": prop.Read,
    "toml":       toml.Read,
}
```

每个 Reader 实现 `func([]byte) (map[string]any, error)` 接口，可扩展。

## 配置展开

YAML 嵌套结构会被展开为扁平 map，方便通过点号访问：

```yaml
# YAML 原始结构
app:
  name: my-service
  server:
    port: 8080
    host: 0.0.0.0
  datasource:
    mysql:
      url: jdbc:mysql://localhost:3306/db
```

```go
// 展开后（使用 GetFlattenedMap）
map[string]any{
    "app.name":             "my-service",
    "app.server.port":      8080,
    "app.server.host":      "0.0.0.0",
    "app.datasource.mysql.url": "jdbc:mysql://localhost:3306/db",
}
```

## 配置文件覆盖机制

```
1. 加载 app.yml（基础配置）
2. 若存在 app-{profile}.yml（如 app-dev.yml），加载并覆盖
   （当前版本中 profile 功能为 TODO 状态）

后续加载的值会覆盖前面的同名 key。
```

## 使用示例

```go
// 在应用程序启动时
env, _ := ag_conf.NewStandardEnvironment()
ag_conf.LoadLocalConfigToState(env)

// 获取配置
appName := env.GetProperty("app.name")
serverPort := env.GetProperty("app.server.port")
```
