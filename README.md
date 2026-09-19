# 电商运营助手

面向中小电商团队的单品运营闭环工作台。当前仓库已完成 FastAPI 后端、Vue 3 前端、MySQL 结构与迁移、认证与 RBAC、商品库存、竞品运营、AI 诊断与创意生成、素材审核、投放与复盘、批量导入、演示数据、运营工作台和系统设置。

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

6. 在第三个终端启动图片/视频生成 Worker：

```powershell
.\scripts\start-worker.ps1
```

开发联调建议设置 `GENERATION_PROVIDER=mock`；接入百炼异步媒体接口时改为 `dashscope`。Worker 支持多并发、优雅停止、领取锁、心跳、超时恢复和指数退避。

需要手工执行一次超时与过期锁扫描时：

```powershell
& '.\.venv\Scripts\python.exe' -m backend.scripts.generation_worker --scan-only
```

7. 访问：

- 前端：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8011/docs>
- 存活检查：<http://127.0.0.1:8011/api/v1/health/live>
- 数据库就绪检查：<http://127.0.0.1:8011/api/v1/health/ready>

> 后端固定使用 `8011` 端口；`8000` 端口保留给本机的 `FlClashCore`。

## 验证命令

```powershell
uv run pytest
uv run ruff check backend
Set-Location frontend
npm run type-check
npm run build
```

发布前完整质量门禁（测试、构建、密钥扫描、依赖漏洞和高危静态检查）：

```powershell
.\scripts\run-quality-gates.ps1
```

## Docker 部署

Docker Compose 同时启动 MySQL、API、Worker 和 Nginx 前端：

```powershell
docker compose up -d --build
```

- Web：<http://127.0.0.1:8080>
- API：<http://127.0.0.1:8011>
- `8000` 端口始终保留给 `FlClashCore`。

生产启动、备份恢复、升级和回滚详见 [部署升级与回滚](docs/部署升级与回滚.md)。

## 发布包

```powershell
.\scripts\build-release.ps1 -Version 0.1.0
```

脚本在所有质量门禁通过后生成 ZIP 和 SHA-256 文件。验收证据见 [测试安全与性能报告](docs/测试安全与性能报告.md)、[验收记录](docs/验收记录-v0.1.0.md) 和 [管理员与演示手册](docs/管理员与演示手册.md)。

## 安全约定

- `.env`、平台凭证、模型密钥不得提交到版本库。
- 开发数据库使用项目专用账号，不使用 MySQL `root`。
- 普通文本模型保留 `LLM_MODEL` 配置，严格结构化任务默认使用 Qwen-Plus；图片优先使用 `qwen-image-3.0`，自动化测试仍使用 Mock Provider。
- 当前存储默认为本地 `storage/`；供应商结果会先校验 HTTPS 来源、地址、重定向、大小、MIME 和文件签名，再以 SHA-256 可追溯方式转存。部署前可按统一存储接口扩展对象存储。

## 数据库迁移

