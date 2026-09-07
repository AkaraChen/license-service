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

生产站点为 <https://shukka-license.akr.moe/>，托管于 Netlify 项目
[`shukka-license`](https://app.netlify.com/projects/shukka-license)。
`.github/workflows/docs-deploy.yml` 在每次推送到 `main` 时使用锁定依赖严格构建，
然后将 `site/` 发布到生产；也可以在 GitHub Actions 手动运行该工作流。
其他分支不会发布。构建失败不会替换线上版本。

部署需要在此仓库配置 Actions Secret `NETLIFY_AUTH_TOKEN`，项目 ID 直接记录在工作流中。
令牌失效时更新此 Secret，再重新运行工作流。
Cloudflare 的 `shukka-license.akr.moe` 使用 DNS-only CNAME 指向
`shukka-license.netlify.app`；HTTPS 证书由 Netlify 管理。
需要回滚时，在 Netlify 的 Deploys 中选择之前的成功部署并发布。
