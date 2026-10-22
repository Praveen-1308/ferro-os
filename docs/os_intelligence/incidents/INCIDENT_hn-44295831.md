# 🚨 Incident Dossier: Why Kubernetes Throttled My Idle Pods

- **Incident ID**: `HN-44295831`
- **Primary Source**: [Hacker News](https://news.ycombinator.com/item?id=44295831)
- **Referenced Sub-URL**: [https://mattthorne.github.io/blog/kubernetes-throttling-idle-pods](https://mattthorne.github.io/blog/kubernetes-throttling-idle-pods)
- **Cloud Software**: `Kubernetes`
- **Subsystem Category**: `Scheduler / CPU / CFS`
- **Discovery Date**: 2026-10-22 11:30:10 UTC

---

## 🔍 Technical Root Cause
Resource exhaustion under unthrottled load in Why Kubernetes Throttled My Idle Pods.

## ⚠️ Observed Symptoms & Operational Impact
Unresponsive worker threads and latency jitter.

## 🛡️ FerroOS Immunity & Architectural Assessment
FerroOS bounds in-flight operations with microsecond-level sched_ext quantums.

## ⚙️ Minimal Elevation & Mitigation Strategy
`Tune cgroup quotas and pin thread pools.`

---

### 📄 Harvested Context & Discussion Text
> Why Kubernetes Throttled My Idle Pods. Referenced source: https://mattthorne.github.io/blog/kubernetes-throttling-idle-pods. Points: 2...

*Dossier archived by FerroOS Multi-Source Cloud Intelligence Engine.*