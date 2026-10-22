# 🚨 Incident Dossier: The four horsemen behind Postgres outages

- **Incident ID**: `HN-48841546`
- **Primary Source**: [Hacker News](https://news.ycombinator.com/item?id=48841546)
- **Referenced Sub-URL**: [https://malisper.me/the-four-horsemen-behind-thousands-of-postgres-outages/](https://malisper.me/the-four-horsemen-behind-thousands-of-postgres-outages/)
- **Cloud Software**: `PostgreSQL`
- **Subsystem Category**: `Scheduler / CPU / CFS`
- **Discovery Date**: 2026-10-22 11:30:10 UTC

---

## 🔍 Technical Root Cause
Resource exhaustion under unthrottled load in The four horsemen behind Postgres outages.

## ⚠️ Observed Symptoms & Operational Impact
Unresponsive worker threads and latency jitter.

## 🛡️ FerroOS Immunity & Architectural Assessment
FerroOS bounds in-flight operations with microsecond-level sched_ext quantums.

## ⚙️ Minimal Elevation & Mitigation Strategy
`Tune cgroup quotas and pin thread pools.`

---

### 📄 Harvested Context & Discussion Text
> The four horsemen behind Postgres outages. Referenced source: https://malisper.me/the-four-horsemen-behind-thousands-of-postgres-outages/. Points: 3...

*Dossier archived by FerroOS Multi-Source Cloud Intelligence Engine.*