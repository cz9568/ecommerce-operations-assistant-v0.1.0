# 电商运营助手

面向中小电商团队的单品运营闭环工作台。当前仓库已完成可开发基础环境：FastAPI 后端、Vue 3 前端、MySQL 结构与迁移、健康检查、认证基础、测试与代码质量配置。

## 目录

```text
backend/                 FastAPI 应用
frontend/                Vue 3 + TypeScript 应用
scripts/                 准备、启动和管理员创建脚本
storage/                 本地开发素材目录
电商运营助手.md           原始需求
电商运营助手-需求分析与任务拆解.md
技术方案与开发约定.md
```

## 环境要求

- Python 3.12+
- uv 0.11+
- Node.js 20+
- MySQL 8.x

## 本地启动

1. 将 `.env.example` 中缺少的配置补充到根目录 `.env`。不要提交 `.env`。
2. 一键同步依赖、执行数据库迁移并验证环境：

```powershell
.\scripts\bootstrap.ps1
```

3. 首次创建应用管理员（密码交互输入，不写入命令历史）：

```powershell
.\scripts\create-admin.ps1
```

4. 启动后端：

```powershell
.\scripts\start-backend.ps1
```

5. 在另一个终端启动前端：

```powershell
.\scripts\start-frontend.ps1
```

6. 访问：

- 前端：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/api/v1/health/live>
- 数据库就绪检查：<http://127.0.0.1:8000/api/v1/health/ready>

## 验证命令

```powershell
uv run pytest
uv run ruff check backend
Set-Location frontend
npm run type-check
npm run build
```

## 安全约定

- `.env`、平台凭证、模型密钥不得提交到版本库。
- 开发数据库使用项目专用账号，不使用 MySQL `root`。
- 文本默认使用 Qwen-Max，图片优先使用 `qwen-image-3.0`；自动化测试仍使用 Mock Provider。
- 当前存储默认为本地 `storage/`，部署前再切换对象存储。

## 数据库迁移

当前迁移包含 28 张项目表，覆盖用户权限、令牌撤销、店铺商品、SKU 库存、竞品、AI 诊断、创意方案、异步任务、素材、链接、投放、经营数据、复盘、导入、审计和系统设置。

```powershell
& '.\.venv\Scripts\alembic.exe' current
& '.\.venv\Scripts\alembic.exe' upgrade head
& '.\.venv\Scripts\alembic.exe' check
```

## 已实现接口

- `POST /api/v1/auth/login`：用户名和密码登录。
- `GET /api/v1/auth/me`：查询当前用户。
- `POST /api/v1/auth/logout`：撤销当前访问令牌。
- `GET /api/v1/users`：管理员分页查询用户。
- `POST /api/v1/users`：管理员创建用户。
- `PATCH /api/v1/users/{user_id}`：管理员更新角色、状态、显示名称或密码。
- `GET /api/v1/health/live`、`GET /api/v1/health/ready`：服务健康检查。

模型配置连通性可使用最小文本请求验证，脚本不会输出 API Key：

```powershell
& '.\.venv\Scripts\python.exe' -m backend.scripts.verify_qwen
```
