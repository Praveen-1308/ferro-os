# FerroOS Testing & Quality Assurance Suite

FerroOS incorporates an extensive, automated verification suite designed to validate every layer of the operating system from kernel-level security to userspace application parity.

---

## Testing Framework & Test Suite Index

| Test Category | Suite File | Coverage & Purpose | Passing Rate |
| :--- | :--- | :--- | :--- |
| **Negative Scenarios & Chaos** | [CHAOS_AND_NEGATIVE_SCENARIOS.md](CHAOS_AND_NEGATIVE_SCENARIOS.md) | 9 adversarial negative scenarios: OOM bombs, fork bombs, broker termination, Landlock escapes. | **9 / 9 (100%)** |
| **GNU Differential Parity** | [../operations/COREUTILS_AND_PARITY.md](../operations/COREUTILS_AND_PARITY.md) | 30 head-to-head differential parity tests vs Ubuntu GNU coreutils. | **30 / 30 (100%)** |
| **Sandbox Profiles & Mesh** | [../security/LANDLOCK_SANDBOXING.md](../security/LANDLOCK_SANDBOXING.md) | 4 selectable sandbox profiles (strict, shared, broker, dev) and shared memory pool. | **4 / 4 (100%)** |
| **Supervisor & Containers** | [../operations/SERVICE_SUPERVISION.md](../operations/SERVICE_SUPERVISION.md) | `ferro-superd` process supervision and `ferrocage` container lifecycle tests. | **8 / 8 (100%)** |
| **Vulnerability Audit** | [../security/SYSTEM_HARDENING_AND_CWE.md](../security/SYSTEM_HARDENING_AND_CWE.md) | CWE-22, CWE-78, CWE-400, CWE-426, CWE-190, CWE-226 exploit defenses. | **5 / 5 (100%)** |
| **Bare-Metal QEMU Boot** | [../developer/BUILD_AND_PACKAGING.md](../developer/BUILD_AND_PACKAGING.md) | Automated headless QEMU hardware bootloader and serial console test. | **100% Boot** |

---

## Running the Complete Automated Test Suite

```bash
# 1. Run GNU coreutils differential parity suite
python3 tools/differential_parity_engine.py

# 2. Run selectable sandbox profiles & shared memory mesh test
python3 tools/test_sandbox_profiles_and_mesh.py

# 3. Run supervisor and container lifecycle tests
python3 tools/test_supervisor_and_container.py

# 4. Run 9 negative chaos & security scenarios
python3 tools/test_negative_scenarios_and_chaos.py

# 5. Run full codebase survey & architecture graph validator
python3 tools/survey_full_ferro_os.py
```
