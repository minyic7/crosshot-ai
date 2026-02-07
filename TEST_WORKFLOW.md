# 测试工作流程

完整测试从部署到 CI/CD 自动更新的流程。

## 前置准备

1. **设置 GitHub 环境变量**
   ```bash
   # 创建 .env 文件（如果还没有）
   echo "GITHUB_USERNAME=你的GitHub用户名" > .env
   ```

2. **确保 GitHub Token 已配置**
   ```bash
   # 登录 GitHub Container Registry
   echo $GITHUB_TOKEN | docker login ghcr.io -u 你的GitHub用户名 --password-stdin
   ```

---

## 阶段 1: 本地构建测试

### 1.1 构建 Crawler 镜像

```bash
# 构建镜像
docker build -f apps/crawler/Dockerfile -t crawler:local .

# 验证镜像
docker images | grep crawler
```

### 1.2 本地运行单个实例

```bash
# 创建数据目录
mkdir -p data/test logs/test

# 运行测试实例
docker run --rm \
  -e PLATFORM=x \
  -e KEYWORDS="AI,Python,Web3" \
  -e MAX_RESULTS=20 \
  -e INTERVAL=60 \
  -e LOG_LEVEL=INFO \
  -v $(pwd)/data/test:/app/data \
  -v $(pwd)/logs/test:/app/logs \
  --name crawler-test \
  crawler:local
```

**预期输出:**
```
🚀 Crawler service starting...
📋 进程 ID: 1
🏷️  平台: x
🕷️  [x] 爬虫循环启动...
📋 [x] 配置:
   - 平台: x
   - 关键词: ['AI', 'Python', 'Web3']
   - 最大结果数: 20
🔍 [x] 开始爬取，关键词: ['AI', 'Python', 'Web3']
📱 [x] 平台: X (Twitter)
⏳ [x] 进度: 10/20 (50.0%)
✅ [x] 爬取完成: 20 个 post
💾 [x] Mock 数据已保存到: /app/data/mock_data_20260207_123456.json
📊 [x] 统计:
   - 总互动: 45,234 点赞, 1,234 评论
   - 媒体类型: {'image': 12, 'video': 6, 'gif': 2}
```

### 1.3 测试优雅停止

打开另一个终端:
```bash
# 发送停止信号
docker stop -t 60 crawler-test

# 或使用 Ctrl+C
```

**预期输出:**
```
⏸️  [x] 收到 SIGTERM 信号，准备优雅停止...
💾 [x] 正在保存进度...
✅ [x] 进度已保存到 /app/data/progress_x.json
👋 [x] Crawler service stopped gracefully
```

### 1.4 验证数据文件

```bash
# 查看保存的数据
ls -lh data/test/
cat data/test/progress_x.json | jq .
cat data/test/mock_data_*.json | jq '.items | length'
```

---

## 阶段 2: Docker Compose 多实例测试

### 2.1 启动 X 平台（3个实例）

```bash
# 使用帮助脚本
./scripts/compose-helper.sh up x

# 或直接使用 docker-compose
docker-compose -f docker-compose.yml -f docker-compose.x.yml up -d
```

### 2.2 查看运行状态

```bash
# 查看容器
docker ps --filter "label=platform=x"

# 查看日志（所有实例）
./scripts/compose-helper.sh logs x

# 查看特定实例日志
docker logs -f crawler-x-ai
```

**预期看到 3 个 crawler + 1 个 watchtower 运行:**
```
CONTAINER ID   IMAGE                          STATUS          NAMES
abc123         ghcr.io/.../crawler:latest     Up 10 seconds   crawler-x-ai
def456         ghcr.io/.../crawler:latest     Up 10 seconds   crawler-x-python
ghi789         ghcr.io/.../crawler:latest     Up 10 seconds   crawler-x-web3
jkl012         containrrr/watchtower:latest   Up 10 seconds   watchtower-x
```

### 2.3 验证数据分离

```bash
# 每个实例应该有独立的数据目录
tree -L 3 data/x/
```

**预期结构:**
```
data/x/
├── ai/
│   ├── mock_data_20260207_123456.json
│   └── progress_x.json
├── python/
│   ├── mock_data_20260207_123457.json
│   └── progress_x.json
└── web3/
    ├── mock_data_20260207_123458.json
    └── progress_x.json
```

