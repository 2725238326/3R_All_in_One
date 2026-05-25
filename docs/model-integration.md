# Model Integration Guide

## Adding a New Model

To integrate a new 3R model into the platform, follow these steps:

### 1. Create Model Spec

Create `agent/model_specs/<model_name>.yaml`:

```yaml
name: NewModel
family: dust3r
type: static_multiview
repo:
  url: https://github.com/org/newmodel
  server_path: /hdd3/kykt26/code/newmodel
environment:
  conda_env: newmodel
  python: "3.11"
  torch: "2.5.1+cu121"
checkpoints:
  - name: model.pth
    path: checkpoints/
    size_gb: 1.5
build_steps: []
smoke_test:
  script: "python -c \"import newmodel; print('OK')\""
  expected: "OK"
runner:
  script: runners/newmodel_runner.py
  conda_env: newmodel
  default_params:
    image_size: 512
output_contract:
  required: [pointcloud.ply, scene_meta.json]
status: planned
```

### 2. Write Runner Script

Create `runners/newmodel_runner.py`. The runner must:

- Read `job.json` from the job directory
- Execute the model with the specified parameters
- Write outputs to the `output/` directory
- Write `scene_meta.json` with model metadata
- Write status updates to `status.json`
- Exit with code 0 on success

### 3. Register in Backend

Add the model to `backend/model_registry.py`:

```python
ModelSpec(
    key="newmodel",
    label="NewModel",
    family="dust3r",
    runner_status="planned",
    ...
)
```

### 4. Add Output Contract

Add to `backend/model_contracts.py`:

```python
"newmodel": ModelContract(
    model="newmodel",
    outputs=[
        OutputSpec(key="pointcloud", ...),
        OutputSpec(key="scene_meta", ...),
    ]
)
```

### 5. Setup Remote Environment

Use the agent to automatically set up the environment:

```python
from agent.env_builder import SSHConfig, build_environment, ModelSpec

ssh = SSHConfig(host="172.17.140.97", user="kykt26", alias="KYKT-UI")
spec = ModelSpec.from_yaml("agent/model_specs/newmodel.yaml")
report = build_environment(ssh, spec)
```

### 6. Verify with Smoke Test

```python
from agent.smoke_runner import smoke_check_model
report = smoke_check_model(ssh, spec)
print(f"Ready: {report.ready}")
```

## Current Model Status

| Model | Env | Checkpoints | Smoke | Runner | Platform E2E |
|-------|-----|-------------|-------|--------|-------------|
| DUSt3R | ✅ | ✅ | ✅ | ✅ | ✅ |
| MASt3R | ✅ | ✅ | ✅ | ✅ | ✅ |
| MonST3R | ✅ | ✅ | ✅ | ✅ | ✅ |
| Spann3R | ✅ | ✅ | ✅ | ✅ | ✅ |
| Fast3R | ✅ | ✅ | ✅ | ✅ | ✅ |
| Align3R | ✅ | ✅ | ✅ | ❌ | ❌ |
| CUT3R | ✅ | ✅ | ✅ | ❌ | ❌ |

## Server Layout

```
/hdd3/kykt26/
├── code/
│   ├── dust3r-main/
│   ├── mast3r/
│   ├── monst3r/
│   ├── spann3r/
│   ├── fast3r/
│   ├── align3r/
│   └── cut3r/
├── models/
│   ├── DUSt3R_ViTLarge_BaseDecoder_512_dpt.pth
│   ├── MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth
│   └── fast3r/
├── jobs/
│   └── <job_id>/
└── runners/
```
