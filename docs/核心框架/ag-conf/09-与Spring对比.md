---
tags:
  - ag-core
  - ag-conf
  - comparison
  - spring
---

# 与 Spring Framework 的对比

AgConf 的设计**深度借鉴 Spring Framework 的配置体系**，从接口命名到实现逻辑都有明显的 Spring 影子。

## 架构对比

```
Spring Framework                     AgConf
═══════════════════════════          ═══════════════════════════
Environment                          IEnvironment (已废弃)
  ├── ConfigurableEnvironment          ├── IConfigurableEnvironment
  │   └── StandardEnvironment          │   └── StandardEnvironment
  │       ├─ MutablePropertySources    │       ├─ MutablePropertySources
  │       └─ PropertyResolver          │       └─ IConfigurablePeopertyResolver
  │           └─ PropertySources-      │           └─ PropertySources-
  │              PropertyResolver      │              PropertyResolver
  │                  ├─ Abstract-      │                  ├─ Abstract-
  │                  │  Property-      │                  │  Property-
  │                  │  Resolver       │                  │  Resolver
  │                  └─ Property-      │                  └─ Property-
  │                     Placeholder-   │                     Placeholder-
  │                     Helper         │                     Helper
  └─ PropertySource                    └─ IPropertySource
      └─ MapPropertySource                 └─ MapPropertySource

@Value                                 value struct tag
@ConfigurationProperties              ConfigurationPropertiesBinder.Bind()
{password} / {cipher}                 {cipher} + 解密器
```

## 关键差异

| 特性      | Spring                  | AgConf                               | 差异说明              |
| ------- | ----------------------- | ------------------------------------ | ----------------- |
| 接口命名    | `PropertyResolver`      | `IPropertyResolver`                  | Go 习惯用 `I` 前缀标记接口 |
| 占位符语法   | `${key:default}`        | `${key:default}`                     | 功能对齐                          |
| 属性绑定    | 注解 + 自动扫描               | 手动 `Binder.Bind()`                   | Go 无注解机制          |
| 转换服务    | `ConversionService`     | 直接 `strconv`                         | TODO 状态           |
| Profile | 完整支持                    | 接口定义但未实现                             | TODO 状态           |
| 属性源定义   | 文件 + 注解 + 编程式           | 编程式 + 文件 Reader                      | 更轻量               |
| 加密支持    | `{cipher}`（jasypt）      | `{cipher}` + 自定义解密器                  | 功能对齐              |
| Watcher | Spring Cloud Bus        | Nacos Watcher                        | 目前仅有 Nacos 实现     |
| 必填校验    | `@Value(required=true)` | `required:"true"` tag                | 类似实现              |
| 嵌套占位符   | 支持                      | 支持                                   | 功能对齐、实现类似         |
| 并发安全    | 线程安全                    | 读写锁 + CopyOnWriteSlice               | Go 风格实现           |
| 错误处理    | 异常抛出                    | 返回 error                             | Go 惯例             |
| 默认值     | `:` 分隔                  | `:` 分隔                               | 完全一致              |

## 相同设计理念

1. **属性源优先级链** — 高优先级覆盖低优先级
2. **占位符递归解析** — 值中的占位符继续解析
3. **大小写不敏感** — key 查找忽略大小写
4. **尾部加载覆盖** — 后加载的配置源优先级更高
5. **懒初始化** — 占位符解析器延迟创建

## TODO 项

AgConf 中标记为 TODO 但 Spring 已完整支持的特性：

- [ ] **Profile 机制** — `GetActiveProfiles()` / `GetDefaultProfiles()` 已定义但未实现
- [ ] **ConversionService** — 自定义类型转换器
- [ ] **配置目录加载** — `LoadConfigDir()` 仅返回错误
- [ ] **更精确的刷新控制** — 目前所有绑定对象都自动刷新