### 2.4 启动小红书平台（4个实例）

```bash
./scripts/compose-helper.sh up xhs

# 验证运行
docker ps --filter "label=platform=xhs"
```

### 2.5 同时运行所有平台

```bash
./scripts/compose-helper.sh up all

# 查看所有容器
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

---

## 阶段 3: CI/CD 流程测试

### 3.1 提交代码触发 CI

```bash
# 查看当前状态
git status

# 提交 mock crawler 实现
git add apps/crawler/__main__.py
git commit -m "feat: add mock crawler implementation

- Simulate X/XHS/Douyin platform data
- Generate realistic engagement metrics
- Save JSON data files
- Support graceful shutdown during scraping
- Detailed progress logging

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# 推送到 GitHub（触发 CI/CD）
git push origin main
```

### 3.2 监控 GitHub Actions

1. 访问: `https://github.com/你的用户名/crosshot-ai/actions`
2. 查看 "Build and Push Crawler Image" workflow
3. 等待构建完成（约 3-5 分钟）

**预期步骤:**
```
✅ Checkout code
✅ Set up Docker Buildx
✅ Log in to GitHub Container Registry
✅ Extract metadata
✅ Build and push Docker image
   - Building apps/crawler/Dockerfile
   - Pushing to ghcr.io/你的用户名/crawler:latest
   - Pushing to ghcr.io/你的用户名/crawler:sha-abc123
```

### 3.3 验证镜像已推送

```bash
# 在本地拉取新镜像
docker pull ghcr.io/你的GitHub用户名/crawler:latest

# 查看镜像信息
docker inspect ghcr.io/你的GitHub用户名/crawler:latest | jq '.[0].Created'
```

---

## 阶段 4: Watchtower 自动更新测试

### 4.1 观察 Watchtower 日志

```bash
# X 平台 watchtower（每 5 分钟检查）
docker logs -f watchtower-x

# 小红书 watchtower（每 30 分钟检查）
docker logs -f watchtower-xhs
```

**预期日志（X 平台 5 分钟后）:**
```
time="2026-02-07T12:00:00Z" level=info msg="Checking for updates"
time="2026-02-07T12:00:01Z" level=info msg="Found new image for crawler-x-ai"
time="2026-02-07T12:00:01Z" level=info msg="Stopping container crawler-x-ai (60s timeout)"
time="2026-02-07T12:00:05Z" level=info msg="Container stopped gracefully"
time="2026-02-07T12:00:06Z" level=info msg="Starting container crawler-x-ai"
time="2026-02-07T12:00:07Z" level=info msg="Update complete for crawler-x-ai"
```

### 4.2 验证容器已更新

```bash
# 查看容器启动时间（应该是最近更新的）
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" | grep crawler-x

# 验证进度已恢复
cat data/x/ai/progress_x.json | jq .
```

**预期输出:**
```
NAMES           STATUS              IMAGE
crawler-x-ai    Up 2 minutes        ghcr.io/.../crawler:latest
crawler-x-python Up About an hour   ghcr.io/.../crawler:latest  # 还未更新
crawler-x-web3   Up About an hour   ghcr.io/.../crawler:latest  # 还未更新
```

### 4.3 手动触发更新测试

如果不想等 5 分钟，可以手动触发:

```bash
# 方法 1: 重启 watchtower（立即检查）
docker restart watchtower-x

# 方法 2: 手动拉取并重启
docker pull ghcr.io/你的GitHub用户名/crawler:latest
docker restart crawler-x-ai
```

---

## 阶段 5: 增加功能并测试完整流程

### 5.1 修改代码（例如：增加新的统计信息）

编辑 `apps/crawler/__main__.py`，在统计信息中添加新字段:

```python
logger.info(f"📊 [{platform}] 统计:")
logger.info(f"   - 总互动: {total_likes:,} 点赞, {total_comments:,} 评论")
logger.info(f"   - 媒体类型: {media_types_count}")
logger.info(f"   - 平均点赞: {total_likes//len(items_scraped) if items_scraped else 0}")  # 新增
```

### 5.2 提交更新

