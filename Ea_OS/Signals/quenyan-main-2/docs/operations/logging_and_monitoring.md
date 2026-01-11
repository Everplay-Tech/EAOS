# Logging and Monitoring

The upgraded CLI emits structured JSON logs that make it easy to stream telemetry into existing observability stacks.  This document explains how to ingest those events, derive metrics, and visualise dependency graphs for fleet-wide awareness.

## 1. Log Formats

The global `--log-format` flag supports three modes:

| Mode | Behaviour | Use Case |
| --- | --- | --- |
| `json` | Machine-friendly events with timestamps and payloads | Default; forward to SIEM / log aggregation. |
| `plain` | Compact `event: payload` text | Local debugging and ad-hoc analysis. |
| `quiet` | Suppresses structured logs | Benchmarking or piping binary output to stdout. |

Every log event includes:

```json
{
  "timestamp": "2024-03-16T12:15:03.123456Z",
  "event": "project-batch-encode",
  "payload": {
    "processed": 12,
    "project_root": "/workspace/app",
    "integrations": [ { "system": "cargo", "manifest_path": "Cargo.toml", ... } ]
  }
}
```

## 2. Shipping Logs

1. **Filebeat / Fluent Bit** – tail `stderr` from the CLI process and ship to your collector.  Parse as JSON and index `payload.project_root` for dashboards.
2. **Systemd journal** – wrap the CLI in a `systemd` service unit.  The journal will automatically capture the JSON which can then be forwarded to Loki or Elastic.
3. **Kubernetes** – run the CLI inside a job or CronJob.  The JSON logs appear on `stdout` and can be scraped by the cluster-wide log pipeline.

Recommended fields to index:

- `event` – discriminates encode vs dependency graph actions.
- `payload.integrations[].system` – highlights which build tools are active.
- `payload.key_id` (from `key-metadata` events) – supports audit requirements.

## 3. Metrics Extraction

| Metric | Event Source | Computation |
| --- | --- | --- |
| Successful batch encodes | `project-batch-encode` | Count events grouped by `project_root`. |
| Incremental rebuild churn | `project-incremental-file` | Sum `action == "rebuilt"` per run. |
| Key rotations | `key-rotation` | Count occurrences per provider/key. |

Alert when the ratio of `rebuilt` to total files exceeds 20% over a rolling 7-day window, which signals dependency churn or stale state files.

## 4. Visualising Dependency Graphs

1. Run `mcs-reference project dependency-graph --json > graph.json`.
2. Load `graph.json` into a graphing tool (e.g., Neo4j Bloom, Graphviz) using the adjacency list stored at `payload.graph`.
3. Overlay build integration metadata from `payload.integrations` to see which subsystems will be impacted by upstream outages.

## 5. Monitoring KMS Metadata

The `Keys` CLI command exposes KMS rotation status via structured logs and optional JSON/YAML output files.  Suggested pipeline:

1. Nightly, run `mcs-reference keys --provider aws --key-id alias/quenyan --json > kms-status.json`.
2. Parse `kms-status.json` and raise a warning if `rotation_due` is within 7 days.
3. Archive the audit trail array for compliance review.

## 6. Example Loki Configuration

```yaml
scrape_configs:
  - job_name: quenyan
    pipeline_stages:
      - json:
          expressions:
            event: event
            project: payload.project_root
            action: payload.action
      - labels:
          event:
          project:
    static_configs:
      - targets: [localhost]
        labels:
          __path__: /var/log/quenyan/*.log
```

With this pipeline you gain end-to-end visibility into encoding throughput, dependency topology changes, and cryptographic key hygiene.
