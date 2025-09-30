# 权限系统深度指南

本文档深入介绍权限系统的技术原理、同步机制和性能优化。

> 📝 **寻找模块开发流程？** 请查看 [模块化开发指南](./MODULAR_DEVELOPMENT.md)

## 📋 概述

本项目采用**代码驱动**的RBAC（基于角色的访问控制）系统，核心特性：

- ✅ **代码定义权限**：权限在代码中定义，确保版本控制和可追溯
- ✅ **自动同步**：启动时自动同步代码定义与数据库，保持一致性  
- ✅ **完全自动化**：支持权限增删改，无需手动SQL操作
- ✅ **开发友好**：使用模板函数，一行代码创建模块权限集
- ✅ **生产安全**：权限变更可审计，支持回滚

## 🏗️ 设计理念

### 为什么选择代码驱动？

| 对比项 | 传统动态权限 | 代码驱动权限 | 
|--------|------------|------------|
| **数据源** | UI界面管理 | 代码文件定义 |
| **版本控制** | 难以追溯 | ✅ Git完整记录 |
| **环境一致性** | 容易偏差 | ✅ 代码保证一致 |
| **团队协作** | 冲突风险高 | ✅ 代码审查机制 |
| **部署复杂度** | 需要数据迁移 | ✅ 自动同步 |
| **权限审计** | 依赖数据库 | ✅ 代码历史 |

### 核心原则

1. **单一数据源**：代码是权限配置的唯一真实来源
2. **声明式配置**：描述"应该是什么"，而非"如何变成"
3. **自动化同步**：系统自动保持代码与数据库一致
4. **开发者友好**：模板化、零配置的开发体验

## 目录

