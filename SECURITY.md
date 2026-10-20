# Security Policy

FerroOS takes the security of our operating system, userspace crates, and memory-safe abstractions seriously.

---

## Supported Versions

Security updates and critical vulnerability patches are applied to the active `main` branch and the latest stable recovery release.

| Version | Supported |
| :--- | :--- |
| `main` (Rolling Dev) | ✅ Yes |
| `v1.0.0-gold-recovery-point` / `release/v1.0-gold-stable` | ✅ Yes |
| `< 1.0.0` (Alpha / Pre-releases) | ❌ No |

---

## Reporting a Vulnerability

If you discover a potential security vulnerability in FerroOS:

1. **Do NOT open a public GitHub Issue.**
2. Report the vulnerability privately via **[GitHub Private Vulnerability Reporting](https://github.com/Praveen-1308/ferro-os/security/advisories/new)**.
3. Include:
   * A detailed description of the vulnerability.
   * Steps or a script to reproduce the issue.
   * Any potential impact (e.g. privilege escalation, memory disclosure, denial of service).
4. The project maintainers will acknowledge receipt within 48 hours and work with you to coordinate a secure patch and disclosure timeline.

---

## Security Guarantees & Architecture

* **Rust Userspace**: The PID 1 init system (`ferro-init`), core utilities (`ferro-core`), and package manager (`ferro-pkg`) are implemented in pure, memory-safe Rust, preventing buffer overflows, use-after-free, and pointer aliasing vulnerabilities.
* **Cryptographic Verification**: `ferro-pkg` (`rpk` v0.2.0) computes FIPS 180-4 standard SHA-256 hashes for all package payloads before unpacking.
* **Transactional Rollback**: Any mid-stream corruption or signature failure immediately triggers an atomic rollback, cleaning up extracted files and preventing broken state injection.
* **Dependabot & CodeQL**: Automated vulnerability scanners continuously audit our dependencies and codebases on GitHub Actions.
