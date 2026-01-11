# Security Policy

## Supported Versions
| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability
Kodiak is a security tool, but it (and we) are not infallible.
If you find a vulnerability in Kodiak itself (e.g., RCE via the dashboard, API security issues):

1.  **DO NOT** open a public GitHub issue.
2.  Email us at `security@kodiak.ai` (or user specified contact).
3.  We will respond within 48 hours.

## Safety Warnings
Kodiak is a powerful security tool designed for authorized testing only.

### Usage Guidelines
- **Authorization**: Only scan targets you own or have explicit permission to test.
- **Liability**: The authors are not responsible for misuse of this tool.
- **Sandboxing**: While we sandbox tools in Docker, running untrusted code always carries risk. Run Kodiak on an isolated VM for maximum security.

### Deployment Security
Since Kodiak operates without built-in authentication, consider these security measures:

- **Network Isolation**: Deploy behind a VPN or restrict access via firewall rules
- **TLS Encryption**: Use a reverse proxy with TLS for production deployments
- **Access Control**: Implement IP allowlists or API key protection at the network level
- **Data Protection**: Ensure scan results and credentials are stored securely
- **Regular Updates**: Keep Kodiak and its dependencies updated

### Responsible Disclosure
We encourage responsible disclosure of security issues and will work with researchers to address vulnerabilities promptly.
