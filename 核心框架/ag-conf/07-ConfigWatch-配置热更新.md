---
tags:
  - ag-core
  - ag-conf
  - watch
  - hot-reload
---

# 配置热更新 — Watch & Refresh

> 对应文件：`watch.go`、`watcher_refresh.go`

## 架构

```
Watcher 接口                         ← 每个配置源实现此接口
  ├── NacosConfigWatcher            (Nacos 配置监听)
  └── 可扩展（文件监听、etcd 等）

WatcherManager                       ← 统一管理所有 Watcher
  ├── 注册 Watcher
  ├── 接收配置变更事件
  └── 通知变更监听器（Listener）

WatcherServer                        ← 服务器形式运行
  └── Start/Stop 生命周期管理
```

## Watcher 接口

```go
type Watcher interface {
    Start(ctx context.Context, callback ChangePropertySources)
    Stop()
}

type ConfigChangeListener func(k, v string)
type ChangePropertySources func(propertySources []IPropertySource)
```

## WatcherManager 核心逻辑

```go
func (wm *WatcherManager) run(ctx context.Context) error {
    for {
        select {
        case watcher := <-wm.watcherChan:
            // 注册新 watcher
            wm.startWatcher(watcher)
        case propertySources := <-wm.refreshChan:
            // 处理配置刷新
            wm.refreshPropertySources(propertySources)
        case <-time.After(60 * time.Second):
            // 定期自检（TODO）
        case <-ctx.Done():
            // 关闭所有 watcher
            wm.close()
        }
    }
}
```

## 配置刷新流程

```
外部配置变更触发（如 Nacos 推送）
     │
     ▼
Watcher.Start() 回调 ChangePropertySources(ps)
     │
     ▼
WatcherManager.refreshPropertySources(ps)
     │
     ├── 1. 对比新旧配置，找出变化的 key
     │       changes(befor, after) → map[key]value
     │
     ├── 2. 解密配置（DecryptConfigSource）
     │
     ├── 3. 替换属性源（ReplaceSource）
     │
     └── 4. 通知变更监听器
          ├── 匹配所有关联的 key
          └── 调用注册的 ConfigChangeListener
```

## 变更检测

```go
func changes(befor, after map[string]interface{}) map[string]interface{} {
    result := make(map[string]interface{})
    // 被删除的 key
    for key := range befor {
        if _, exists := after[key]; !exists {
            result[key] = nil
        }
    }
    // 被修改的 key
    for key, val := range after {
        if beforVal, exists := befor[key]; !exists || beforVal != val {
            result[key] = val
        }
    }
    // 新增的 key
    for key, val := range after {
        if _, exists := befor[key]; !exists {
            result[key] = val
        }
    }
    return result
}
```

## Key 匹配规则

```go
// matchRefreshKey 判断 changekey 是否匹配 listener 注册的 key
// 规则：
// - "a.b.c" 匹配 "a.b.c"、"a.b"（前缀匹配）
// - "a.b.c" 不匹配 "a"、"a.c"
// - "a.b[1]" 匹配 "a.b"、"a.b[1]"
// - 所有比较忽略大小写
```

## 自动刷新链路（从 Binder 到 Watcher）

```
Binder.Bind(&cfg, "app")
  │
  └── BindValue() 内部自动调用
       │
       WatcherM.RegChangeListener(key, func(k, v string) {
           // 配置变更时重新绑定
           cpb.BindValue(ctx, v, param)
       })
```

这意味着：

1. 应用启动时 `Binder.Bind()` 绑定配置
2. 配置发生变更
3. Watcher 检测到变更
4. 通知 Listener
5. Listener 重新绑定结构体
6. 应用自动使用新配置

## Nacos 配置 Watcher

`contribute/agnacos/config/nacos_watcher.go` 实现了基于 Nacos 的远程配置监听：

```go
type NacosConfigWatcher struct {
    client      naming_client.INamingClient
    configCli   config_client.IConfigClient
    dataId      string
    group       string
    // ...
}

func (w *NacosConfigWatcher) Start(ctx context.Context, callback ChangePropertySources) {
    // 监听 Nacos 配置变更
    // 变更时解析新配置 → 构造新 PropertySource → 回调
}
```
