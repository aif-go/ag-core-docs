---
tags:
  - ag-core
  - ag-conf
  - bind
  - reflection
---

# 配置绑定 — Bind 到结构体

> 对应文件：`bind.go`

## 概述

`ConfigurationPropertiesBinder` 通过 **反射** 将扁平的配置 map 绑定到 Go 结构体，类似 Spring 的 `@ConfigurationProperties`。

## 核心接口

```go
type IBinder interface {
    GetEnv() IConfigurableEnvironment    // 获取配置环境
    Bind(i any, name ...string) error    // 绑定配置到结构体
}
```

## 基本用法

```go
// 定义配置结构体
type ServerConfig struct {
    Host string `value:"${host:localhost}"`
    Port int    `value:"${port:8080}"`
}

type AppConfig struct {
    Name   string       `value:"${name}"`
    Server ServerConfig `value:"${server}"`  // 嵌套结构体
}

// 绑定
binder := ag_conf.NewConfigurationPropertiesBinder(env)
var cfg AppConfig
err := binder.Bind(&cfg, "app")
// 此时属性 app.name, app.server.host, app.server.port 被绑定到结构体
```

## 标签系统

### `value` 标签（可选）

**不指定 `value` 标签时，默认使用 Go 字段名作为配置 key。**

```go
type Config struct {
    Host string  // key = "app.Host"（无 value 标签，使用字段名 Host）
    Port int     // key = "app.Port"
}
```

**指定 `value` 标签时，使用标签中定义的 key：**

```go
type Config struct {
    Host    string `value:"${db.host}"`           // key = "app.db.host"
    Port    int    `value:"${db.port:3306}"`       // key = "app.db.port"，默认 3306
    Timeout int    `value:"${timeout}"`             // key = "app.timeout"
}
```

**特殊用法：只设默认值，不指定 key（key 仍用字段名）：**

```go
type Config struct {
    Port int `value:"${:=8080}"`  // key = "app.Port"，找不到时默认 8080
}
```

### `required` 标签

标记字段为必填，缺失时返回 `ErrNotExist`：

```go
type Config struct {
    Host     string `value:"${db.host}" required:"true"`   // key = "app.db.host"，必填
    Password string `required:"true"`                       // key = "app.Password"，必填
    Port     int    `value:"${db.port:3306}"`               // key = "app.db.port"，可选
}
```

### key 拼接规则

```go
Binder.Bind(&cfg, "app")  // root key = "app"

// 字段 "Name" 无 value 标签 → key = "app.Name"（root + "." + 字段名）
// 字段 value:"${server.host}" → key = "app.server.host"（root + "." + 标签key）
// 字段 value:"${host}" → key = "app.host"

Binder.Bind(&cfg, "")     // root key = ""

// 字段 "Name" 无 value 标签 → key = "Name"（直接用字段名）
// 字段 value:"${server.host}" → key = "server.host"（直接用标签key）
```

## 支持的类型

| 类型 | 说明 |
|------|------|
| `string` | 字符串 |
| `int` / `int64` / `int32` | 整数类型 |
| `bool` | 布尔值 |
| `float64` / `float32` | 浮点数 |
| `struct` | 嵌套结构体，递归绑定 |
| `slice` | 切片（如 `server.hosts[0]`, `server.hosts[1]`） |
| `map` | 字典（如 `cache.redis.*`） |
| `pointer` | 自动解引用 |
| 其他基础类型 | 通过 `strconv` 转换 |

## 绑定逻辑

### 结构体（bindStruct）

```go
1. 检查当前 key 是否有后代属性
2. 遍历每个字段
3. 解析 value 标签，构建子 key（如 "app.server.host"）
4. 递归调用 BindValue
5. 匿名字段继续遍历其所有字段
```

### 切片（bindSlice）

```go
1. 按索引递增查找：key[0], key[1], key[2]...
2. 找不到时停止（最后一个有效元素）
3. 必填时第一个元素不可为空
```

### Map（bindMap）

```go
1. 查找 key 的所有后代子键
2. 去重后遍历
3. 每个子键递归绑定
```

## 自动刷新（热更新）

所有通过 `Binder.Bind()` 绑定的结构体，**自动注册了配置变更监听器**：

```go
// 在 BindValue 内部：
WatcherM.RegChangeListener(param.Key, func(ck, cv string) {
    // 当配置变化时，自动重新绑定
    cpb.BindValue(rbctx, v, param)
})
```

这意味着配置热更新后，已绑定的结构体字段值会自动更新，无需手动处理。

## 错误处理

```go
var (
    ErrNotExist        = errors.New("not exist")        // key 不存在
    ErrInvalidSyntax   = errors.New("invalid syntax")    // 标签语法错误
    ErrUnBindableType  = errors.New("unbindable type")   // 不可绑定的类型
    ErrUnsupportedType = errors.New("unsupported type")  // 不支持的类型
)
```
