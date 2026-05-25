# Model Blueprint Schema

每个模型的 YAML 蓝图是 Agent 框架的基础"标签"。Agent 读取蓝图后执行自动化搭建、验证、运行和评估。

## Schema Definition

```yaml
# ─────────────── 身份标签 ───────────────
name: str               # 模型名称 (e.g. "MonST3R")
key: str                # 平台内部 key (e.g. "monst3r")
family: str             # 模型族 (dust3r / independent)
version: str            # 代码版本/commit
paper:
  title: str            # 论文标题
  url: str              # arxiv 链接
  venue: str            # 发表会议/期刊
  year: int

# ─────────────── 能力标签 ───────────────
tags:
  type: str             # static_multiview | dynamic_video | spatial_memory | fast_multiview | online_persistent | video_depth
  input: list[str]      # [images, video, image_pairs]
  output: list[str]     # [pointcloud, mesh, depth, trajectory, camera_poses, masks]
  paradigm: str         # pairwise | global_memory | feedforward | streaming
  scene: str            # static | dynamic | both

# ─────────────── 源码配置 ───────────────
repo:
  url: str              # Git 仓库 URL
  branch: str
  commit: str           # 固定 commit hash (可选)
  submodules: list[str] # 需要的 submodules
  server_path: str      # 服务器上的绝对路径

# ─────────────── 环境配置 ───────────────
environment:
  conda_env: str        # conda 环境名
  python: str           # Python 版本
  torch: str            # PyTorch 版本+CUDA后缀
  cuda_toolkit: str     # 系统 CUDA 路径 (e.g. /usr/local/cuda-12.6)
  cuda_arch: str        # GPU compute capability (e.g. "7.5" for TITAN RTX)

  # conda 创建策略
  create_strategy: str  # "fresh" | "clone_from"
  clone_source: str     # 如果 clone_from，指定源 env 名

  # pip 依赖
  pip_requirements: str # requirements.txt 相对路径 (相对 repo root)
  extra_pip: list[str]  # 额外 pip 包 (repo requirements 之外)
  exclude_pip: list[str]# 从 requirements 中排除的包

  # 系统依赖
  system_deps: list[str] # 系统包 (apt/yum)

# ─────────────── 权重/检查点 ───────────────
checkpoints:
  - name: str           # 文件名
    path: str           # 相对 repo 的存放路径
    source: str         # "huggingface" | "url" | "manual"
    url: str            # 下载链接 (如适用)
    size_gb: float
    hash: str           # SHA256 (可选)
    required: bool      # true = 缺失则无法运行

# ─────────────── 编译步骤 ───────────────
build_steps:
  - name: str           # 步骤名 (e.g. "compile curope")
    cmd: str            # 执行命令
    cwd: str            # 工作目录 (相对 repo root)
    env:                # 环境变量
      TORCH_CUDA_ARCH_LIST: str
      CUDA_HOME: str
    verify: str         # 验证命令 (验证编译产物存在)
    notes: str          # 备注/经验

# ─────────────── 资源需求 ───────────────
resources:
  gpu_memory_gb: float  # 预估 GPU 显存需求
  ram_gb: float         # 预估内存需求
  disk_gb: float        # 安装后磁盘占用
  max_frames: int       # 最大支持帧数 (视频模型)
  batch_size_limit: int # 最大 batch size (当前 GPU)

# ─────────────── 健康检查 ───────────────
health_checks:
  - name: str           # 检查名
    type: str           # "import" | "cuda_kernel" | "file_exists" | "command"
    command: str        # 执行命令
    expected: str       # 期望输出
    critical: bool      # 是否为阻塞检查

smoke_test:
  script: str           # 完整 smoke test 命令
  timeout_sec: int      # 超时时间
  expected: str         # 期望输出包含的字符串
  output_files: list    # 期望生成的输出文件

# ─────────────── Runner 配置 ───────────────
runner:
  script: str           # runner 脚本路径
  conda_env: str        # 运行时 env (通常和 environment.conda_env 相同)
  entry_pattern: str    # 进程匹配模式 (取消时 kill 用)
  default_params:       # 默认参数 (key: value)
    image_size: int
    # ...
  param_tiers:          # 参数预设梯度
    fast:   { ... }
    standard: { ... }
    enhanced: { ... }

# ─────────────── 输出合同 ───────────────
output_contract:
  required:             # 必须输出的文件
    - key: str          # 语义 key
      pattern: str      # 文件名或 glob
      type: str         # "ply" | "glb" | "json" | "png" | "txt" | "npy"
      description: str
  optional:             # 可选输出
    - key: str
      pattern: str
      type: str
  scene_meta:           # scene_meta.json 中的期望字段
    - field: str
      type: str

# ─────────────── 已知问题 ───────────────
known_issues:
  - id: str             # 问题编号
    description: str
    workaround: str
    resolved: bool
    resolved_date: str

# ─────────────── 兼容矩阵 ───────────────
compatibility:
  gpu_models: list[str] # 已测试 GPU (e.g. ["TITAN RTX", "RTX 3090"])
  os: list[str]         # 已测试 OS
  glibc_min: str        # 最低 GLIBC 版本
  driver_min: str       # 最低 NVIDIA 驱动版本

# ─────────────── 状态 ───────────────
status: str             # "integrated" | "env_ready" | "planned" | "deferred"
priority: str           # "baseline" | "high" | "medium" | "low"
last_verified: str      # ISO date of last successful verification
```

## Agent 使用蓝图的流程

```
1. 读取蓝图 YAML
2. 按 environment 配置创建/验证 conda env
3. 按 checkpoints 验证权重文件是否存在
4. 按 build_steps 编译必要扩展
5. 按 health_checks 逐项验证
6. 按 smoke_test 执行端到端验证
7. 标记 status → integrated/env_ready
8. 按 runner + output_contract 注册到平台
```
