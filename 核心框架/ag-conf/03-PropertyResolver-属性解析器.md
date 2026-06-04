---
tags:
  - ag-core
  - ag-conf
  - resolver
  - placeholder
---

# PropertyResolver 属性解析器

> 对应文件：`resolver_abstract_property_resolver.go`、`resolver_property_sources_property_resolver.go`、`property_placeholder_helper.go`

## 解析链路

AgConf 采用**三层解析架构**，职责逐层递进：

```
IPropertyResolver                    ← 接口层：定义解析契约
  └── IConfigurablePeopertyResolver  ← 配置层：可设置占位符语法
       └── AbstractPropertyResolver  ← 抽象层：实现占位符解析 + 必填校验
            └── PropertySourcesPropertyResolver  ← 实现层：遍历属性源查找值
```

## AbstractPropertyResolver

提供占位符解析和必填校验的通用实现，由子类注入 `GetProperty` / `GetPropertyAsRawString` 函数。

### 字段

```go
type AbstractPropertyResolver struct {
    PlaceholderPrefix                    string   // 占位符前缀，默认 "${"
    PlaceholderSuffix                    string   // 占位符后缀，默认 "}"
    ValueSeparator                       string   // 默认值分隔符，默认 ":"
    IgnoreUnresolvableNestedPlaceholders bool     // 是否忽略未解析的嵌套占位符
    RequiredProperties []string                    // 必填属性列表

    GetProperty            func(key string) string // 由子类注入
    GetPropertyAsRawString func(key string) string // 由子类注入
}
```

### 占位符解析

使用 `sync.Once` 延迟创建 `PropertyPlaceholderHelper`：

- **ResolvePlaceholders** — 忽略未解析占位符（`ignoreUnresolvable=true`）
- **ResolveRequiredPlaceholders** — 未解析时报错（`ignoreUnresolvable=false`）

### 必填校验

```go
resolver.SetRequiredProperties("db.url", "redis.host")
err := resolver.ValidateRequiredProperties()  // 缺失时返回错误
```

## PropertySourcesPropertyResolver

### 属性查找逻辑

```go
func (pspr *PropertySourcesPropertyResolver) getProperty(key string, resolve bool) (string, error) {
    // 1. 按优先级遍历所有属性源
    for _, ps := range pspr.PropertySources.GetPropertySources() {
        // 2. 大小写不敏感查找
        value := getPropertyFold(key, ps)
        if value != nil {
            // 3. 递归解析值中的占位符
            if resolve {
                value = pspr.ResolveNestedPlaceholders(value)
            }
            return value, nil
        }
    }
    // 4. 所有属性源都找不到，返回空字符串
    return "", nil
}
```

**要点：**
- 查找时**忽略 key 的大小写**（`strings.EqualFold`）
- 找到值后**递归解析其中的占位符**
- 第一个匹配即返回（优先级由属性源顺序决定）

## PropertyPlaceholderHelper — 占位符解析引擎

### 功能

递归解析字符串中的占位符，替换为实际值。

### 支持 ${} 语法

占位符解析在**每次读取属性值时自动触发**（`getProperty(key, true)` → `resolveNestedPlaceholders`）。这意味着在 YAML 配置中可以直接引用其他属性的值：

```yaml
# 基本占位符
db_url: ${DB_URL}

# 带默认值
port: ${SERVER_PORT:8080}

# 跨路径引用（引用同一 YAML 中其他 section 的值）
nacos:
  config:
    serveraddr: 192.168.1.1:8848
  naming:
    serveraddr: ${nacos.config.serveraddr}    # ← 引用 config 下的值
    namespace: ${nacos.config.namespace}

# 嵌套占位符
app_name: app-${ENV:dev}
```

> 只要属性值以 `${` 开头，解析器就会递归查找并替换，key 匹配大小写不敏感（`EqualFold`）。

### 递归解析流程

```
解析 "${db.${env}.host}"
     │
     ▼ 找到外层 ${...}
     │
"db.${env}.host"
     │
     ▼ 递归解析内层占位符
     │
"${env}" → "dev"
     │
     ▼ 替换后
"db.dev.host"
     │
     ▼ 从属性源获取 "db.dev.host"
     │
"10.0.0.1"
```

### 安全机制

- **循环引用检测** — 使用 `visitedPlaceholders` map 追踪已访问的占位符
- **Builder 池** — 使用 `sync.Pool` 复用 `strings.Builder`，减少 GC 压力
- **边界处理** — `findPlaceholderEndIndex` 正确处理嵌套占位符的括号匹配

### 默认值解析

```
${key:defaultValue}
   ↑       ↑
   key     分隔符后的默认值

解析逻辑：
1. 尝试获取 actualPlaceholder 的值
2. 若为空，使用 defaultValue
3. 若也为空，根据 ignoreUnresolvable 决定是否报错
```