当前迁移包含 33 张项目表，覆盖用户权限、令牌撤销、店铺商品、SKU 库存、库存建议、竞品、AI 诊断、AI 用量日志、创意方案及其版本历史、异步任务、素材、链接、投放、经营数据、复盘及其版本历史、导入、审计和系统设置。

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
- `GET/POST /api/v1/stores`：查询或创建店铺。
- `GET/PATCH /api/v1/stores/{store_id}`：店铺详情或更新。
- `GET /api/v1/stores/{store_id}/summary`：商品、SKU、低库存及平台账号聚合统计。
- `GET/POST /api/v1/stores/{store_id}/platform-accounts`：查询或创建脱敏平台账号。
- `GET/PATCH /api/v1/platform-accounts/{account_id}`：平台账号详情或更新。
- `POST /api/v1/platform-accounts/{account_id}/authorization/start`：开始授权占位流程。
- `POST /api/v1/platform-accounts/{account_id}/authorization/callback`：处理安全白名单回调。
- `POST /api/v1/platform-accounts/{account_id}/authorization/revoke`：撤销授权状态。
- `GET/POST /api/v1/products`：筛选查询或创建商品。
- `GET/PATCH/DELETE /api/v1/products/{product_id}`：商品详情、更新或软删除。
- `PATCH /api/v1/products/{product_id}/status`：启用或停用商品。
- `GET/POST /api/v1/products/{product_id}/mappings`：查询或创建平台商品映射。
- `PATCH/DELETE /api/v1/products/{product_id}/mappings/{mapping_id}`：更新或删除归属校验后的映射。
- `GET/POST /api/v1/products/{product_id}/skus`：分页查询或创建 SKU。
- `GET/PATCH /api/v1/products/{product_id}/skus/{sku_id}`：SKU 详情或更新。
- `PATCH /api/v1/products/{product_id}/skus/{sku_id}/status`：启用或停用 SKU。
- `GET /api/v1/inventory`、`GET /api/v1/inventory/low-stock`：库存和低库存分页查询。
- `GET/PATCH /api/v1/products/{product_id}/skus/{sku_id}/inventory`：库存详情或预警/库位配置。
- `POST /api/v1/products/{product_id}/skus/{sku_id}/inventory/adjustments`：并发安全地调整库存或锁定量。
- `GET /api/v1/products/{product_id}/skus/{sku_id}/inventory/movements`：分页查询库存流水。
- `POST /api/v1/stores/{store_id}/inventory-advice/generate`：生成可解释的店铺库存建议快照。
- `GET /api/v1/stores/{store_id}/inventory-advice`：查询最新库存建议。
- `GET /api/v1/stores/{store_id}/inventory-advice/runs`：分页查询建议生成历史。
- `GET /api/v1/stores/{store_id}/inventory-advice/runs/{run_id}`：查询指定建议批次。
- `GET/POST /api/v1/products/{product_id}/competitors`：筛选查询或创建竞品。
- `GET/PATCH/DELETE /api/v1/products/{product_id}/competitors/{competitor_id}`：竞品详情、更新或软停用。
- `POST /api/v1/products/{product_id}/competitors/import-url-tasks`：创建合规的公开链接解析任务。
- `GET /api/v1/products/{product_id}/link-parse-tasks`：查询解析任务进度与错误。
- `POST /api/v1/products/{product_id}/link-parse-tasks/{task_id}/run`：执行或重试公开链接解析。
- `POST /api/v1/products/{product_id}/link-parse-tasks/{task_id}/apply`：人工选择字段并回填竞品。
- `GET/POST/PATCH /api/v1/products/{product_id}/competitors/{competitor_id}/monitor`：查询或配置竞品监控。
- `POST /api/v1/products/{product_id}/competitors/{competitor_id}/monitor/run`：立即生成监控快照。
- `GET /api/v1/products/{product_id}/competitors/{competitor_id}/monitor/snapshots`：查询监控快照和变化字段。
- `POST /api/v1/workspace/competitor-monitors/run-due`：原子领取并运行到期监控。
- `POST /api/v1/products/{product_id}/diagnoses/generate`：基于当前业务快照生成七段结构化商品诊断。
- `GET /api/v1/products/{product_id}/diagnoses`：分页查询商品诊断历史。
- `GET/PATCH /api/v1/products/{product_id}/diagnoses/{diagnosis_id}`：查询或并发安全地编辑诊断。
- `POST /api/v1/products/{product_id}/creative-plans/generate`：从最新或指定诊断生成至少三个主图方向或视频脚本。
- `GET /api/v1/products/{product_id}/creative-plans`：按类型、状态分页查询创意方案。
- `GET/PATCH /api/v1/products/{product_id}/creative-plans/{plan_id}`：查询或并发安全地编辑方案。
- `POST /api/v1/products/{product_id}/creative-plans/{plan_id}/status`：执行草稿、选中、归档状态流转。
- `GET /api/v1/products/{product_id}/creative-plans/{plan_id}/revisions`：查询不可变版本历史。
- `POST /api/v1/products/{product_id}/generation-jobs`：从已选中的精确方案版本幂等创建异步图片/视频任务。
- `GET /api/v1/products/{product_id}/generation-jobs`：按类型和状态分页查询商品生成任务。
- `GET /api/v1/products/{product_id}/generation-jobs/{job_id}`：查询任务进度、结果或稳定错误信息。
- `GET /api/v1/products/{product_id}/generation-jobs/{job_id}/events`：查询完整任务事件时间线。
- `POST /api/v1/products/{product_id}/generation-jobs/{job_id}/cancel`：按最新任务版本取消等待中或运行中的任务。
- `POST /api/v1/products/{product_id}/generation-jobs/{job_id}/retry`：在尝试次数上限内重新排队失败或超时任务。
- `GET /api/v1/products/{product_id}/assets`：按媒体、审核和文件状态分页查询商品素材。
- `GET /api/v1/products/{product_id}/assets/{asset_id}`：查询素材版本、来源、校验信息和审核数据。
- `GET /api/v1/products/{product_id}/assets/{asset_id}/content`：登录鉴权后安全读取图片或视频内容。
- `PATCH /api/v1/products/{product_id}/assets/{asset_id}`：乐观锁更新场景、评分、标签和备注。
- `POST /api/v1/products/{product_id}/assets/{asset_id}/review`：审核通过、驳回或撤回审核。
- `POST /api/v1/products/{product_id}/assets/{asset_id}/check`：重新检查素材文件存在性和 SHA-256。
- `POST /api/v1/products/{product_id}/assets/sync/{job_id}`：幂等补同步历史成功任务的生成结果。
- `POST /api/v1/products/{product_id}/promotion-links/generate`：生成三类推广链接场景建议。
- `GET/POST /api/v1/products/{product_id}/promotion-links`：分页查询或创建推广链接。
- `GET/PATCH /api/v1/products/{product_id}/promotion-links/{link_id}`：查询或并发安全地编辑、停用推广链接。
- `GET /api/v1/products/{product_id}/promotion-links/{link_id}/statistics`：查询有效、过滤和独立访客点击统计。
- `GET /api/v1/r/{tracking_code}`：校验有效链接、隐私化记录点击并跳转。
- `POST /api/v1/products/{product_id}/ad-recommendations/generate`：基于已审核素材和有效链接生成八类投放建议。
- `GET /api/v1/products/{product_id}/ad-recommendations`：分页查询投放建议历史。
- `GET/PATCH /api/v1/products/{product_id}/ad-recommendations/{recommendation_id}`：查询或并发安全地编辑待确认建议。
- `PATCH /api/v1/products/{product_id}/ad-recommendations/{recommendation_id}/confirmation`：人工确认或驳回建议。
- `POST /api/v1/products/{product_id}/ad-experiments/generate`：从已确认建议创建实验草稿。
- `GET /api/v1/products/{product_id}/ad-experiments`：分页查询投放实验。
- `GET/PATCH /api/v1/products/{product_id}/ad-experiments/{experiment_id}`：查询实验或更新状态与草稿内容。
- `GET/POST /api/v1/products/{product_id}/performance-records`：分页查询或录入经营数据。
- `GET /api/v1/products/{product_id}/performance-records/summary`：按有效记录汇总经营指标。
- `GET/PATCH/DELETE /api/v1/products/{product_id}/performance-records/{record_id}`：查询、完整更新或软作废经营记录。
- `POST /api/v1/products/{product_id}/review-reports/generate`：按周期快照生成四段结构化运营复盘。
- `GET /api/v1/products/{product_id}/review-reports`：分页查询复盘报告历史。
- `GET/PATCH /api/v1/products/{product_id}/review-reports/{report_id}`：查询或并发安全地编辑复盘报告。
- `GET /api/v1/products/{product_id}/review-reports/{report_id}/revisions`：查询不可变复盘内容版本。
- `GET /api/v1/imports/templates/{import_type}`：下载商品、SKU 库存或经营数据 CSV 模板。
- `POST /api/v1/imports/{import_type}/upload`：上传 CSV 并生成不写业务表的逐行校验预览。
- `GET /api/v1/imports`、`GET /api/v1/imports/{batch_id}`：查询导入批次与逐行结果。
- `POST /api/v1/imports/{batch_id}/confirm`：幂等确认导入，支持逐行部分成功。
- `GET /api/v1/imports/{batch_id}/errors.csv`：下载带错误列、错误码和原因的失败行。
- `POST /api/v1/demo-data/initialize`：管理员幂等初始化或校准完整演示业务链路。
- `GET /api/v1/dashboard`：按平台聚合工作台指标、店铺、商品、低库存、生成任务和复盘。
- `GET /api/v1/settings`：管理员查询模型、系统与队列配置，敏感值不返回明文。
- `PATCH /api/v1/settings/{group}`：管理员校验并更新指定配置分组，保存审计记录。
- `GET /api/v1/health/live`、`GET /api/v1/health/ready`：服务健康检查。

