---
tags:
  - ag-core
  - contribute
  - agredis
  - redis
  - architecture
  - overview
---

# AgRedis — Redis 客户端

> 路径：`contribute/agredis/` | 基于 [go-redis v9](https://github.com/redis/go-redis) 的 Redis 客户端封装

## 概述

AgRedis 在 go-redis v9 之上提供了一套**接口抽象** + **读写分离客户端** + **Builder 模式**。核心设计是 `AgRedisClient` 接口，它精选 go-redis 的 Cmdable 子集（String、Hash、List、Set、SortedSet、Bitmap、Generic），屏蔽了 PubSub、Stream、模块扩展等高级功能。同时提供 `RWClient` 实现主从读写分离。

```
YAML 配置
    │
    ▼
AgRedisProperties
    ├── type: universal  →  redis.UniversalClient (单机/集群/Sentinel)
    └── type: rw         →  RWClient (主写 + 从读)
                              │
                        AgRedisClient 接口
                              │
                    嵌入 go-redis Cmdable 子集
                    (String / Hash / List / Set / SortedSet / Bitmap / Generic)
```

## 文件结构

```
agredis/
├── config_redis.go              # AgRedisProperties + AgUniversalOptionsProperties
├── config_converter.go          # → redis.UniversalOptions 转换
├── ag_client.go                 # AgRedisClient 接口定义
├── ag_client_builder.go         # AgRedisClientBuilder (Universal / RW)
│
├── rw_client.go                 # RWClient：主从读写分离客户端
├── rw_client_hook.go            # RWClient.AddHook（广播到主从）
├── rw_client_string_cmdable.go  # RWClient 读操作路由到从节点 (Get/MGet/HGet/Exists)
├── rw_client_sortedset_cmdable.go
├── rw_client_generic_cmdable.go
│
├── zfx_redis.go                 # FX Module (FxAgRedisServerMode)
├── zfx_ag_client_builder.go     # FX Builder 注入
│
└── test/
    ├── redis_test.go
    ├── agclient_test.go
    └── over_test.go
```

## AgRedisClient 接口

```go
// ag_client.go:17-62
type AgRedisClient interface {
    // 基础
    Echo(ctx context.Context, message interface{}) *redis.StringCmd
    Ping(ctx context.Context) *redis.StatusCmd

    // Cmdable 子集（精选常用类型）
    redis.StringCmdable      // String：Get/Set/Incr/MGet/MSet...
    redis.HashCmdable        // Hash：HGet/HSet/HDel/HGetAll...
    redis.ListCmdable        // List：LPush/RPop/LLen...
    redis.SetCmdable         // Set：SAdd/SMembers/SIsMember...
    redis.SortedSetCmdable   // ZSet：ZAdd/ZRange/ZRank...
    redis.BitMapCmdable      // Bitmap：GetBit/SetBit/BitCount...
    redis.GenericCmdable     // 通用：Del/Exists/Expire/TTL/Type...

    // 管理
    AddHook(redis.Hook)
    Watch(ctx context.Context, fn func(*redis.Tx) error, keys ...string) error
    Close() error
    PoolStats() *redis.PoolStats
}
```

接口限定：
- 不暴露 PubSub、Stream、JSON、Search、Timeseries 等高级功能
- 不暴露 `Do()`（自定义命令）和 `Process()`（底层方法）
- 所有实现（`redis.Client`、`redis.ClusterClient`、`redis.Ring`、`RWClient`）均满足该接口

## 两种客户端模式

| 模式 | 对应类型 | 使用场景 |
|------|---------|---------|
| `universal` | `redis.UniversalClient` | 单机、集群、Sentinel 均由 go-redis 自动选择 |
| `rw` | `RWClient` | 主从架构，写走主节点，读走随机的从节点 |

详见 [01-配置与客户端模式](01-配置与客户端模式.md)。
