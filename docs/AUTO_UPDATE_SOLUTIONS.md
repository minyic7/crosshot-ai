# 自动更新方案对比

## 问题：Watchtower API 不兼容

**原因**：
- Watchtower 容器内 Docker client 版本：1.25
- Docker Engine 最低要求：API 1.44+
- 版本差距太大，无法兼容

## 🔄 推荐的替代方案

### 方案 1: GitHub Actions + SSH ⭐⭐⭐ 推荐

**优点**：
- ✅ 简单可靠，无需额外工具
- ✅ CI/CD 完成后立即部署
- ✅ 支持任何 Docker 主机（NAS、VPS）
- ✅ 可以执行任意部署脚本

**缺点**：
- ❌ 需要配置 SSH 密钥
- ❌ NAS 需要允许 SSH 访问

**设置步骤**：

1. **生成 SSH 密钥（在 NAS 上）**：
   ```bash
   ssh-keygen -t ed25519 -C "github-actions"
   cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
   cat ~/.ssh/id_ed25519  # 复制私钥
   ```

2. **在 GitHub 添加 Secrets**：
   - 仓库 → Settings → Secrets → New repository secret
   - `NAS_HOST`: NAS 的 IP 或域名
   - `NAS_USER`: SSH 用户名
   - `NAS_SSH_KEY`: 私钥内容

3. **启用 workflow**：
   - 已创建: `.github/workflows/deploy-ssh.yml`
   - 镜像构建完成后自动触发

**工作流程**：
```
代码推送 → GitHub Actions 构建镜像 → 推送到 GHCR
    ↓
构建成功 → SSH 连接 NAS → docker compose pull → 重启容器
```

---

### 方案 2: Portainer Webhook ⭐⭐

**优点**：
- ✅ 图形化界面管理
- ✅ 无需 SSH
- ✅ 支持多种触发方式

**缺点**：
- ❌ 需要安装 Portainer
- ❌ 需要配置 webhook
- ❌ 额外的资源占用

**设置步骤**：

1. **安装 Portainer（在 NAS 上）**：
   ```bash
   docker volume create portainer_data
   docker run -d \
     -p 9000:9000 \
     --name portainer \
     --restart=always \
     -v /var/run/docker.sock:/var/run/docker.sock \
     -v portainer_data:/data \
     portainer/portainer-ce:latest
   ```

2. **创建 Webhook**：
   - 登录 Portainer (http://NAS_IP:9000)
   - Stacks → 选择 crosshot-ai → Webhooks
   - 创建 webhook，复制 URL

3. **在 GitHub 添加 Secret**：
   - `PORTAINER_WEBHOOK_URL`: Webhook URL

4. **启用 workflow**：
   - 已创建: `.github/workflows/deploy-to-nas.yml`

---

### 方案 3: 本地定时脚本 ⭐

**优点**：
- ✅ 完全本地控制
- ✅ 无需网络访问
- ✅ 可自定义逻辑

**缺点**：
- ❌ 不是实时更新（依赖 cron 间隔）
- ❌ 需要手动配置 crontab

**设置步骤**：

1. **给脚本执行权限**：
   ```bash
   chmod +x scripts/auto-update.sh
   ```

2. **配置 crontab（在 NAS 上）**：
   ```bash
   crontab -e
   ```

   添加：
   ```
   # 每 5 分钟检查 X 平台更新
   */5 * * * * /share/crosshot-ai/scripts/auto-update.sh x

   # 每 30 分钟检查小红书平台更新
   */30 * * * * /share/crosshot-ai/scripts/auto-update.sh xhs
   ```

3. **查看日志**：
   ```bash
   tail -f /var/log/crosshot-auto-update.log
   ```

---

### 方案 4: 修复 Watchtower (不推荐)

**可能的修复**：
```yaml
watchtower-x:
  image: containrrr/watchtower:latest
  environment:
    - DOCKER_API_VERSION=1.44  # 强制使用新版本 API
```

**问题**：
- ❌ Watchtower 内部 client 太旧，即使设置也可能不工作
- ❌ 不是长期解决方案

---

## 📊 方案对比总结

| 方案 | 实时性 | 复杂度 | 可靠性 | 推荐度 |
|------|--------|--------|--------|--------|
| GitHub Actions + SSH | ⭐⭐⭐ | 中 | ⭐⭐⭐ | ⭐⭐⭐ |
| Portainer Webhook | ⭐⭐⭐ | 中 | ⭐⭐ | ⭐⭐ |
| 本地定时脚本 | ⭐ | 低 | ⭐⭐⭐ | ⭐ |
| 修复 Watchtower | - | 高 | ⭐ | ❌ |

---

## 🎯 建议

### 开发测试阶段（现在）
使用**本地定时脚本**或**手动更新**：
```bash
# 手动更新 X 平台
./scripts/compose-helper.sh down x
docker compose -f docker-compose.yml -f docker-compose.x.yml pull
./scripts/compose-helper.sh up x
```

### 生产部署（NAS）
使用**GitHub Actions + SSH**：
- 代码推送后自动部署
- 无需额外服务
- 简单可靠

---

## 🚀 快速测试当前构建

等待 GitHub Actions 完成后，手动测试更新：

```bash
# 1. 拉取最新镜像
docker pull ghcr.io/minyic7/crosshot-ai/crawler:latest

# 2. 查看镜像创建时间（验证是新版本）
docker inspect ghcr.io/minyic7/crosshot-ai/crawler:latest | grep Created

# 3. 重启容器使用新镜像
./scripts/compose-helper.sh down x
./scripts/compose-helper.sh up x

# 4. 验证新功能（查看日志中的"平均互动"）
docker logs crawler-x-ai --tail 20 | grep "平均互动"
```

预期输出：
```
   - 平均互动: 2,456 点赞/条, 234 评论/条  # 🆕 新功能
```
