# Security Policy

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue. Use GitHub's private vulnerability-reporting option on the repository's **Security** tab when it is available. If that option is unavailable, contact the repository owner privately through their GitHub profile before sharing technical details.

Include the affected version or commit, reproduction steps, impact, and any suggested mitigation. Do not include real work records, databases, exports, credentials, or other personal data in a report.

## Security model

Alfy Work Intelligence is a local, single-user application. It does not provide authentication or authorization and is not designed to be exposed directly to an untrusted network or the public internet. Keep the backend and frontend bound to localhost unless you have added appropriate network security controls.

Application records, imports, exports, and backups may contain sensitive professional information. Store them in a protected local directory and inspect exports before sharing them.
