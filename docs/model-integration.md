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

Use `agent/model_specs/SCHEMA.md` as the authoritative schema. The YAML file is the agent-side contract; the backend registry and runner script are the platform-side contract.

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

| Model | Backend status | Runner script | Closing note |
|-------|----------------|---------------|--------------|
| DUSt3R | `baseline` | `runners/dust3r_runner.py` | Baseline static reconstruction path |
| MASt3R | `validated_smoke` | `runners/mast3r_runner.py` | Static matching/reconstruction path |
| MonST3R | `validated_standard_sample` | `runners/monst3r_runner.py` | Main dynamic video sample path |
| Spann3R | `validated_smoke` | `runners/spann3r_runner.py` | Spatial-memory reconstruction path |
| Fast3R | `validated_smoke_attention_fallback` | `runners/fast3r_runner.py` | Large image collection path with attention fallback |
| Align3R | `runner_ready` | `runners/align3r_runner.py` | Runner ready; full dataset validation remains follow-up work |
| CUT3R | `validated_smoke` | `runners/cut3r_runner.py` | Streaming/persistent-state path smoke verified |

`backend/model_registry.py` is the source of truth for platform-visible model status. The table above summarizes the current closing state and should be updated when `runner_status` changes.

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

## Closing Scope

For the closing delivery, a model is considered sufficiently integrated when:

- it has an agent YAML blueprint,
- it appears in `backend/model_registry.py`,
- it has a runner script under `runners/`,
- it can create or consume `job.json`, `status.json`, and `scene_meta.json`,
- at least smoke-level validation or a documented blocker exists.

Full paper-level benchmark reproduction is not part of the platform integration contract. It belongs to experiment design and depends on dataset, ground truth, and server environment stability.
