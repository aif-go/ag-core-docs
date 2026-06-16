---
tags:
  - ag-core
  - agonet
  - tls
  - tlcp
  - security
  - architecture
---

# 安全配置：TLS 与 TLCP

> 文件：`config_tls.go` + `options_tls.go` | TLS + 国密 TLCP 双栈支持

## 概述

Agonet 同时支持标准 **TLS**（RFC 8446）和中国国家密码标准 **TLCP**（GB/T 38636-2020，国密传输层密码协议）。服务端可以同时监听两种协议（`tls_tlcp`）。

## TLS 类型

```go
// config_tls.go:16-21
const (
    TLSType_UNSET    TLSType = ""          // 未设置
    TLSType_NONE     TLSType = "none"      // 不使用
    TLSType_TLS      TLSType = "tls"       // 标准 TLS
    TLSType_TLCP     TLSType = "tlcp"      // 国密 TLCP
    TLSTYPE_TLS_TLCP TLSType = "tls_tlcp"  // 双栈（仅服务端）
)
```

## 配置结构

```yaml
config:
  security:
    type: tls                      # 服务端 TLS 类型
    cliType: tls                   # 客户端 TLS 类型（可独立配置）
    certsDir: certs                # 证书基础路径

    tls:                           # TLS 证书
      caPath: ca.crt
      authCertPath: server.crt     # 认证证书
      authKeyPath: server.key      # 认证私钥
      signCertPath: ""             # （TLS 通常不需要签名证书）
      signKeyPath: ""
      serverName: example.com
      insecureSkipVerify: false

    tlcp:                          # TLCP 证书（国密）
      caPath: sm2-ca.cer
      authCertPath: sm2-auth.cer   # 认证证书
      authKeyPath: sm2-auth.key    # 认证私钥
      signCertPath: sm2-sign.cer   # 签名证书
      signKeyPath: sm2-sign.key    # 签名私钥
      encCertPath: sm2-enc.cer     # 加密证书（TLCP 特有）
      encKeyPath: sm2-enc.key      # 加密私钥
      serverName: example.com
      insecureSkipVerify: false
```

### SecurityConfig

```go
// config_tls.go:33-43
type SecurityConfig struct {
    Type     TLSType      // 服务端安全类型
    CliType  TLSType      // 客户端安全类型（独立配置）

    CertsDir string       // 证书基础路径

    TLS  TLSConfig
    TLCP TLCPConfig
}
```

### TLSConfig

```go
// config_tls.go:45-65
type TLSConfig struct {
    CaPath       string   // CA 证书路径
    AuthCertPath string   // 认证证书路径
    AuthKeyPath  string   // 认证私钥路径
    SignCertPath string   // 签名证书路径（TLS 双向认证）
    SignKeyPath  string

    ServerName         string
    InsecureSkipVerify bool   // 跳过证书验证
}
```

### TLCPConfig

```go
// config_tls.go:67-86
type TLCPConfig struct {
    CaPath       string   // CA 证书路径
    AuthCertPath string   // 认证证书（加密证书）
    AuthKeyPath  string   // 认证私钥
    SignCertPath string   // 签名证书
    SignKeyPath  string
    EncCertPath  string   // 加密证书（TLCP 特有）
    EncKeyPath   string

    ServerName         string
    InsecureSkipVerify bool
}
```

TLCP 使用双证书体系（签名证书 + 加密证书），这与 TLS 的单证书体系不同。

## 客户端与服务端独立配置

```yaml
config:
  security:
    type: tls                  # 服务端使用 TLS
    cliType: tlcp              # 客户端使用 TLCP（连接外部 TLCP 服务）
```

Option 中客户端 TLS 配置独立于服务端，未设置时默认复用服务端配置：

```go
// options.go:60-79
func (opt *Options) CliTLSType() TLSType {
    if opt.CLI_TLSType != TLSType_UNSET { return opt.CLI_TLSType }
    return opt.TLSType  // 默认复用服务端配置
}

func (opt *Options) CliTLSConfig() *tls.Config {
    if opt.CLI_TLSConfig != nil { return opt.CLI_TLSConfig }
    return opt.TLSConfig
}
```

## 双栈模式（TLS + TLCP）

```yaml
config:
  security:
    type: tls_tlcp           # 同时监听 TLS 和 TLCP
```

此时 Server 同时创建 TLS Listener 和 TLCP Listener，客户端根据 `cliType` 选择连接方式。

## 连接时协议选择

客户端 `Dial` 根据 TLSType 选择连接方式：

```go
// client.go:133-152
// import "github.com/aif-go/ag-core/contribute/agonet"

switch cliTlsType {
case TLSType_NONE:
    c, err = net.Dial(network, addr)
case TLSType_TLS:
    c, err = tls.Dial(network, addr, tlsCfg)
case TLSType_TLCP:
    c, err = tlcp.Dial(network, addr, tlcpCfg)
}
```

---

## 常见陷阱

### ❌ TLCP 证书排列搞反

TLCP 使用**双证书体系**（签名证书 + 加密证书），与 TLS 的单证书体系不同。`auth` 和 `sign` 和 `enc` 是三种不同用途的证书：

| 字段 | 用途 | 搞反后果 |
|------|------|---------|
| `authCertPath` / `authKeyPath` | 认证证书（身份验证） | 握手失败 |
| `signCertPath` / `signKeyPath` | 签名证书（数字签名） | 签名验证失败 |
| `encCertPath` / `encKeyPath` | 加密证书（密钥交换） | 无法解密 |

> `auth` ≠ `sign` ≠ `enc`，不能把同一个证书填到三个字段里。

### ❌ 证书路径相对于 `certsDir` 而非工作目录

```yaml
security:
  certsDir: /etc/certs      # 基础路径
  tls:
    authCertPath: server.crt  # 实际路径: /etc/certs/server.crt
```

所有证书路径都拼接在 `certsDir` 之后，不要写绝对路径。

### ❌ 客户端忘记配置 `cliType`

客户端默认复用服务端的 `type`。如果服务端是 `tls_tlcp` 双栈而客户端不指定 `cliType`，客户端会尝试 `tls_tlcp` 导致 Dial 失败。

```yaml
# ✅ 明确指定客户端 TLS 类型
security:
  type: tls_tlcp       # 服务端双栈
  cliType: tls          # 客户端只用 TLS
```
