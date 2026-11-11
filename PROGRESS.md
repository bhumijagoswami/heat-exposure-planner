# Progress

- Done — M1 scaffold on `dev`, Python 3.12 venv, hash-locked development dependencies, credential exclusions, local Git hook and security notes.
- Done — M2 SDK initialization with local login or deployment secrets, validated analysis inputs, offline tests and opt-in live smoke test.
- Checks — `make check` passes Ruff, 46 offline tests and Bandit. Run `gitleaks detect --redact` before every milestone commit.
- Setup — Use `uv venv --python 3.12`, then `make install hooks`. The hook requires Gitleaks v8.24.3 on PATH or in `.local/bin`.
- Decisions — Local project ID comes from `EE_PROJECT` in ignored `.env`. Local initialization delegates credential discovery to the SDK. Deployment accepts EE_SERVICE_ACCOUNT_JSON via environment or a supplied st.secrets mapping.
- Decisions — Use the 2019–2025 analysis window. Reject grids conservatively using the buffered-circle area bound. Coordinate swaps are detectable only when a value violates its named axis range.
- Next — Wait for approval before M3 layer builders.
- Verification pending — User runs `.venv/bin/pytest -m live` manually to check real project access. Default pytest excludes live tests.
