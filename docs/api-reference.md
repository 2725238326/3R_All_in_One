# API Reference

Base URL: `http://127.0.0.1:8765`

## Health

```
GET /api/health
```

## Jobs

```
GET    /api/bootstrap          # App bootstrap data
GET    /api/jobs               # List all jobs
POST   /api/jobs               # Create job
GET    /api/jobs/{id}          # Get job detail
POST   /api/jobs/{id}/dispatch # Dispatch to remote
POST   /api/jobs/{id}/retry    # Retry failed job
POST   /api/jobs/{id}/cancel   # Cancel running job
POST   /api/jobs/{id}/duplicate # Duplicate as new job
GET    /api/jobs/{id}/scene-meta # Get normalized scene_meta.json
GET    /api/jobs/{id}/contract-check # Validate outputs against result contract
GET    /api/jobs/{id}/bundle   # Download job bundle (.zip)
```

## Batch Operations

```
POST   /api/jobs/batch-dispatch   # Dispatch multiple jobs
POST   /api/jobs/batch-cancel     # Cancel multiple jobs
```

## Scheduler

```
GET    /api/scheduler/status   # Queue status
POST   /api/scheduler/enqueue  # Add job to queue
POST   /api/scheduler/dequeue  # Remove from queue
POST   /api/scheduler/config   # Update scheduler config
```

## Metrics & Reports

```
GET    /api/jobs/{id}/metrics              # Compute evaluation metrics
GET    /api/jobs/{id}/report               # Export HTML/PDF report
POST   /api/jobs/{id}/visuals/generate     # Generate visual artifacts
GET    /api/jobs/{id}/visuals/{filename}   # Get visual artifact file
```

## Samples & Comparison

```
GET    /api/samples                         # List samples
GET    /api/compare/samples/{id}            # Sample comparison data
GET    /api/compare/samples/{id}/report     # Comparison report
POST   /api/compare/samples/{id}/visuals/generate  # Generate comparison visuals
```

## System

```
GET    /api/system/resources    # CPU/GPU/memory/disk stats
GET    /api/deployment/status   # Remote model deployment status
GET    /api/runners/availability # Optional runner availability
```

## Agent

```
GET    /api/agent/registry        # List Agent model blueprints
GET    /api/agent/registry/{model} # Get one model blueprint
GET    /api/agent/validate        # Validate all blueprints
GET    /api/agent/validate?model={model} # Validate one blueprint
GET    /api/agent/builds          # List environment build tasks
GET    /api/agent/builds/{task_id} # Get build task status
POST   /api/agent/build/{model}   # Start async environment build task
POST   /api/agent/smoke/{model}   # Start async smoke check task
POST   /api/agent/health/{model}  # Start async health check task
POST   /api/agent/smoke-batch     # Start async batch smoke checks
GET    /api/agent/checks          # List smoke/health check tasks
GET    /api/agent/checks/{task_id} # Get smoke/health check task status
GET    /api/agent/experiment-record/{job_id} # Get reproducible experiment manifest
GET    /api/agent/experiment-record/{job_id}/download # Download experiment record zip
```

## Experiments

```
GET    /api/experiments/templates           # List experiment templates
POST   /api/experiments/templates           # Create experiment template
DELETE /api/experiments/templates/{id}      # Delete experiment template
POST   /api/experiments/templates/{id}/run  # Create jobs from a template
GET    /api/experiments/runs                # List experiment runs
GET    /api/experiments/runs/{run_id}       # Get experiment run detail
```

## AI Advisor

```
GET    /api/advisor/status      # Advisor availability
GET    /api/advisor/providers   # Available AI providers
GET    /api/advisor/config      # Read config (masked key)
POST   /api/advisor/config      # Update config
POST   /api/advisor/evaluate    # AI evaluation for a job
```

## WebSocket

```
WS     /ws/jobs/{id}           # Real-time job status updates
```
