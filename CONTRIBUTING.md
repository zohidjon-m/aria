# Contributing

Thank you for considering a contribution to Open AML Compliance Sidecar.

This project is a public-alpha AML investigation sidecar. Keep contributions
aligned with the core boundary: agents investigate and propose, humans decide,
and bank source systems remain read-only unless a bank-owned integration
explicitly controls writes with RBAC and audit.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . -r requirements.txt
python -m unittest discover -s tests
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . -r requirements.txt
python -m unittest discover -s tests
```

For the optional frontend demo:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

## Contribution Rules

- Do not add production claims that are not supported by tests and documented
  evaluation.
- Do not add autonomous alert dismissal, autonomous SAR filing, or source-system
  mutation behavior to the agent layer.
- Keep source adapters narrow, typed, allowlisted, and parameterized.
- Keep generated artifacts in sidecar storage.
- Add or update tests for behavior changes.
- Update docs when public behavior, configuration, or integration guidance
  changes.

## Pull Request Checklist

- Python tests pass.
- Frontend lint/build pass when frontend files change.
- No real credentials, customer data, API keys, database dumps, or local cache
  files are committed.
- Public-facing language preserves the public-alpha limitation and human-review
  posture.
- New dependencies are justified and included in the appropriate manifest.
