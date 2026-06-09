# Security Policy

## Supported Versions

This repository is currently a public alpha. Security fixes should target the
latest `main` branch unless maintainers explicitly create release branches.

## Reporting a Vulnerability

Do not open a public issue for suspected vulnerabilities, leaked secrets, data
exposure, authentication bypasses, prompt-injection paths, unsafe tool access,
or source-system write risks.

Report privately through GitHub's private vulnerability reporting feature when
available, or contact the repository owner directly. Include:

- affected component,
- reproduction steps,
- expected impact,
- whether any credentials or sensitive data are involved,
- suggested mitigation if known.

## Security Boundary

The intended production boundary is bank-controlled data access. The sidecar
must not hold broad source-system write privileges and must not let an LLM
execute arbitrary SQL against bank systems.

Security-sensitive areas include:

- source adapters and MCP tools,
- runtime bounds and tool allowlists,
- RBAC and human decision endpoints,
- evidence persistence and audit logs,
- SAR draft confidentiality,
- model-provider and API-key configuration,
- prompt-injection handling for tool output.

## Public Alpha Limitations

This project has not completed a production threat model, bank-specific model
risk review, penetration test, or compliance approval. Treat the demo stack and
default Docker credentials as local evaluation tooling only.
