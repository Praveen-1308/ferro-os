# 🚨 Incident Dossier: PHP2Shell was probed 4 days before disclosure. Is anyone doing a look-back hunt, not just patching?

- **Incident ID**: `REDDIT-SYSADMIN-1xc99ct`
- **Primary Source**: [Reddit r/sysadmin](https://www.reddit.com/r/sysadmin/comments/1xc99ct/php2shell_was_probed_4_days_before_disclosure_is/)
- **Referenced Sub-URL**: [https://aws.amazon.com/blogs/security/amazon-threat-intelligence-identifies-php2shell-exploitation-prior-to-public-disclosure-in-madpot/](https://aws.amazon.com/blogs/security/amazon-threat-intelligence-identifies-php2shell-exploitation-prior-to-public-disclosure-in-madpot/)
- **Cloud Software**: `Linux Server Administration`
- **Subsystem Category**: `Scheduler / CPU / CFS`
- **Discovery Date**: 2026-10-22 11:30:12 UTC

---

## 🔍 Technical Root Cause
Resource exhaustion under unthrottled load in PHP2Shell was probed 4 days before disclosure. Is anyone doing a look-back hunt, not just patching?.

## ⚠️ Observed Symptoms & Operational Impact
Unresponsive worker threads and latency jitter.

## 🛡️ FerroOS Immunity & Architectural Assessment
FerroOS bounds in-flight operations with microsecond-level sched_ext quantums.

## ⚙️ Minimal Elevation & Mitigation Strategy
`Tune cgroup quotas and pin thread pools.`

---

### 📄 Harvested Context & Discussion Text
> PHP2Shell was probed 4 days before disclosure. Is anyone doing a look-back hunt, not just patching? <!-- SC_OFF --><div class="md"><p>Quick recap for anyone catching up. AWS says its honeypots saw a PHP2Shell (CVE-2026-109618/109619) exploit attempt on 17 Oct, four days before the embargo lifted, from anonymised infrastructure (<a href="https://aws.amazon.com/blogs/security/amazon-threat-intelligence-identifies-php2shell-exploitation-prior-to-public-disclosure-in-madpot/">AWS write-up</a>). SecurityWeek reports the details leaked on 20 Oct and a PoC video went out early (<a href="https://www.s...

*Dossier archived by FerroOS Multi-Source Cloud Intelligence Engine.*