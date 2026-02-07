# Crosshot AI - 多平台爬虫系统

智能化、分布式、可扩展的社交媒体数据采集系统。

## 🏗️ 架构设计

```
├── apps/
│   ├── crawler/           # 通用爬虫（支持多平台）
│   └── example-app/       # 应用模板
│
├── docker-compose.yml     # 基础配置
├── docker-compose.x.yml   # X (Twitter) 平台
├── docker-compose.xhs.yml # 小红书平台
└── docker-compose.watchtower.yml  # 全局自动更新
```

**一个镜像，多个实例，通过环境变量配置平台和任务。**

---

## 🚀 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，设置 GITHUB_USERNAME
```

### 2. 启动爬虫

#### 方式 A: 使用帮助脚本（推荐）

```bash
# 启动 X 平台
./scripts/compose-helper.sh up x

# 启动小红书平台
./scripts/compose-helper.sh up xhs

# 启动所有平台
./scripts/compose-helper.sh up all

# 查看 X 平台日志
./scripts/compose-helper.sh logs x

# 停止小红书平台
./scripts/compose-helper.sh down xhs
```

#### 方式 B: 直接使用 docker-compose

```bash
# 启动 X 平台
docker-compose -f docker-compose.yml -f docker-compose.x.yml up -d

# 启动小红书平台
docker-compose -f docker-compose.yml -f docker-compose.xhs.yml up -d

# 启动所有平台
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.x.yml \
  -f docker-compose.xhs.yml \
  up -d

# 查看日志
docker-compose -f docker-compose.yml -f docker-compose.x.yml logs -f

# 停止
docker-compose -f docker-compose.yml -f docker-compose.x.yml down
```

---

## 📁 文件说明

### docker-compose.yml
基础配置，定义网络和共享资源。

### docker-compose.x.yml
X (Twitter) 平台的所有爬虫实例：
- `crawler-x-ai` - AI 相关话题
- `crawler-x-python` - Python 开发
- `crawler-x-web3` - Web3 区块链
- `watchtower-x` - X 平台专属自动更新（每 5 分钟）

### docker-compose.xhs.yml
小红书平台的所有爬虫实例：
- `crawler-xhs-beauty` - 美妆护肤
- `crawler-xhs-travel` - 旅行攻略
- `crawler-xhs-fashion` - 穿搭时尚
- `crawler-xhs-food` - 美食探店
- `watchtower-xhs` - 小红书专属自动更新（每 30 分钟）

### docker-compose.watchtower.yml
全局 Watchtower 配置（可选），如果不想每个平台独立配置。

---

## ⚙️ 配置说明

每个 crawler 通过环境变量配置：

```yaml
environment:
  - PLATFORM=x              # 平台: x, xhs, douyin
  - KEYWORDS=AI,Python      # 爬取关键词（逗号分隔）
  - MAX_RESULTS=100         # 每次爬取数量
  - INTERVAL=3600           # 爬取间隔（秒）
  - LOG_LEVEL=INFO          # 日志级别
```

---

## 📊 数据存储

```
data/
├── x/
│   ├── ai/         # X 平台 AI 话题数据
│   ├── python/     # X 平台 Python 数据
│   └── web3/       # X 平台 Web3 数据
└── xhs/
    ├── beauty/     # 小红书美妆数据
    ├── travel/     # 小红书旅行数据
    ├── fashion/    # 小红书穿搭数据
    └── food/       # 小红书美食数据

logs/
├── x/
│   ├── ai/
│   ├── python/
│   └── web3/
└── xhs/
    ├── beauty/
    ├── travel/
    ├── fashion/
    └── food/
```

---

## 🔄 自动更新策略

### 方案 1: 平台专属 Watchtower（当前配置）

- **X 平台**: 每 5 分钟检查更新（更新频繁）
- **小红书**: 每 30 分钟检查更新（更新较慢）

### 方案 2: 全局 Watchtower

使用 `docker-compose.watchtower.yml`，统一管理所有平台更新。

---

## 📝 添加新 Crawler

### 在现有平台添加

编辑 `docker-compose.x.yml` 或 `docker-compose.xhs.yml`：

```yaml
crawler-x-新主题:
  <<: *x-crawler-base  # 复用基础配置
  container_name: crawler-x-新主题
  volumes:
    - ./data/x/新主题:/app/data
    - ./logs/x/新主题:/app/logs
  environment:
    - PLATFORM=x
    - KEYWORDS=关键词1,关键词2
    - MAX_RESULTS=100
    - INTERVAL=3600
```

### 添加新平台

1. 复制 `docker-compose.x.yml` 为 `docker-compose.新平台.yml`
2. 修改所有 `x` 为新平台标识
3. 调整 crawler 配置和关键词
4. 启动: `./scripts/compose-helper.sh up 新平台`

---

## 🛠️ 常用命令

```bash
# 查看所有运行的容器
docker ps

# 查看特定 crawler 日志
docker logs -f crawler-x-ai

# 重启特定 crawler
docker restart crawler-xhs-beauty

# 查看资源使用
docker stats

# 进入容器调试
docker exec -it crawler-x-ai sh
```

---

## 🔍 监控和调试

### 查看进度文件

```bash
# X 平台 AI 话题进度
cat data/x/ai/progress_x.json

# 小红书美妆进度
cat data/xhs/beauty/progress_xhs.json
```

### 查看实时日志

```bash
# 使用帮助脚本
./scripts/compose-helper.sh logs x

# 或直接查看
tail -f logs/x/ai/*.log
```

---

## 📚 部署到 NAS

详见 [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 🧪 开发

### 本地测试

```bash
cd apps/crawler
uv sync
uv run python -m crawler

# 设置环境变量测试
PLATFORM=x KEYWORDS=test uv run python -m crawler
```

### 构建镜像

```bash
docker build -f apps/crawler/Dockerfile -t crawler:test .
```

---

## 📖 更多文档

- [部署指南](DEPLOYMENT.md) - QNAP NAS 部署步骤
- [架构设计](docs/ARCHITECTURE.md) - 系统架构说明
- [API 文档](docs/API.md) - 接口文档

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 License

MIT License
