# Security Policy

## Supported Versions
| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability
Kodiak is a security tool, but it (and we) are not infallible.
If you find a vulnerability in Kodiak itself (e.g., RCE via the dashboard, unauthenticated API access):

1.  **DO NOT** open a public GitHub issue.
2.  Email us at `security@kodiak.ai` (or user specified contact).
3.  We will respond within 48 hours.

## Safety Warnings
Kodiak is a powerful tool.
- **Authorization**: Only scan targets you own or have explicit permission to test.
- **Liability**: The authors are not responsible for misuse of this tool.
- **Sandboxing**: While we sandbox tools in Docker, running untrusted code always carries risk. Run Kodiak on an isolated VM for maximum security.