## 已实现前端功能

- 登录、登录态保持、刷新恢复、退出和 401 失效回登录。
- 路由守卫、角色权限菜单、403/404 页面和响应式应用壳。
- 统一 API 客户端、标准错误反馈、通用表单弹窗和分页表格容器。
- 用户筛选、分页、创建、编辑、启停用和角色管理。
- 运营工作台支持平台筛选、指标、店铺卡片、商品池、库存预警、最近任务/复盘和空环境演示引导。
- 店铺列表/详情/编辑、库存概览、平台账号占位授权和库存建议。
- 商品列表/创建/编辑和九标签详情工作区，支持 URL 直达与未保存离开提醒。
- 平台商品映射、SKU 维护、库存配置/调整、低库存预警和库存流水查询。
- 竞品维护、字段来源标识、公开链接解析任务、错误重试和人工选择回填。
- 竞品监控配置、立即执行、失败提示、历史快照变化和人工采用。
- 商品诊断生成确认、数据缺失提示、七段结构化展示、人工编辑和历史版本选择；查看人员只读。
- 主图方向卡片、视频脚本/分镜编辑、同类唯一选中、归档保护和不可变版本历史；选中方案可直接创建异步媒体任务并立即返回任务编号。
- 商品生成任务页支持类型/状态筛选、进度自动刷新、失败退避、详情、生成结果、错误信息、事件时间线，以及按权限显示的取消和重试操作。
- 商品素材库支持图片/视频网格、安全预览、媒体/审核/文件状态筛选、版本与来源追溯、评分、场景、标签、备注、文件检查和审核；查看人员只读。
- 推广链接工作区支持场景建议、UTM 配置、追踪地址复制、编辑/停用，以及有效点击、过滤点击和独立访客日统计。
- 投放工作区支持选择已审核素材和有效链接生成八段建议、人工确认/驳回、实验草稿编辑和严格状态流转；全部文案明确不执行真实投放。
- 经营复盘工作区支持指标总览、经营记录录入/编辑/作废、关联方案/素材/链接/实验、复盘生成/编辑/版本时间线，以及从复盘直接开启并追溯下一轮诊断；经营数据导入已接入统一导入中心。
- 导入中心支持三类标准模板下载、CSV 拖拽上传、字段说明、确认前逐行校验与影响范围、错误行下载、部分成功结果和历史批次回看；经营复盘页面可直接进入经营数据导入。
- 管理员可从导入中心幂等初始化带【演示】标识的完整样例，样例覆盖从店铺建档到复盘开启下一轮诊断的全链路，且不调用真实模型或广告平台。
- 管理员可管理模型、系统和 Worker 队列配置，页面标明环境/数据库来源及立即、新请求或重启 Worker 生效；密钥只写不回显。

