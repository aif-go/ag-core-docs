# ag-core 文档

> 企业级 Go 微服务框架 + 代码生成平台
>
> 源码：[aif-go/ag-core](https://github.com/aif-go/ag-core)（私有仓库）

## 在线文档

📖 **完整文档站**：[aif-go.github.io/ag-core-docs](https://aif-go.github.io/ag-core-docs)

## 核心能力

- **代码生成** — Excel 表结构 → YAML 定义 → Go 后端代码（ORM / DAO / protobuf / 微服务桩）
- **微服务基座** — 统一 App 启动器，集成配置、日志、加密、错误处理
- **多协议支持** — HTTP（Hertz） + RPC（Kitex）
- **基础设施集成** — Nacos / Redis / Kafka / GORM

## 技术栈

| 技术            | 用途          |
| ------------- | ----------- |
| Go 1.24       | 主力语言        |
| Hertz         | HTTP 框架     |
| Kitex         | RPC 框架      |
| GORM          | ORM         |
| Nacos         | 服务发现 + 配置中心 |
| Redis / Kafka | 缓存 / 消息队列   |

## 本地预览

```bash
# 安装依赖（首次）
python -m venv .venv && source .venv/bin/activate
pip install mkdocs-material mkdocs-roamlinks-plugin

# 启动本地服务
mkdocs serve

# 构建并部署到 GitHub Pages
mkdocs gh-deploy --force
```
