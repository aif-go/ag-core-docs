---
tags:
  - ag-core
  - ag-conf
  - environment
---

# Environment 环境抽象

> 对应文件：`resolver_abstract_enviroment.go`、`resolver_standardEnvironment.go`

## 设计模式

Environment 层是 **外观模式 + 委托模式** 的典型应用：

- 对外暴露统一的属性访问接口
- 内部将实际工作委托给 `PropertyResolver` 和 `PropertySources`

## AbstractEnvironment

```go
type AbstractEnvironment struct {
    PropertySources  *MutablePropertySources       // 属性源集合
    PropertyResolver IConfigurablePeopertyResolver // 属性解析器
}
```

所有 `IPropertyResolver` 方法都是简单的委托：

```go
func (e *AbstractEnvironment) GetProperty(key string) string {
    return e.PropertyResolver.GetProperty(key)
}
```

## StandardEnvironment（默认实现）

```go
type StandardEnvironment struct {
    AbstractEnvironment
}

func NewStandardEnvironment() (*StandardEnvironment, error) {
    e := &StandardEnvironment{}
    e.PropertySources = NewMutablePropertySources()
    e.PropertyResolver = NewPropertySourcesPropertyResolver(e.PropertySources)
    e.customizePropertySources(e.PropertySources)
    return e, nil
}
```

### 初始化流程

```
NewStandardEnvironment()
  │
  ├── 创建 MutablePropertySources（空的属性源集合）
  ├── 创建 PropertySourcesPropertyResolver（关联同一集合）
  └── customizePropertySources()
       ├── 解析命令行 -D 参数 → [SYS]-Properties
       ├── 读取系统环境变量 → [SYS]-Environment
       └── 解密系统配置 → [DECRYPT]-SystemEnvAndProp
```

## 命令行参数解析

```
# 标准格式（默认使用 -D 前缀）
./app -Ddb.host=localhost -Dserver.port=8080

# 可通过环境变量 GS_ARGS_PREFIX 自定义前缀
GS_ARGS_PREFIX=-- ./app --db.host=localhost

# 无等号视为 true
./app -Ddebug
```

**处理逻辑：**
1. 遍历 `os.Args`
2. 匹配前缀（默认 `-D`）
3. `=` 分隔 key/value，无值则默认为 `true`
4. key 中的 `_` 自动替换为 `.`
5. key 统一转为小写

## 系统环境变量解析

```
# 环境变量中的 _ 自动转为 .
DB_HOST=localhost → db.host

# key 统一转为小写
DB_HOST=localhost → db.host

# 多层嵌套
REDIS_CLUSTER_NODES=node1,node2 → redis.cluster.nodes
```

## Environment 的实际使用

```go
// 1. 创建环境
env, _ := ag_conf.NewStandardEnvironment()

// 2. 加载本地配置（追加属性源）
ag_conf.LoadLocalConfigToState(env)

// 3. 获取属性
dbHost := env.GetProperty("db.host")
dbPort := env.GetPropertyDefault("db.port", "3306")

// 4. 解析占位符
connStr := env.ResolvePlaceholders("${db.host}:${db.port}")

// 5. 必填校验
env.SetRequiredProperties("db.host", "db.password")
err := env.ValidateRequiredProperties()

// 6. 绑定到结构体
binder := ag_conf.NewConfigurationPropertiesBinder(env)
var cfg Config
binder.Bind(&cfg, "app")
```
