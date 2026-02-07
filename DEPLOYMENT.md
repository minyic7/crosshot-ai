# 🚀 部署指南

## 快速部署到 QNAP NAS

### 前置要求

- QNAP NAS 已安装 **Container Station**
- 已启用 SSH 访问
- GitHub 仓库已设置为 Public（或配置了 GHCR 访问权限）

---

## 📋 步骤 1: 准备 NAS 环境

### 1.1 SSH 连接到 QNAP

```bash
ssh admin@your-nas-ip
```

### 1.2 创建项目目录

```bash
# 进入 Container Station 的数据目录
cd /share/Container

# 创建项目目录
mkdir -p crosshot-ai
cd crosshot-ai

# 创建数据和日志目录
mkdir -p data logs
```

### 1.3 下载配置文件

```bash
# 方法 1: 直接从 GitHub 下载
wget https://raw.githubusercontent.com/你的用户名/crosshot-ai/main/docker-compose.yml
wget https://raw.githubusercontent.com/你的用户名/crosshot-ai/main/.env.example

# 方法 2: 或者使用 git clone
git clone https://github.com/你的用户名/crosshot-ai.git
cd crosshot-ai
```

---

## 📋 步骤 2: 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件
vi .env
```

修改以下内容：
```bash
GITHUB_USERNAME=你的GitHub用户名  # ← 改成你的用户名
```

---

## 📋 步骤 3: 启动服务

### 3.1 拉取镜像并启动

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f crawler
```

### 3.2 验证服务状态

```bash
# 查看运行的容器
docker ps

# 应该看到两个容器：
# - crawler (你的爬虫)
# - watchtower (自动更新服务)
```

---

## 📋 步骤 4: 测试自动更新

### 4.1 本地修改代码

```bash
# 在你的本地电脑上
cd crosshot-ai
echo "# Test change" >> apps/crawler/__main__.py
git add .
git commit -m "test: trigger auto deployment"
git push
```

### 4.2 观察自动部署过程

```bash
# 在 NAS 上查看 Watchtower 日志
docker logs -f watchtower

# 你会看到类似输出：
# - Checking for updates
# - Found new image
# - Stopping container crawler
# - Starting new container
```

完整流程：
```
本地 git push
    ↓ (约 2-5 分钟)
GitHub Actions 构建镜像
    ↓ (镜像推送到 GHCR)
    ↓ (最多 5 分钟)
Watchtower 检测到更新
    ↓
发送 SIGTERM 信号给 crawler
    ↓ (最多 60 秒)
Crawler 保存进度并退出
    ↓
Watchtower 拉取新镜像
    ↓
启动新容器
    ↓
Crawler 从保存的进度继续运行
```

**总耗时：5-10 分钟完全自动部署！**

---

## 🔧 常用命令

### 查看日志
```bash
# 实时查看爬虫日志
docker-compose logs -f crawler

# 查看最近 100 行
docker-compose logs --tail=100 crawler

# 查看 Watchtower 日志
docker-compose logs -f watchtower
```

### 手动更新
```bash
# 强制拉取最新镜像并重启
docker-compose pull
docker-compose up -d
```

### 停止服务
```bash
# 停止所有服务
docker-compose down

# 停止但保留容器
docker-compose stop

# 重启服务
docker-compose restart crawler
```

### 查看资源使用
```bash
# 查看容器资源使用情况
docker stats crawler watchtower
```

---

## 🐛 故障排查

### 1. 容器无法启动

```bash
# 查看详细日志
docker-compose logs crawler

# 检查镜像是否存在
docker images | grep crawler

# 手动拉取镜像测试
docker pull ghcr.io/你的用户名/crawler:latest
```

### 2. Watchtower 无法访问镜像

如果仓库是私有的，需要配置认证：

```yaml
# docker-compose.yml 中添加
watchtower:
  environment:
    - REPO_USER=你的GitHub用户名
    - REPO_PASS=你的GitHub_TOKEN
```

### 3. 查看 Docker 权限

```bash
# 确保当前用户在 docker 组
id
groups

# 如果没有，添加到 docker 组
sudo usermod -aG docker $USER
```

### 4. 清理磁盘空间

```bash
# 清理未使用的镜像
docker image prune -a

# 清理所有未使用的资源
docker system prune -a --volumes
```

---

## 📊 监控和通知

### 配置 Watchtower 通知（可选）

编辑 `.env` 文件添加通知 URL：

```bash
# Discord 通知
WATCHTOWER_NOTIFICATION_URL=discord://token@id

# Slack 通知
WATCHTOWER_NOTIFICATION_URL=slack://token@channel

# 邮件通知
WATCHTOWER_NOTIFICATION_URL=smtp://username:password@host:port/?from=sender@example.com
```

---

## 🔒 安全建议

1. **使用私有仓库**（推荐）
   - GitHub 仓库设为 Private
   - 配置 Personal Access Token

2. **限制 SSH 访问**
   ```bash
   # 修改 SSH 端口
   # 使用密钥认证而非密码
   ```

3. **定期备份数据**
   ```bash
   # 备份数据目录
   tar -czf backup-$(date +%Y%m%d).tar.gz data/
   ```

---

## 📚 参考资源

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Watchtower 文档](https://containrrr.dev/watchtower/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [QNAP Container Station 指南](https://www.qnap.com/zh-cn/software/container-station)

---

## ✅ 部署完成检查清单

- [ ] Container Station 已安装
- [ ] SSH 访问已配置
- [ ] 项目目录已创建
- [ ] docker-compose.yml 已下载
- [ ] .env 文件已配置
- [ ] 服务已启动（`docker ps` 显示 2 个容器）
- [ ] 日志正常（`docker-compose logs -f crawler`）
- [ ] 测试自动更新成功

**恭喜！你的持续运行爬虫已成功部署！** 🎉
