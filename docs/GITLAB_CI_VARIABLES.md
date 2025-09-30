# GitLab CI/CD 变量配置指南

## 📍 配置位置
项目设置 -> CI/CD -> Variables

## 🔑 需要配置的变量

| 变量名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `DEPLOY_HOST` | Variable | 生产服务器IP或域名 | `192.168.1.100` 或 `prod.example.com` |
| `DEPLOY_USER` | Variable | SSH登录用户名 | `deploy` 或 `ubuntu` |
| `SSH_PRIVATE_KEY` | Variable | SSH私钥（完整内容） | 见下方说明 |

## 📝 配置步骤

### 1. 进入GitLab变量设置
1. 打开GitLab项目页面
2. 点击左侧菜单 **Settings** -> **CI/CD**
3. 找到 **Variables** 部分，点击 **Expand** 展开

### 2. 添加变量
点击 **Add variable** 按钮，逐个添加：

#### DEPLOY_HOST
- **Key**: `DEPLOY_HOST`
- **Value**: 你的服务器地址
- **Type**: Variable
- **Environment scope**: All (default)
- **Protect variable**: ✅ 勾选（仅在受保护分支可用）
- **Mask variable**: ✅ 勾选（在日志中隐藏）

#### DEPLOY_USER
- **Key**: `DEPLOY_USER`
- **Value**: SSH用户名
- **Type**: Variable
- **Environment scope**: All (default)
- **Protect variable**: ✅ 勾选
- **Mask variable**: ✅ 勾选

#### SSH_PRIVATE_KEY
- **Key**: `SSH_PRIVATE_KEY`
- **Value**: SSH私钥的完整内容（包含头尾）
- **Type**: Variable
- **Environment scope**: All (default)
- **Protect variable**: ✅ 勾选
- **Mask variable**: ✅ 勾选

## 🔐 生成SSH密钥

### 1. 在本地生成新的SSH密钥对
```bash
# 生成ED25519密钥（推荐）
ssh-keygen -t ed25519 -f gitlab_deploy -C "gitlab-ci-deployment"

# 或生成RSA密钥
ssh-keygen -t rsa -b 4096 -f gitlab_deploy -C "gitlab-ci-deployment"
```

### 2. 将公钥添加到服务器
```bash
# 方法1: 使用ssh-copy-id
ssh-copy-id -i gitlab_deploy.pub user@your-server

# 方法2: 手动添加
cat gitlab_deploy.pub | ssh user@your-server "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### 3. 复制私钥内容到GitLab变量
```bash
# 查看私钥内容
cat gitlab_deploy

# 复制全部内容，包括：
# -----BEGIN OPENSSH PRIVATE KEY-----
# ...密钥内容...
# -----END OPENSSH PRIVATE KEY-----
```

## ⚠️ 注意事项

### 安全注意事项
- ✅ 始终勾选 **Protect variable** 选项
- ✅ 始终勾选 **Mask variable** 选项
- ❌ 不要在代码中硬编码任何敏感信息
- ❌ 不要将私钥文件提交到Git仓库

### 服务器准备
确保服务器满足以下条件：
- [ ] Docker和Docker Compose已安装
- [ ] `/app` 目录存在且有正确权限
- [ ] Git仓库已克隆到 `/app` 目录
- [ ] 已配置 `.env.production` 文件（项目根目录）

### 权限要求
部署用户需要有以下权限：
- 读写 `/app` 目录
- 执行 `docker` 和 `docker-compose` 命令
- 拉取Git仓库更新

## 🧪 测试部署

### 1. 手动触发部署
1. 进入 GitLab 项目的 **CI/CD** -> **Pipelines**
2. 点击 **Run pipeline**
3. 选择 `main` 分支
4. 点击 **Run pipeline**
5. 在 Pipeline 页面点击 **deploy:production** 旁的播放按钮

### 2. 查看部署日志
点击正在运行的Job查看实时日志

### 3. 验证部署结果
```bash
# 在服务器上检查容器状态
docker-compose -f docker-compose.prod.yml ps

# 查看服务日志
docker-compose -f docker-compose.prod.yml logs -f
```

## 🔄 切换为自动部署

如需推送到main分支后自动部署，编辑 `.gitlab-ci.yml`：

```yaml
deploy:production:
  # ... 其他配置 ...
  when: on_success  # 改为自动部署
  # 或直接删除 when 行
```

## 📚 相关文档

- [GitLab CI/CD 文档](https://docs.gitlab.com/ee/ci/)
- [GitLab CI/CD 变量](https://docs.gitlab.com/ee/ci/variables/)
- [SSH 密钥管理](https://docs.gitlab.com/ee/ci/ssh_keys/)