```bash
git add apps/crawler/__main__.py
git commit -m "feat: add average likes to crawler stats

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
git push origin main
```

### 5.3 完整流程验证

1. **GitHub Actions 开始构建** (0-30秒)
   - 访问 Actions 页面确认

2. **构建新镜像** (3-5分钟)
   - 等待 workflow 完成

3. **Watchtower 检测更新** (最多 5 分钟)
   - 观察 watchtower-x 日志

4. **优雅停止旧容器** (0-60秒)
   - 观察 crawler 日志，确认进度已保存

5. **启动新容器** (5-10秒)
   - 新容器加载之前的进度继续运行

6. **验证新功能** (立即)
   - 查看日志，确认新的统计信息出现

```bash
# 一键查看整个流程
watch -n 5 'docker ps --format "table {{.Names}}\t{{.Status}}" | grep crawler-x && echo "---" && docker logs --tail 5 crawler-x-ai 2>&1 | grep "统计"'
```

---

## 常见问题排查

### 问题 1: Watchtower 不更新

**检查:**
```bash
# 1. 验证 watchtower 配置
docker logs watchtower-x | grep -i "error\|warning"

# 2. 手动拉取看是否有新镜像
docker pull ghcr.io/你的GitHub用户名/crawler:latest

# 3. 检查标签过滤
docker inspect watchtower-x | jq '.[0].Config.Env' | grep WATCHTOWER
```

**解决方案:**
- 确认 GitHub Actions 成功推送镜像
- 验证镜像标签匹配（latest）
- 检查 GITHUB_USERNAME 环境变量

### 问题 2: 容器无法优雅停止

**检查:**
```bash
# 查看停止时的日志
docker stop -t 60 crawler-x-ai
docker logs crawler-x-ai --tail 50
```

**解决方案:**
- 确认信号处理器已注册
- 检查是否有阻塞操作
- 增加超时时间

### 问题 3: 进度没有恢复

**检查:**
```bash
# 验证进度文件存在
ls -lh data/x/ai/progress_x.json

# 验证卷挂载正确
docker inspect crawler-x-ai | jq '.[0].Mounts'
```

**解决方案:**
- 确认卷路径正确
- 检查文件权限
- 验证 JSON 格式正确

---

## 性能监控

### 实时监控所有容器

```bash
# CPU 和内存使用
docker stats

# 只看 crawler
docker stats $(docker ps --filter "label=platform" -q)
```

### 日志聚合查看

```bash
# 所有 X 平台实例的最新日志
for container in crawler-x-ai crawler-x-python crawler-x-web3; do
  echo "=== $container ==="
  docker logs --tail 5 $container 2>&1 | grep "爬取完成\|统计"
  echo
done
```

### 数据统计

```bash
# 统计已爬取的数据量
find data/ -name "mock_data_*.json" -exec jq -r '.total_items' {} \; | awk '{sum+=$1} END {print "总共爬取:", sum, "条"}'

# 统计每个平台
for platform in x xhs; do
  count=$(find data/$platform -name "mock_data_*.json" -exec jq -r '.total_items' {} \; | awk '{sum+=$1} END {print sum}')
  echo "$platform 平台: $count 条"
done
```

---

## 清理命令

```bash
# 停止所有
./scripts/compose-helper.sh down all

# 清理数据（谨慎！）
rm -rf data/x data/xhs logs/

# 清理镜像
docker rmi ghcr.io/你的GitHub用户名/crawler:latest
docker rmi crawler:local

# 完全重置
docker system prune -a --volumes
```

---

## 下一步

测试通过后，可以：

1. **实现真实爬虫逻辑**
   - 替换 `crawl_platform()` 中的 mock 代码
   - 集成 Playwright 进行实际抓取
   - 添加错误处理和重试逻辑

2. **添加数据库存储**
   - 将 JSON 数据保存到 PostgreSQL/SQLite
   - 实现数据去重和增量更新

3. **部署到 NAS**
   - 参考 `DEPLOYMENT.md` 部署到 QNAP NAS
   - 配置自动重启和监控

4. **添加 Web Dashboard**
   - 查看爬取进度和数据统计
   - 控制 crawler 启停

5. **配置告警通知**
   - Watchtower Discord/Slack 通知
   - 爬虫错误告警
