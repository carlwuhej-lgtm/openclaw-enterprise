# Security Policy

## Reporting a Vulnerability

We take the security of OpenClaw Enterprise seriously. If you believe you have found a security vulnerability, please report it to us as described below.

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email at security@openclaw.local with the following information:

1. Description of the vulnerability
2. Steps to reproduce the issue
3. Potential impact
4. Suggested fix (if any)

## Response Time

We will acknowledge receipt of your report within 48 hours and will send you a more detailed response within 5 business days.

## Security Best Practices

When deploying OpenClaw Enterprise in production:

1. **Change default credentials** - Always change the default `admin/admin` password
2. **Use strong SECRET_KEY** - Generate a random 64-character key for JWT signing
3. **Enable HTTPS** - Use SSL/TLS for all communications
4. **Regular updates** - Keep the software up to date
5. **Monitor logs** - Regularly review audit logs for suspicious activity
6. **Network isolation** - Deploy behind a firewall and limit access

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

---

**Thank you for helping keep OpenClaw Enterprise secure!**
