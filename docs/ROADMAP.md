# 3R All-in-One 发展路线图

> 基于 v0.4.1 代码库分析，最后更新: 2026-05-26

---

## 📊 当前状态分析

### 代码量统计

| 模块 | 文件数 | 主要大文件 |
|------|--------|-----------|
| Backend | 14 个 .py | `app.py` (91KB), `ssh_runner.py` (45KB) |
| Frontend | 20 个 .tsx/.ts | `App.tsx` (45KB), `styles.css` (82KB) |
| Agent | 8 个 .py | `env_builder.py` (17KB), `cli.py` (12KB) |
| Runners | 7 个 .py | 每个 6-18KB |
| Model Specs | 7 个 .yaml | 每个 4-7KB |

### 技术债务清单

| 问题 | 严重程度 | 位置 |
|------|----------|------|
| **零测试覆盖** | 🔴 高 | 全项目 |
| App.tsx 单体组件 (1055行) | 🟠 中 | client/src/App.tsx |
| app.py 单体路由 (2000+行) | 🟠 中 | backend/app.py |
| 无状态管理 (props drilling) | 🟡 低 | 前端组件间 |
| CSS 82KB 无模块化 | 🟡 低 | styles.css |
| Runner 脚本重复逻辑 | 🟡 低 | runners/*.py |

---

## 🎯 Phase 1: 短期目标 (v0.5 - v0.6)

### 1.1 测试基础设施 ⭐ 最高优先级

```
tests/
├── conftest.py              # pytest fixtures
├── backend/
│   ├── test_job_store.py    # 任务存储测试
│   ├── test_model_contracts.py
│   ├── test_ssh_runner.py   # mock SSH 连接
│   └── test_api_endpoints.py # FastAPI TestClient
├── agent/
│   ├── test_registry.py     # 模型注册表
│   ├── test_schema_validator.py
│   └── test_env_builder.py
└── integration/
    └── test_job_lifecycle.py # 端到端任务流程
```

**具体任务：**

1. 安装测试依赖：
   ```toml
   # pyproject.toml [project.optional-dependencies]
   test = ["pytest>=8.0", "pytest-asyncio", "pytest-cov", "httpx", "respx"]
   ```

2. 创建 `conftest.py` 共享 fixtures：
   - `tmp_job_dir` - 临时任务目录
   - `mock_ssh_client` - paramiko mock
   - `test_client` - FastAPI TestClient
   - `sample_model_spec` - 测试用 YAML

3. 优先覆盖核心路径：
   - `job_store.py` - create/update/query
   - `model_registry.py` - load/query
   - `/api/jobs/*` 端点
   - `agent/registry.py` - 模型查询

4. 目标覆盖率：**核心模块 80%+**

### 1.2 模型执行完善

当前 7 个模型蓝图已定义，但执行链路需要：

```python
# backend/pipeline_executor.py (新建)
class PipelineExecutor:
    """统一的模型执行管道"""
    
    async def execute(self, job: JobRecord, spec: ModelSpec):
        # 1. 环境检查
        await self.check_environment(spec)
        
        # 2. 数据预处理
        await self.preprocess_inputs(job, spec)
        
        # 3. 执行推理/训练
        result = await self.run_model(job, spec)
        
        # 4. 后处理
        await self.postprocess_outputs(job, result)
        
        # 5. 指标计算
        await self.compute_metrics(job, result)
```

**任务清单：**
- [ ] 统一 runner 接口 (`BaseRunner` 抽象类)
- [ ] 实现断点续训 (checkpoint 检测)
- [ ] 添加资源配额检查 (GPU 内存/磁盘空间)
- [ ] 任务队列优先级

### 1.3 结果可视化

```
client/src/components/
├── viewers/
│   ├── PointCloudViewer.tsx    # Three.js / Potree
│   ├── MeshViewer.tsx          # GLB/OBJ 查看
│   ├── DepthMapViewer.tsx      # 深度图热力图
│   └── TrajectoryViewer.tsx    # 相机轨迹可视化
└── comparison/
    ├── SideBySideView.tsx      # 双模型对比
    └── MetricsChart.tsx        # 指标图表 (Recharts)
```

**技术选型：**
- 点云: `@react-three/fiber` + `@react-three/drei`
- 图表: `recharts` 或 `visx`
- 3D 模型: `@google/model-viewer` (简单) 或 Three.js (完整控制)

### 1.4 用户体验增强

- [ ] 主题切换 (dark/light) - CSS 变量
- [ ] 任务执行实时日志流 (WebSocket 已有基础)
- [ ] 错误诊断面板 + 一键导出日志
- [ ] 快捷键支持 (Ctrl+Enter 提交, Esc 关闭)

---

## 🚀 Phase 2: 中期目标 (v0.7 - v1.0)

### 2.1 Agent 智能化

基于现有 `agent/` 模块扩展：

```python
# agent/auto_tuner.py
class AutoTuner:
    """自动参数调优"""
    
    def suggest_params(self, 
                       model_key: str, 
                       input_stats: InputStats,
                       hardware: HardwareProfile) -> dict:
        """
        根据输入数据特征和硬件配置推荐参数
        - 图片数量 → batch_size
        - 分辨率 → rescale
        - GPU 内存 → precision (fp16/fp32)
        """
        pass
    
    def optimize(self, 
                 job_history: list[JobRecord],
                 target_metric: str = "psnr") -> dict:
        """贝叶斯优化历史任务参数"""
        pass
```

```python
# agent/anomaly_detector.py
class TrainingMonitor:
    """训练异常检测"""
    
    def check_loss_curve(self, losses: list[float]) -> list[Warning]:
        """
        检测:
        - Loss 爆炸 (NaN / Inf)
        - Loss 停滞 (方差过小)
        - Loss 震荡 (方差过大)
        """
        pass
```

### 2.2 集群调度

```
backend/cluster/
├── scheduler.py        # 任务调度器
├── node_manager.py     # 节点管理
├── load_balancer.py    # 负载均衡
└── protocols.py        # 通信协议

# 技术选型:
# - 轻量级: 自建 SSH 调度 (当前 ssh_runner 扩展)
# - 中等规模: Celery + Redis
# - 大规模: Ray Cluster
```

### 2.3 模型市场

```yaml
# 模型蓝图包格式 (.3rmodel)
meta:
  name: gaussian-splatting-v2
  version: 1.0.0
  author: community
  description: Improved 3DGS implementation

spec: # 内嵌 model_spec YAML
  ...

files:
  - runner.py
  - requirements.txt
```

**功能：**
- 在线蓝图仓库 (GitHub Releases / 自建)
- 一键安装/更新/卸载
- 版本兼容性检查

### 2.4 导出格式扩展

```python
# backend/exporters/
class FormatConverter:
    """3D 格式转换"""
    
    supported_formats = {
        "input": ["ply", "obj", "glb", "gltf", "fbx"],
        "output": ["ply", "obj", "glb", "gltf", "usdz", "splat"]
    }
    
    def convert(self, input_path: Path, output_format: str) -> Path:
        # 使用 trimesh / open3d / assimp
        pass
```

---

## 🏢 Phase 3: 长期目标 (v1.x+)

### 3.1 企业级特性

```
backend/enterprise/
├── auth/
│   ├── users.py        # 用户管理
│   ├── roles.py        # 角色定义
│   └── permissions.py  # 权限控制
├── audit/
│   ├── logger.py       # 操作日志
│   └── compliance.py   # 合规报告
└── tenant/
    └── isolation.py    # 多租户隔离
```

### 3.2 部署方案

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...
    volumes:
      - ./data:/app/data
  
  worker:
    build: ./backend
    command: celery -A worker worker
    deploy:
      replicas: 3
  
  frontend:
    build: ./client
    ports:
      - "80:80"
```

```yaml
# helm/values.yaml (Kubernetes)
backend:
  replicas: 2
  resources:
    limits:
      nvidia.com/gpu: 1
worker:
  replicas: 4
  gpu: true
```

### 3.3 SDK 与 API

```python
# 3r-sdk (PyPI 包)
from r3_sdk import Client

client = Client("http://localhost:8765")

# 创建任务
job = client.jobs.create(
    model="monst3r",
    source_type="video",
    files=["scene.mp4"],
    params={"scenegraph_type": "swinstride-5-noncyclic"}
)

# 等待完成
result = job.wait()

# 下载结果
result.download("./output/", artifacts=["mesh.glb", "depth_video.mp4"])
```

---

## 🔧 技术债务清理计划

### 高优先级 (随 Phase 1 进行)

#### 1. 添加测试
```bash
# 目标结构
pytest tests/ --cov=backend --cov=agent --cov-report=html
# 覆盖率目标: 核心模块 80%+
```

#### 2. 拆分 App.tsx

```
client/src/
├── App.tsx              # 仅路由和布局 (<200行)
├── pages/
│   ├── JobsPage.tsx     # 任务列表
│   ├── CreateJobPage.tsx
│   ├── JobDetailPage.tsx
│   └── SettingsPage.tsx
├── components/
│   ├── layout/
│   ├── forms/
│   └── viewers/
├── hooks/
│   ├── useJobs.ts
│   ├── useBackendStatus.ts
│   └── useWebSocket.ts
└── stores/              # Zustand 状态管理
    ├── jobStore.ts
    └── uiStore.ts
```

#### 3. 拆分 app.py

```
backend/
├── app.py               # 仅 FastAPI app 初始化 (<100行)
├── routers/
│   ├── jobs.py          # /api/jobs/*
│   ├── models.py        # /api/models/*
│   ├── samples.py       # /api/samples/*
│   ├── deployment.py    # /api/deployment/*
│   └── websocket.py     # WebSocket 处理
├── services/
│   ├── job_service.py
│   ├── model_service.py
│   └── execution_service.py
└── core/
    ├── config.py
    ├── exceptions.py
    └── dependencies.py
```

### 中优先级 (Phase 2)

#### 4. 统一 Runner 接口

```python
# runners/base.py
from abc import ABC, abstractmethod

class BaseRunner(ABC):
    """所有 runner 的基类"""
    
    @abstractmethod
    def validate_inputs(self, inputs: list[Path]) -> bool:
        """验证输入文件"""
        pass
    
    @abstractmethod
    def build_command(self, params: dict) -> list[str]:
        """构建执行命令"""
        pass
    
    @abstractmethod
    def parse_output(self, stdout: str, stderr: str) -> dict:
        """解析输出"""
        pass
    
    def run(self, job_dir: Path, params: dict) -> RunResult:
        """模板方法"""
        self.validate_inputs(...)
        cmd = self.build_command(params)
        result = self.execute(cmd)
        return self.parse_output(result)
```

#### 5. CSS 模块化

```
# 方案 A: CSS Modules
styles/
├── global.module.css
├── components/
│   ├── Button.module.css
│   └── Card.module.css

# 方案 B: Tailwind CSS
# 配合 @apply 提取组件类

# 方案 C: CSS-in-JS (styled-components / emotion)
# 最大灵活性，但增加包体积
```

### 低优先级 (Phase 3)

#### 6. 类型增强

```bash
# 后端
pip install mypy types-PyYAML types-paramiko
mypy backend/ --strict

# 前端 (已有 TypeScript)
# 检查 any 使用, 添加更严格的 tsconfig
```

---

## 📅 里程碑时间表 (建议)

| 版本 | 目标 | 预估周期 |
|------|------|----------|
| v0.5 | 测试覆盖 50%+ / App.tsx 拆分 | 2-3 周 |
| v0.6 | 3D 查看器 / 主题切换 | 2 周 |
| v0.7 | Runner 统一接口 / 断点续训 | 3 周 |
| v0.8 | Agent 参数推荐 / 异常检测 | 3 周 |
| v0.9 | 多节点调度基础 | 4 周 |
| v1.0 | 稳定发布 / 文档完善 | 2 周 |

---

## 📚 参考资源

- [FastAPI 最佳实践](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [React 项目结构](https://react.dev/learn/thinking-in-react)
- [Tauri Sidecar 文档](https://tauri.app/v2/guides/features/sidecar/)
- [Three.js React 集成](https://docs.pmnd.rs/react-three-fiber)
- [Pytest 最佳实践](https://docs.pytest.org/en/stable/how-to/fixtures.html)
