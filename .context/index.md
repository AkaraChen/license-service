# Shukka License 开发文档

Shukka License 是基于 Django 的单租户授权服务，提供管理员控制台、客户自助页面、
JSON API 和 OpenAPI 接口说明。

本目录（`.context/`）保存内部文档；对外部署说明在 `docs/`（[部署概览](../docs/deploy.md)、[数据库](../docs/database.md)、[Docker](../docs/docker.md)、[Kamal](../docs/kamal.md)）。

## 文档导航

- [Kamal 部署](kamal.md)：单服务器部署、HTTPS、持久化数据和运维命令。
- [本机部署验证](kamal-local-validation.md)：本机端到端验证步骤与环境差异。
- [安全修复记录](security-scan-2026-09-06.md)：安全扫描问题、修复措施和回归验证。

项目快速启动、配置项和 API 约定见仓库根目录的 `README.md`，完整协议见 `SPEC.md`。
运行 Django 服务后，可访问其 `/docs` 路径查看交互式 API 文档。

## 维护文档站点

在项目根目录执行：

```bash
uv sync --locked
uv run zensical serve
```

打开 <http://127.0.0.1:8001> 预览，修改 `docs/` 下的 Markdown 文件后自动刷新。
安装了 just 时，也可以使用 `just docs`。

```bash
uv run zensical build --strict
# 或 just docs-build
```

构建产物位于 `site/`。站点配置和导航位于 `zensical.toml`；新增页面后可在其中添加导航项。
正式部署时，在配置的 `[project]` 中填写实际的 `site_url`。
