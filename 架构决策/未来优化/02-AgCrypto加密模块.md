---
tags:
  - ag-core
  - future
  - crypto
  - optimization
  - discussion
---

# AgCrypto 优化 — 从占位到真正的加密模块

> 讨论日期：2026-06-04 | 状态：待讨论

## 问题

当前 `ag_crypto` 是预留的占位模块，存在五个核心问题：

| # | 问题 | 影响 |
|---|------|------|
| 1 | **默认"加密器"是 Base64** — Base64 是编码不是加密，零安全性 | `ITextEncryptor` 名不副实，给使用者错误的安全预期 |
| 2 | **全局单例不走 DI** — `Get/SetEncryptorPrimary()` 是全局变量 | 无法多加密器共存、单测互相污染、与框架 FX 风格割裂 |
| 3 | **没有密钥管理** — 若要上 AES/SM4，密钥从哪获取、如何轮换、如何区分不同加密器 | 生产环境无法安全落地 |
| 4 | **`Encrypt()` 方向闲置** — 接口有加密方法，但框架里只有 ag_conf 解密的消费方 | 接口设计不完整，加密工具链缺失 |
| 5 | **`{cipher}` 协议碎片化** — 格式定义散落在 ag_conf（前缀常量）+ ag_crypto（解密实现），没有统一的密文协议 | 扩展困难，无法支持多加密器共存、无法带 IV/KeyID |

## 现状分析

### 接口定义

```go
// ag/ag_crypto/encryptor.go
var DefaultEncryptorPrimary ITextEncryptor = Base64Encryptor  // 全局单例

type ITextEncryptor interface {
    Name() string
    Encrypt(plaintext string) (string, error)
    Decrypt(ciphertext string) (string, error)
}
```

### 唯一消费方

```go
// ag_conf/decrypt.go:78-85
encryptor := ag_crypto.GetEncrytorPrimary()
if strings.HasPrefix(ciphertext, "{cipher}") {
    ciphertext = ciphertext[len("{cipher}"):]
    plaintext, err := encryptor.Decrypt(ciphertext)
}
```

消费方直接判断 `{cipher}` 前缀，然后调用默认加密器解密——这个流程假设：世界上只有一种密文格式和一个加密器。

### 全局单例的隐患

```go
// ❌ 当前：全局变量 + init() 注册
func init() {
    ag_crypto.SetEncryptorPrimary(&SM4Encryptor{key: loadKey()})
}

// 问题：
// - 无法在同一个进程中使用多种加密器
// - 单测 A 改了全局 → 单测 B 受影响
// - 加密器初始化依赖配置，但配置加载在 crypto 注册之后
```

---

## 优化方案讨论

### 方案 A：密文协议 + FX 多加密器（推荐）

核心思路：密文自带加密器标识，ag_conf 通过 FX 注入加密器表，按标识分发解密。

#### 密文协议

密文不再是没有结构的裸 base64，而是带元数据前缀：

```
{cipher:name[:keyid]}payload
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `cipher` | ✅ | 类型标识，替代当前纯文本前缀 |
| `name` | ✅ | 加密器名称，对应注册的加密器 |
| `keyid` | 可选 | 密钥版本标识，支持密钥轮换 |
| `payload` | ✅ | 加密后的密文（base64 编码） |

示例：

```yaml
# 使用 SM4 加密
db.password: "{cipher:sm4}AbCdEf123456=="

# 使用密钥版本 v2 的 AES 加密
api.key: "{cipher:aes:v2}XYZ789abc="

# 向后兼容：不带 name 时使用默认加密器（Base64）
debug.token: "{cipher}ZGVidWc="
```

#### 加密器注册

```go
// ag/ag_crypto/registry.go (新增)
type EncryptorRegistry struct {
    encryptors map[string]ITextEncryptor
    default_   ITextEncryptor
}

func (r *EncryptorRegistry) Register(name string, enc ITextEncryptor)
func (r *EncryptorRegistry) Get(name string) (ITextEncryptor, error)
func (r *EncryptorRegistry) SetDefault(enc ITextEncryptor)
```

#### FX 注入（新方式）

```go
// 注册加密器
fx.Provide(
    ag_crypto.NewSM4Encryptor,                     // 提供 SM4 实现
    ag_crypto.NewAESEncryptor,                     // 提供 AES 实现
    ag_crypto.FxEncryptorRegistry,                 // 聚合到 Registry
)

// 提供密钥（从配置读取）
fx.Provide(func(env ag_conf.IConfigurableEnvironment) *ag_crypto.KeyConfig {
    return &ag_crypto.KeyConfig{
        Path: env.GetProperty("crypto.key.path"),
    }
})
```

```yaml
# 密钥配置
crypto:
  key:
    path: /etc/keys/sm4.key           # 密钥文件路径
    # 或
    # env: CRYPTO_KEY                  # 从环境变量读取
