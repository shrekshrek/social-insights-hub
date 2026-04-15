# 开发流程快查

> 后端先行：先交付稳定 API，再开发前端，减少等待和返工。
> 新模块完整实现步骤见 [MODULAR_DEVELOPMENT.md](./MODULAR_DEVELOPMENT.md)。

---

## 阶段 0：设计

在动手写代码前先想清楚：

- **数据库**：需要哪些新表？字段和关系怎么设计？
- **API**：URL 路径、HTTP 方法、请求/响应结构
- **权限**：需要哪些 `target:action` 组合？页面访问权限和数据操作权限分别是什么？

---

## 阶段 1：后端

```
models.py         ← 定义 SQLAlchemy 数据模型
    ↓
schemas.py        ← 定义 Pydantic 请求/响应模型
    ↓
service.py        ← 实现业务逻辑
    ↓
router.py         ← 定义 API 端点，引用 service
    ↓
main.py           ← include_router() 注册路由
    ↓
rbac/init_data.py ← 注册权限（重启后自动同步）
rbac/dependencies.py ← 添加权限依赖快捷函数
```

```bash
pnpm be:migrate:make "描述"   # 生成迁移脚本
pnpm be:migrate:up            # 应用迁移
pnpm dev                      # 重启服务，权限自动同步
# 打开 http://localhost:8000/docs 测试所有端点
pnpm be:lint                  # 检查代码
```

---

## 阶段 2：前端

```
layers/[module]/composables/use[Module]Api.ts  ← 封装 API 调用
    ↓
layers/[module]/pages/                          ← 实现页面和组件
    ↓
layers/[module]/nuxt.config.ts                 ← Layer 配置
    ↓
nuxt.config.ts（根）                            ← extends 注册 Layer
    ↓
config/permissions.ts                          ← 添加权限常量
config/routes.ts                               ← 配置路由权限和导航
```

```bash
pnpm fe:typecheck   # 类型检查
pnpm fe:lint        # lint 检查
```

---

## 阶段 3：联调

```bash
# 完整检查
pnpm fe:typecheck && pnpm be:lint && pnpm be:test
```

- 登录后访问新页面，验证路由守卫生效
- 用不同权限的账号测试访问控制
- 检查后端日志确认新权限已同步
