# emby-cli — desarrollo local, build y publicación GitHub
# Uso: cd src/app && make install | make test | make push | make release VERSION=X.Y.Z

PYTHON   ?= .venv/bin/python
PIP      ?= $(PYTHON) -m pip
VERSION  ?=

.PHONY: help venv install test build check clean push release

help:
	@echo "Desarrollo:"
	@echo "  make venv               Crear .venv si no existe"
	@echo "  make install            venv + pip install -e '.[dev]'"
	@echo "  make test               pytest -q"
	@echo "  make build              python -m build → dist/"
	@echo "  make check              twine check dist/*"
	@echo "  make clean              borrar dist/, build/, caches"
	@echo ""
	@echo "GitHub:"
	@echo "  make push               git push -u origin HEAD"
	@echo "  make release VERSION=X.Y.Z"
	@echo "                          tag vX.Y.Z + push + gh release"
	@echo "                          (CI publish.yml → PyPI)"

venv:
	@test -x $(PYTHON) || python3 -m venv .venv
	@$(PIP) install -q --upgrade pip

install: venv
	$(PIP) install -e ".[dev]"

test: install
	$(PYTHON) -m pytest -q

build: install
	$(PYTHON) -m build

check: build
	$(PYTHON) -m twine check dist/*

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true

push:
	@git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Not a git repo; init remote first."; exit 1; }
	git push -u origin HEAD

release:
ifndef VERSION
	$(error VERSION is required, e.g. make release VERSION=0.1.0)
endif
	@git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Not a git repo."; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "Working tree not clean."; git status --short; exit 1; }
	@grep -q "$(VERSION)" CHANGELOG.md || echo "WARNING: $(VERSION) not found in CHANGELOG.md"
	@git rev-parse "v$(VERSION)" >/dev/null 2>&1 && { echo "Tag v$(VERSION) already exists."; exit 1; } || true
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	git push origin HEAD
	git push origin "v$(VERSION)"
	@command -v gh >/dev/null 2>&1 && gh release create "v$(VERSION)" --generate-notes \
		|| echo "gh not found; tag pushed — create the GitHub release manually if needed."
