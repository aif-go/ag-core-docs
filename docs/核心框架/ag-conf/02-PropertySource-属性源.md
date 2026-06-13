---
tags:
  - ag-core
  - ag-conf
  - property-source
---

# PropertySource 属性源体系

> 对应文件：`api_source.go`、`source_property_source.go`、`sources_mutable_property_sources.go`

## 接口定义

```go
// IPropertySource 单个属性源
type IPropertySource interface {
    GetName() string                  // 属性源名称（用于定位和替换）
    EqualsName(psname string) bool    // 名称比较
    GetSource() map[string]any        // 底层 map 数据
    GetProperty(key string) any       // 获取指定 key 的值
    ContainsProperty(key string) bool // 是否包含指定 key
    GetPropertyNames() []string       // 所有 key 列表
}
```

## 实现类

### MapPropertySource（基础实现）

最基础的实现，直接包装 `map[string]any`：

```go
type MapPropertySource struct {
    NamedPropertySource      // 内嵌名称支持
    Source map[string]any    // 底层数据
}
```

### PropertiesPropertySource（带锁版本）

在 `MapPropertySource` 基础上增加了 `sync.Mutex`，用于可能并发读取的场景：

```go
type PropertiesPropertySource struct {
    MapPropertySource
    lock sync.Mutex
}
```

### SystemEnvironmentPropertySource

系统环境变量的封装，继承自 `MapPropertySource`，无额外行为。

## MutablePropertySources 集合

### 功能

可变的、有序的、并发安全的属性源集合。底层使用 `ag_ext.CopyOnWriteSlice` 实现。

### 优先级操作

```go
// 添加到集合头部（最高优先级）
ps.AddFirst(source)

// 添加到集合尾部（最低优先级）
ps.AddLast(source)

// 在某个指定名称的属性源之前添加
ps.AddBefore("existingName", source)

// 在某个指定名称的属性源之后添加
ps.AddAfter("existingName", source)

// 替换已有的属性源
ps.Replace("name", newSource)

// 删除属性源
ps.Remove("name")
```

### 遍历

```go
// 正序遍历
ps.RangePropertySourceHandler(func(ps IPropertySource) (end bool, err error) {
    // 按优先级从高到低
})

// 倒序遍历
ps.RangePropertySourceHandlerReverse(func(ps IPropertySource) (end bool, err error) {
    // 按优先级从低到高
})
```

### 并发安全

- 读操作使用 `RLock`（读写锁）
- 写操作使用 `Lock`
- 底层列表使用 `CopyOnWriteSlice`，遍历时不会因为写入而 panic

## 属性源命名规范

```
[SYS]-Properties           ← 命令行 -D 参数
[SYS]-Environment          ← 系统环境变量
[LOCAL]-/path/to/app.yml   ← 本地配置文件
[DECRYPT]-SystemEnvAndProp ← 系统配置解密结果
[DECRYPT]-[LOCAL]          ← 本地配置解密结果
```

## 典型的属性源注册顺序

```
1. [SYS]-Properties           ← NewStandardEnvironment() 时注册
2. [SYS]-Environment          ← NewStandardEnvironment() 时注册
3. [DECRYPT]-SystemEnvAndProp ← DecryptSystemConfig() 后插入头部
4. [LOCAL]-app.yml            ← LoadLocalConfig() 时注册
5. [DECRYPT]-[LOCAL]          ← DecryptLocalConfig() 后插入头部
6. Nacos 配置源               ← EnableNacosRemoteConfig() 时注册
```