## AI Provider 与结构化输出

- 未配置模型密钥或将 `LLM_MODEL` 设为 `mock` 时，使用确定性的 Mock Provider。
- 配置 Qwen OpenAI 兼容地址后，支持超时、重试、进程内限流、结构修复和稳定错误码；`LLM_STRUCTURED_MODEL` 默认使用支持严格 JSON Schema 的 `qwen-plus`。
- 诊断、主图方案、视频脚本、投放建议和复盘均有带版本的 Prompt 与严格 JSON Schema。
- 商品诊断成功后保存输入快照、原始输出、结构化字段、模型和 Prompt/Schema 版本；失败只写脱敏用量日志，不创建伪诊断。
- 图片/视频生成统一走 `MediaAdapter`，提供确定性 Mock 与 DashScope 实现；真实适配器采用“异步提交 + Worker 轮询”，验证 HTTPS 结果、图片尺寸和视频时长。
- 任务保存不可变方案快照、模型和生成参数；Worker 会在任务成功前将真实平台临时结果转存到持久化素材库，重复同步不会创建重复素材。

正式库首次使用前需先运行 `scripts/create-admin.ps1` 创建应用管理员，随后从前端登录。

模型配置连通性可使用最小文本请求验证，脚本不会输出 API Key：

```powershell
& '.\.venv\Scripts\python.exe' -m backend.scripts.verify_qwen
```
