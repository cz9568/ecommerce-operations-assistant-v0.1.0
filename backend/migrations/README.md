# 数据库迁移

迁移配置从项目根目录 `.env` 读取数据库连接，不在迁移文件或日志中保存密码。

```powershell
# 查看当前版本
uv run alembic current

# 应用全部迁移
uv run alembic upgrade head

# 模型变更后生成新迁移
uv run alembic revision --autogenerate -m "change description"
```

自动生成后必须人工检查迁移内容，尤其是删除列、修改类型和数据回填操作。

