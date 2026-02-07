# 监控和日志管理 - Loki + Grafana

集中式日志管理解决方案，替代分散的文件日志。

## 🏗️ 架构

```
Crawler Containers → Docker Logs → Promtail → Loki → Grafana
                                                      ↓
                                                  可视化查询
```

**组件**：
- **Loki**: 日志聚合后端（类似 Elasticsearch，但更轻量）
- **Promtail**: 日志收集代理（从 Docker 容器收集日志）
- **Grafana**: 可视化前端（查询和展示日志）

---

## 🚀 快速开始

### 1. 启动监控栈

```bash
# 启动 X 平台 + 监控
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.x.yml \
  -f docker-compose.monitoring.yml \
  up -d

# 或使用 helper 脚本（需要先更新）
./scripts/compose-helper.sh up x monitoring
```

### 2. 访问 Grafana

打开浏览器：`http://localhost:3000`

**默认登录**：
- 用户名: `admin`
- 密码: `admin`

首次登录后会提示修改密码（可选）。

### 3. 查看日志

**方式 1: 使用预配置的 Dashboard**
1. 左侧菜单 → Dashboards
2. 选择 "Crawler Logs"
3. 实时查看所有 crawler 日志

**方式 2: 使用 Explore**
1. 左侧菜单 → Explore
2. 数据源选择 "Loki"
3. 使用 LogQL 查询

---

## 📊 常用查询（LogQL）

### 基础查询

```logql
# 查看所有 crawler 日志
{container=~"crawler-.*"}

# 查看特定平台
{platform="x"}
{platform="xhs"}

# 查看特定容器
{container="crawler-x-ai"}
```

### 日志级别过滤

```logql
# 只看错误日志
{container=~"crawler-.*"} |= "ERROR"

# 只看警告和错误
{container=~"crawler-.*"} |~ "WARNING|ERROR"

# 排除 INFO 级别
{container=~"crawler-.*"} != "INFO"
```

### 内容搜索

```logql
# 查找爬取完成的日志
{container=~"crawler-.*"} |= "爬取完成"

# 查找统计信息
{container=~"crawler-.*"} |= "统计"

# 查找新功能（平均互动）
{container=~"crawler-.*"} |= "平均互动"
```

### 时间范围

```logql
# 最近 5 分钟的错误
{container=~"crawler-.*"} |= "ERROR" [5m]

# 最近 1 小时的日志
{container=~"crawler-.*"} [1h]
```

### 聚合统计

```logql
# 统计每分钟的日志条数
count_over_time({container=~"crawler-.*"} [1m])

# 按日志级别统计
sum by (level) (count_over_time({container=~"crawler-.*"} [5m]))

# 按平台统计
sum by (platform) (count_over_time({container=~"crawler-.*"} [5m]))
```

---

## 🔍 实用场景

### 场景 1: 排查错误

**目标**: 找出最近的所有错误

```logql
{container=~"crawler-.*"} |= "ERROR" or |= "致命错误"
```

在 Grafana 中：
1. Explore → 输入上述查询
2. 时间范围选择 "Last 1 hour"
3. 点击日志查看详情

### 场景 2: 监控爬取进度

**目标**: 实时查看爬取完成的统计

```logql
{container=~"crawler-.*"} |= "爬取完成" or |= "统计"
```

### 场景 3: 验证新功能部署

**目标**: 确认"平均互动"功能已上线

```logql
{container=~"crawler-.*"} |= "平均互动"
```

如果看到日志，说明新版本已部署成功！

### 场景 4: 对比不同平台

**目标**: 同时查看 X 和小红书的日志

```logql
# X 平台
{platform="x"}

# 小红书平台
{platform="xhs"}
```

在 Grafana 中添加多个 Query 并行查看。

---

## 📈 Dashboard 说明

### Crawler Logs Dashboard

**面板**：

1. **Log Stream by Platform**
   - 所有 crawler 的实时日志流
   - 按时间倒序排列
   - 可点击展开查看详情

2. **Error Logs**
   - 只显示错误日志
   - 方便快速排查问题

