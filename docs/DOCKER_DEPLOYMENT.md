# Docker 部署指南

## 前置要求

- Docker 20.10+
- Docker Compose 2.0+

## 快速开始

### 1. 构建并启动服务

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f monst3r
```

### 2. 访问应用

- 前端界面: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/health

### 3. 停止服务

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

## 配置说明

### 环境变量

在 `docker-compose.yml` 中可以配置以下环境变量：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PYTHONUNBUFFERED` | `1` | Python 输出不缓冲 |
| `DATA_ROOT` | `/app/data` | 数据根目录 |
| `LOCAL_JOBS_DIR` | `/app/local_jobs` | 本地任务目录 |

### 数据持久化

默认配置将以下目录挂载到宿主机：

- `./data` -> `/app/data` (应用数据)
- `./local_jobs` -> `/app/local_jobs` (任务数据)

### 可选服务

#### Redis

用于缓存和会话管理：

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
```

#### PostgreSQL

用于持久化存储：

```yaml
postgres:
  image: postgres:15-alpine
  environment:
    - POSTGRES_DB=monst3r
    - POSTGRES_USER=monst3r
    - POSTGRES_PASSWORD=monst3r_password
```

## 生产环境部署

### 1. 使用 Nginx 反向代理

创建 `nginx.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2. 配置 HTTPS

使用 Let's Encrypt 和 Certbot:

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 3. 资源限制

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  monst3r:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

## 故障排查

### 查看容器日志

```bash
docker-compose logs monst3r
```

### 进入容器调试

```bash
docker-compose exec monst3r bash
```

### 重启服务

```bash
docker-compose restart monst3r
```

### 清理并重新构建

```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

## 性能优化

### 1. 使用多阶段构建

当前 Dockerfile 已使用多阶段构建，减小最终镜像大小。

### 2. 启用 GPU 支持

如果需要 GPU 加速，使用 nvidia-docker:

```yaml
services:
  monst3r:
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
```

### 3. 调整 Worker 数量

修改启动命令：

```yaml
command: ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```
