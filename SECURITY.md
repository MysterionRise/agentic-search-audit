# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **GitHub Security Advisories** (Preferred): Use [GitHub's private vulnerability reporting](https://github.com/MysterionRise/agentic-search-audit/security/advisories/new) to report vulnerabilities directly.

2. **GitHub issue with the `security` label** only for non-sensitive reports, otherwise open a private advisory and include:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (if available)

### What to Expect

- **Initial Response**: Within 48 hours, we will acknowledge receipt of your report.
- **Assessment**: Within 7 days, we will assess the vulnerability and determine its severity.
- **Resolution**: We aim to resolve critical vulnerabilities within 30 days.
- **Disclosure**: We will coordinate with you on public disclosure timing.

### Scope

The following are in scope for security reports:

- **Authentication/Authorization bypass**
- **Injection vulnerabilities** (SQL, command, LDAP, etc.)
- **Cross-site scripting (XSS)**
- **Cross-site request forgery (CSRF)**
- **Sensitive data exposure**
- **Insecure cryptographic implementations**
- **Server-side request forgery (SSRF)**
- **Dependency vulnerabilities** with exploitable conditions

### Out of Scope

- Vulnerabilities in third-party services (e.g., LLM providers)
- Social engineering attacks
- Physical security issues
- Denial of service attacks (unless demonstrating a specific vulnerability)
- Spam or rate limiting issues without security impact

## Security Best Practices

When using this tool, follow these security guidelines:

### API Keys and Credentials

- **Never commit API keys** to version control
- Use environment variables for all secrets:
  ```bash
  export OPENAI_API_KEY="your-key"
  export ANTHROPIC_API_KEY="your-key"
  export OPENROUTER_API_KEY="your-key"
  ```
- Use `.env` files locally (included in `.gitignore`)
- Rotate API keys regularly

### Network Security

- Run in isolated network environments when testing against production sites
- Use VPN or proxy when appropriate
- Respect robots.txt and rate limits

### Data Handling

- Audit results may contain sensitive website data
- Store reports securely
- Do not share audit results containing proprietary information

### Docker Security

- Run containers with non-root users (already configured)
- Use specific image tags, not `latest`
- Scan images for vulnerabilities regularly

## Security Features

### Built-in Protections

1. **Input Validation**: All inputs are validated via Pydantic models
2. **robots.txt Compliance**: Enabled by default, respects crawl restrictions
3. **Rate Limiting**: Configurable throttling to prevent abuse
4. **No Credential Storage**: API keys are read from environment, never persisted
5. **Pre-commit Hooks**: Configured to detect accidentally committed secrets

### Compliance

- **robots.txt**: Respected by default (`--ignore-robots` only for authorized testing). `compliance.user_agent` is the agent used for that robots.txt request only.
- **User-Agent in the browser**: the launched backends rotate spoofed Chrome user agents and apply stealth patches (`browser/stealth.py`); the bridge backends use your real browser's identity unchanged. This is not transparent identification; check a site's terms before auditing it.
- **Crawl-delay**: parsed from robots.txt (`RobotsPolicy.get_crawl_delay`) but not applied; pacing comes from `run.throttle_rps`.
- **Real profiles**: on a bridge backend the audit never rotates identity, clears cookies or touches tabs it did not open. Screenshots of a logged-in session can contain account details; review `runs/` before sharing.

## Dependency Security

We regularly update dependencies to address known vulnerabilities. To check for vulnerabilities:

```bash
make audit-deps        # pip-audit against the locked dependency set, as CI does
```

## Security Changelog

| Date | Description |
|------|-------------|
| 2024-01-01 | Initial security policy |
| 2026-10-27 | Corrected the user-agent and crawl-delay claims; pip-audit in CI |

---

Thank you for helping keep Agentic Search Audit secure!
