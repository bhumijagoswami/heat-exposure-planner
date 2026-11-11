VENV := .venv/bin
export TMPDIR := $(CURDIR)/.local/tmp
export UV_CACHE_DIR := $(CURDIR)/.local/uv
export PIP_CACHE_DIR := $(CURDIR)/.local/pip
export PIP_CONFIG_FILE := /dev/null
export PIP_INDEX_URL := https://pypi.org/simple

.PHONY: check hooks lock install

check:
	$(VENV)/ruff check --quiet .
	$(VENV)/pytest -q -x
	$(VENV)/bandit -r src -q

hooks:
	git config --local core.hooksPath .githooks

lock:
	mkdir -p "$(TMPDIR)"
	$(VENV)/pip-compile --cache-dir .local/pip-tools --generate-hashes --allow-unsafe --output-file requirements.txt requirements.in

install:
	mkdir -p "$(TMPDIR)"
	uv pip install --python $(VENV)/python --require-hashes -r requirements.txt
