# Observability Playbook

Enterprise Knowledge Copilot exposes Prometheus metrics under `/metrics`. Import the ready-made Grafana dashboard and alert rules below to get production-grade visibility in minutes.

## Dashboard
- File: `docs/observability/grafana_dashboard.json`
- Panels included:
  - Request rate by status (success, clarification, refusal)
  - Average request latency (rolling 5m)
  - Retrieval confidence p95
  - Cache hit rate
  - Decision counters (clarify vs refuse)
- Import steps:
  1. Open Grafana → Dashboards → Import.
  2. Paste the JSON file contents or upload directly.
  3. Select your Prometheus datasource and save.

## Alerts
- File: `docs/observability/alerts.yml`
- Drop into your Prometheus Alertmanager configuration to monitor:
  - **HighAgentLatency** – Average latency > 4s for 5m.
  - **ConfidenceDrop** – Median retrieval confidence < 0.4 for 10m.
  - **ClarificationSpike** – More than 50 clarifications within 15m.
- Each rule sets severity labels so you can wire them to paging or chat notifications easily.

## Deployment Notes
- Expose `/metrics` via an ingress or internal load balancer; scrape every 15s.
- Set `PROMETHEUS_MULTIPROC_DIR` if you run multiple API workers.
- Consider adding `Grafana` + `Alertmanager` containers to your docker-compose/k8s manifests for local parity.