3. **Scraping Progress**
   - 爬取完成和统计信息
   - 监控爬取进度

4. **Log Level Distribution**
   - 日志级别分布统计
   - 了解系统运行状态

5. **Active Crawlers**
   - 当前活跃的 crawler 数量
   - 确认服务运行正常

6. **X Platform Logs**
   - X 平台专属日志

7. **XHS Platform Logs**
   - 小红书平台专属日志

---

## ⚙️ 配置说明

### 日志保留时间

默认保留 **7 天**，修改 `monitoring/loki-config.yaml`:

```yaml
limits_config:
  retention_period: 168h  # 7 天 = 168 小时
```

可选值：
- `24h` - 1 天
- `72h` - 3 天
- `168h` - 7 天（默认）
- `720h` - 30 天

### 存储位置

日志数据存储在 Docker volumes:

```bash
# 查看数据卷
docker volume ls | grep loki
docker volume ls | grep grafana

# 清理所有数据（危险！）
docker volume rm crosshot-ai_loki-data
docker volume rm crosshot-ai_grafana-data
```

### 性能调优

如果日志量很大，可以调整 `monitoring/loki-config.yaml`:

```yaml
limits_config:
  ingestion_rate_mb: 16      # 增加到 32
  ingestion_burst_size_mb: 32  # 增加到 64
  max_query_series: 1000     # 增加到 5000
```

---

## 🔧 故障排查

### 问题 1: Grafana 无法连接

**检查**:
```bash
# 查看容器状态
docker ps | grep -E "loki|grafana|promtail"

# 查看日志
docker logs grafana
docker logs loki
```

**解决**: 确保所有容器在同一网络（crosshot-ai）

### 问题 2: 看不到日志

**检查 Promtail**:
```bash
docker logs promtail

# 应该看到类似输出：
# level=info msg="Successfully scraped container"
```

**解决**:
1. 确认 crawler 容器正在运行
2. 确认 crawler 有输出日志
3. 重启 Promtail: `docker restart promtail`

### 问题 3: 查询很慢

**原因**: 时间范围太大或日志量太多

**解决**:
1. 缩小时间范围（如只查询最近 1 小时）
2. 添加更多过滤条件
3. 使用更具体的标签（container、platform）

---

## 📱 移动端访问

Grafana 支持移动浏览器访问：

```
http://NAS_IP:3000
```

建议在 NAS 上配置反向代理（Nginx）:
- 添加 HTTPS
- 配置域名
- 设置访问控制

---

## 🔄 与 Portainer 集成

监控栈可以通过 Portainer 管理：

1. **Stack 管理**：
   - Portainer → Stacks → Add stack
   - 粘贴 `docker-compose.monitoring.yml` 内容

2. **Webhook 更新**：
   - 创建 stack webhook
   - 更新 `.github/workflows/deploy-to-nas.yml`
   - 添加监控栈的 webhook URL

---

## 📊 扩展建议

### 添加 Prometheus 指标

如果需要更详细的性能指标（CPU、内存、网络）：

```yaml
# 添加到 docker-compose.monitoring.yml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

node-exporter:
  image: prom/node-exporter:latest
  ports:
    - "9100:9100"
```

### 添加告警

配置 Loki Ruler 发送告警：

```yaml
# monitoring/loki-config.yaml
ruler:
  storage:
    type: local
    local:
      directory: /loki/rules
  rule_path: /tmp/rules
  alertmanager_url: http://alertmanager:9093
```

---

## 🎯 总结

**优势**：
- ✅ 集中式日志管理
- ✅ 实时查询和可视化
- ✅ 强大的 LogQL 查询语言
- ✅ 轻量级（相比 ELK）
- ✅ 与 Docker 原生集成

**适用场景**：
- 多个 crawler 实例的日志统一管理
- 快速排查错误和问题
- 监控爬取进度和统计
- 验证新功能部署

**下一步**：
- 创建自定义 Dashboard
- 配置告警规则
- 集成 Prometheus 指标
- 添加日志归档（长期存储）
