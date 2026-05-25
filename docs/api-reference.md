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
