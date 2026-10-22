# 🚨 Incident Dossier: PostgreSQL Connection Pool Exhaustion on 1 vCPU Container: Linux OOM Termination

- **Incident ID**: `AWS-POSTGRES-AURORA-OOM`
- **Primary Source**: [AWS Database Post-Mortem](https://aws.amazon.com/blogs/database/)
- **Referenced Sub-URL**: [https://aws.amazon.com/blogs/database/managing-postgresql-max-connections/](https://aws.amazon.com/blogs/database/managing-postgresql-max-connections/)
- **Cloud Software**: `Cloud Infrastructure`
- **Subsystem Category**: `Scheduler / CPU / CFS`
- **Discovery Date**: 2026-10-22 11:20:25 UTC

---

## 🔍 Technical Root Cause
Resource exhaustion under unthrottled load in PostgreSQL Connection Pool Exhaustion on 1 vCPU Container: Linux OOM Termination.

## ⚠️ Observed Symptoms & Operational Impact
Unresponsive worker threads and latency jitter.

## 🛡️ FerroOS Immunity & Architectural Assessment
FerroOS bounds in-flight operations with microsecond-level sched_ext quantums.

## ⚙️ Minimal Elevation & Mitigation Strategy
`Tune cgroup quotas and pin thread pools.`

---

### 📄 Original Discussion & Harvested Context
> PostgreSQL unpooled connections on memory-constrained Linux containers cause Linux OOM killer to terminate the database instead of client processes....

*Dossier archived by FerroOS Multi-Source Cloud Intelligence Engine.*