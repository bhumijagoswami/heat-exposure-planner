# Progress

- Done — M1 scaffold on `dev`, Python 3.12 venv, hash-locked development dependencies, credential exclusions, local Git hook and security notes.
- Checks — `make check` runs Ruff, eight Git exclusion tests and Bandit. Run `gitleaks detect --redact` before every milestone commit.
- Setup — Use `uv venv --python 3.12`, then `make install hooks`. The hook requires Gitleaks v8.24.3 on PATH or in `.local/bin`.
- Decisions — Local project ID comes from `EE_PROJECT` in ignored `.env`. M2 will use the existing Earth Engine login through the SDK.
- Next — Wait for approval before M2 authentication and input validation.
- Known issues — Live Earth Engine initialization is pending M2.
