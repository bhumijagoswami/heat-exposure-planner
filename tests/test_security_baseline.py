import subprocess

import pytest


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".streamlit/secrets.toml",
        "service-account.json",
        "private.pem",
        "private.key",
        "data/cache/sample.parquet",
        ".venv/bin/python",
    ],
)
def test_sensitive_artifacts_are_ignored(path):
    subprocess.run(["git", "check-ignore", "--no-index", "-q", path], check=True)


def test_no_ignored_files_are_tracked():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--ignored", "--exclude-standard", "-z"]
    )
    assert not tracked