```

#### ag_conf 消费方改造

```go
// ag_conf/decrypt.go (改造后)
type DecryptProcessor struct {
    registry *ag_crypto.EncryptorRegistry
}

func (dp *DecryptProcessor) decrypt(ciphertext string) (string, error) {
    name, keyid, payload := ag_crypto.ParseProtocol(ciphertext)  // 解析 {cipher:name:keyid}
    encryptor, err := dp.registry.Get(name)
    if err != nil { return "", err }
    if keyid != "" {
        encryptor = encryptor.WithKeyID(keyid)  // 支持密钥版本
    }
    return encryptor.Decrypt(payload)
}
```

#### 优点

- **多加密器共存**：不同配置值可以用不同加密器
- **密钥轮换**：通过 `keyid` 无缝切换密钥版本
- **向后兼容**：`{cipher}` 不带 name 时回退到默认加密器（Base64）
- **FX 化**：注册和消费都走 DI，与框架一致
- **职责清晰**：ag_crypto 负责协议解析和加密器注册；ag_conf 只负责调用

#### 缺点

- 改动范围大：ag_crypto + ag_conf + 所有配置文件
- 协议设计需谨慎：`{cipher:name:keyid}` 语法需要正式的解析器

---

### 方案 B：最小修复 — 只换加密实现

不改架构，只做三件事：

```go
// 1. 默认加密器换成 AES-GCM（需要密钥）
func NewAESEncryptor(key []byte) ITextEncryptor { ... }

// 2. 密钥从环境变量读取
func init() {
    key := []byte(os.Getenv("CRYPTO_KEY"))
    ag_crypto.SetEncryptorPrimary(NewAESEncryptor(key))
}

// 3. {cipher} 保持不变
```

#### 优点

- 改动极小，一天完成
- 解决了"Base64 是编码不是加密"的核心问题

#### 缺点

- 全局单例问题仍在
- 密钥管理靠环境变量，脆弱
- 不支持多加密器、密钥轮换

---

### 方案 C：去掉 ag_crypto，下沉到 ag_conf

```go
// ag_conf 直接通过配置选择加密器
type DecryptConfig struct {
    Encryptor string   // "base64" | "aes" | "sm4"
    KeyPath   string   // 密钥文件路径
}
```

ag_conf 内部根据配置创建加密器，不再需要 ag_crypto 包。

#### 优点

- 减少一个包
- 解密逻辑完全内聚在 ag_conf

#### 缺点

- ag_conf 变得臃肿
- 加密功能无法被其他模块复用
- 与 `text_encryptor.go` 工具（如果将来有加密生成工具）解耦

---

## 方案对比

| 维度 | 方案 A（协议+多加密器） | 方案 B（换实现） | 方案 C（下沉） |
|------|------------------------|-----------------|---------------|
| 安全性 | ✅ AES/SM4 | ✅ AES/SM4 | ✅ AES/SM4 |
| 多加密器共存 | ✅ 按 name 分发 | ❌ 全局单例 | ❌ 单配置 |
| 密钥轮换 | ✅ keyid 协议 | ❌ | ❌ |
| FX 一致 | ✅ | ❌ 全局变量 | ✅ 配置驱动 |
| {cipher} 兼容 | ✅ 向后兼容 | ✅ 不变 | ✅ 不变 |
| 实现成本 | 中高 | 低 | 低 |
| 可扩展性 | ✅ | ❌ | ❌ |

---

## 初步结论

**倾向方案 A**，理由：

1. **安全不是补丁**：方案 B 只是把 Base64 换成 AES，治标不治本。等到需要密钥轮换、多加密器时还得重构
2. **密文协议是基础设施**：`{cipher:name[:keyid]}` 让密文自描述，是后续所有安全功能（密钥轮换、审计日志、加密器迁移）的基础
3. **FX 化对齐框架风格**：全局单例在 DI 框架里格格不入，早晚要改
4. **分步落地**：先做协议 + Registry + FX 注入（不改解密器实现），再做 AES/SM4 真加密器，降低风险

---

## 待讨论

- `{cipher:name[:keyid]}` 协议语法是否够用？需要支持 IV 显式传递吗？
- 密钥管理是文件路径、环境变量还是 KMS？与 ag_conf 的 PropertySource 机制如何结合？
- `Encrypt()` 方向是否需要配套工具（CLI 加密命令、代码生成用 `{cipher}` 前缀输出）？
- 现有 Base64 加密的存量配置如何迁移？平滑过渡期多长？
- 是否需要加密器健康检查（密钥有效性、过期预警）？