- [权限架构](#权限架构)
- [快速开始](#快速开始)
- [权限管理操作](#权限管理操作)
- [最佳实践](#最佳实践)
- [技术原理](#技术原理)
- [故障排除](#故障排除)

## 权限架构

### 权限模型

权限系统使用 `target + action` 结构：
- `target`: 目标模块（如: user, reports, dashboard）
- `action`: 操作类型（如: access, read, write, delete）

### 配置方式
- 所有路由权限在 `config/routes.ts` 的 `ROUTE_CONFIG` 中管理
- 权限常量在 `config/permissions.ts` 中定义
- 路由守卫分3层检查：公开页面 → 登录 → 权限

### 核心文件

权限系统主要由以下文件组成：
- `config/permissions.ts` - 权限常量定义
- `config/routes.ts` - 路由权限配置
- `composables/usePermissions.ts` - 权限检查逻辑  
- `middleware/route-guard.global.ts` - 路由守卫

## 快速开始

### 权限格式

权限使用结构化对象 `{target: string, action: string}`：
- `target`: 目标模块（如: user, dashboard, reports）
- `action`: 操作类型（如: access, read, write, delete）

### 角色策略

- **super_admin**: 拥有所有权限
- **admin**: 拥有管理权限（除核心删除外）
- **user**: 仅拥有明确分配的权限


## 权限管理操作

### 角色权限分配

操作路径：`/rbac/roles/{id}/permissions`

步骤：
1. 进入角色管理页面
2. 选择要配置的角色
3. 点击"编辑权限"
4. 使用权限分组界面分配权限
5. 保存配置

### 用户角色分配

操作路径：`/users/{id}/roles`

步骤：
1. 进入用户管理页面
2. 选择要配置的用户
3. 点击"编辑角色"
4. 选择适当的角色
5. 保存配置

## 最佳实践

### 权限颗粒度

**简单模块**：
```python
# 仅页面访问权限
*create_module_permissions("dashboard", ["access"])
```

**标准模块**：
```python
# 页面 + 查看 + 导出
*create_module_permissions("reports", ["access", "read", "export"])
```

**管理模块**：
```python
# 完整CRUD权限
*create_module_permissions("products", ["access", "read", "write", "delete", "export", "import"])
```

### 配置示例

```typescript
export const ROUTE_CONFIG = {
  // 无特殊权限要求（仅需登录）
  '/dashboard': { permission: null, label: '工作台', showInNav: true },
  '/profile': { permission: null },

  // 单一权限
  '/users': { permission: PERMISSIONS.USER_MGMT_ACCESS, label: '用户管理', showInNav: true },
  '/users/create': { permission: PERMISSIONS.USER_WRITE },

  // 多权限组合（必须全部满足）
  '/system/advanced': {
    permission: [PERMISSIONS.USER_WRITE, PERMISSIONS.ROLE_WRITE],
    label: '系统高级设置',
    showInNav: true,
  }
}
```

### 安全原则

1. 用户默认无权限，按需授权
2. 创建语义明确的角色，避免权限混乱
3. 定期检查用户权限，移除不必要的权限
4. 敏感操作使用独立权限

## 快速参考

### 权限模板函数

```python
# 标准模板
create_module_permissions(module_name, actions, display_names?, descriptions?)

# 常用actions组合
["access"]                           # 仅页面访问
["access", "read"]                   # 页面 + 查看
["access", "read", "write"]          # 页面 + 增改
["access", "read", "write", "delete"] # 完整CRUD
["access", "read", "export"]         # 页面 + 查看 + 导出
```

### 常用命令

```bash
# 开发环境启动（自动同步权限）
pnpm dev

# 权限检查
pnpm fe:typecheck
pnpm fe:lint

# 数据库迁移（用于结构变更，非权限）
pnpm be:migrate:make "description"
pnpm be:migrate:up
```

---

## 技术原理

### 权限同步机制

权限同步采用"声明式配置"模式：

1. **代码定义为唯一真实来源**：所有权限在 `init_data.py` 中定义
2. **启动时对比差异**：系统启动时自动对比代码定义与数据库状态
3. **自动执行变更**：增删改操作保持代码与数据库一致性

### 同步流程详解

```python
async def init_rbac_data(db: AsyncSession):
    # 1. 获取代码中定义的权限
    defined_permissions = {f"{p['target']}:{p['action']}" for p in BASE_PERMISSIONS}
    
    # 2. 获取数据库中现有权限
    db_permissions = {f"{r.target}:{r.action}" for r in db_result}
    
    # 3. 计算差异
    to_add = defined_permissions - db_permissions      # 需要添加
    to_delete = db_permissions - defined_permissions   # 需要删除
    to_update = defined_permissions & db_permissions   # 需要更新
    
    # 4. 执行同步操作
    # 删除 → 添加 → 更新
```

### 性能考虑

| 指标 | 典型值 | 说明 |
|------|--------|------|
| **同步耗时** | <200ms | 权限数量<1000时 |
| **并发安全** | ✅ 支持 | 幂等操作，支持多实例 |
| **内存占用** | ~1KB | 权限数据极小 |
| **启动影响** | 忽略不计 | 不影响整体启动时间 |

### 安全机制

1. **级联删除**：删除权限自动清理 `role_permissions` 关联
2. **事务保护**：所有变更在数据库事务中执行
3. **错误隔离**：权限同步失败不影响应用启动
4. **详细日志**：记录所有变更便于审计

### 故障排除

#### 权限同步失败

**常见原因**：
- 数据库连接问题
- SQL 语法错误（极少见）
- 权限模板定义错误

**解决方法**：
```bash
# 1. 检查后端日志
docker-compose logs backend | grep -E "(权限|Permission|ERROR)"

# 2. 验证数据库连接
docker-compose exec postgres_db psql -U postgres -d fastapi_db -c "SELECT 1;"

# 3. 检查权限定义语法
# 确保 init_data.py 中权限定义格式正确
```

#### 权限不生效

**可能原因**：
- 前端权限缓存未刷新
- 用户会话权限过期
- 权限分配问题

**解决方法**：
```bash
# 1. 刷新前端
# 刷新浏览器页面清除缓存

# 2. 重新登录
# 重新登录获取最新权限

# 3. 检查权限分配
docker-compose exec postgres_db psql -U postgres -d fastapi_db -c "
SELECT u.username, r.name as role, p.target, p.action 
FROM users u 
JOIN user_roles ur ON u.id = ur.user_id 
JOIN roles r ON ur.role_id = r.id 
JOIN role_permissions rp ON r.id = rp.role_id 
JOIN permissions p ON rp.permission_id = p.id 
WHERE u.username = 'admin';
"
```

#### 性能问题

**症状**：启动时间过长

**正常基准**：
- 权限同步：<200ms
- 总启动时间：主要取决于容器和依赖加载

**性能优化**：
```bash
# 1. 检查权限数量
docker-compose exec postgres_db psql -U postgres -d fastapi_db -c "
SELECT COUNT(*) as total_permissions FROM permissions;
"

# 2. 分析同步耗时
# 启动时观察日志中的同步时间戳

# 3. 数据库性能检查
# 确保数据库连接池配置合理
```

### 调试技巧

#### 查看权限同步日志

```bash
# 查看完整权限同步过程
docker-compose logs backend | grep -A 10 -B 5 "权限同步"

# 查看权限变更详情
docker-compose logs backend | grep -E "(添加权限|删除权限|更新权限)"
```

#### 权限数据检查

```bash
# 查看当前权限统计
docker-compose exec postgres_db psql -U postgres -d fastapi_db -c "
SELECT target, COUNT(*) as permission_count 
FROM permissions 
GROUP BY target 
ORDER BY permission_count DESC;
"

# 查看权限使用情况
docker-compose exec postgres_db psql -U postgres -d fastapi_db -c "
SELECT p.target, p.action, COUNT(rp.id) as assigned_roles
FROM permissions p
LEFT JOIN role_permissions rp ON p.id = rp.permission_id
GROUP BY p.target, p.action
ORDER BY assigned_roles DESC;
"
```

### 与传统权限系统对比

| 对比项 | 代码驱动权限 | 传统动态权限 |
|--------|-------------|-------------|
| **配置方式** | 代码文件 | UI界面 |
| **版本控制** | ✅ Git完整记录 | ❌ 难以追溯 |
| **环境一致性** | ✅ 代码保证 | ⚠️ 容易偏差 |
| **部署复杂度** | ✅ 自动同步 | ❌ 需要数据迁移 |
| **团队协作** | ✅ 代码审查 | ⚠️ 冲突风险 |
| **权限审计** | ✅ 代码历史 | ⚠️ 依赖数据库 |
| **学习成本** | 低 | 中等 |
| **灵活性** | 中等 | 高 |

### 最佳实践建议

1. **权限设计**：遵循最小权限原则，避免过度细化
2. **命名规范**：使用语义化的 target 和标准化的 action
3. **测试验证**：在测试环境先验证权限变更
4. **监控维护**：定期检查权限使用情况和性能指标
5. **文档更新**：权限变更时同步更新相关文档
