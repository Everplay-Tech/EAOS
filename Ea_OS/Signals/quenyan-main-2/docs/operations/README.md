# Quenyan Operator Handbook

The files in this directory document the day-to-day operational procedures for running the Quenyan toolchain in production.  They complement the format and security specifications by focusing on deployment, observability, key-management, and recovery activities that are common to enterprise environments.

## Contents

- [Deployment Playbooks](./deployment.md) – sizing guidance, supported topologies, and automation hooks for CI/CD.
- [Logging & Monitoring](./logging_and_monitoring.md) – how to harvest structured logs, wire alerts, and visualise dependency graphs emitted by `mcs-reference`.
- [Disaster Recovery](./disaster_recovery.md) – runbooks for incident response, restoration, and KMS rotation hygiene.
- [Dictionary & Key Operations](./dictionary_and_key_operations.md) – rotation schedules, rollout/rollback procedures, audit checkpoints, and SRE readiness expectations for dictionaries and encryption keys.
- [Operator Tutorials](./tutorials.md) – task-oriented guides to help new staff bootstrap the CLI, integrate with build systems, and rehearse compliance workflows.

All procedures assume Quenyan v1.0 or later and make use of the new project workflows (`batch-encode`, `incremental-rebuild`, `dependency-graph`) as well as the key-management integrations delivered in this change set.
