# l3io-age-passphrase — local developer entry points.
#
# Owner rule (Shawn, 2026-11-08): nothing is released while CI is red, and a
# release/tag/publish follows a full local act run of everything act can run.
# GitHub-only jobs are named in AGENTS.md and in `make preflight` output.

UV ?= uv
ACT ?= act
PYTHON ?= 3.11
GH ?= gh

# ~/.actrc declares secrets as bare `-s NAME`; infisical puts them in the env.
# Do NOT substitute placeholder GITHUB_TOKEN values.
INFISICAL ?= infisical
INFISICAL_PROJECT ?= 7ca0e01b-28f6-4a61-b901-5fe834e1661a
INFISICAL_ENV ?= prod
INFISICAL_PATH ?= /ci/act/l3io-age-passphrase
ACT_RUNNER ?= $(INFISICAL) run --projectId $(INFISICAL_PROJECT) --env $(INFISICAL_ENV) --path $(INFISICAL_PATH) --

# Full linux matrix under act. macos-latest is GitHub-only (named in preflight).
ACT_FLAGS ?= --var-file .act.vars --concurrent-jobs 1 -W .github/workflows/ci.yml --matrix os:ubuntu-latest
ACT_DRYRUN_FLAGS ?= --var-file .act.vars --concurrent-jobs 1 --dryrun
ACT_DRYRUN_LEGS := .github/act-dryrun-legs.json
PREFLIGHT_STAMP = $(shell git rev-parse --git-path l3io-preflight)

RELEASE_WORKFLOW ?= release.yml
RELEASE_BRANCH ?= main
BUMP ?=
_BUMP_WORDS := patch minor major
_BUMP_GOAL := $(firstword $(filter $(_BUMP_WORDS),$(MAKECMDGOALS)))
_BUMP := $(if $(BUMP),$(BUMP),$(_BUMP_GOAL))

.PHONY: help sync develop check lint test build clean \
	ci preflight ci-job ci-list ci-dryrun ci-dryrun-one \
	release release-patch release-minor release-major $(_BUMP_WORDS)

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

sync: ## Install dev tools into .venv
	$(UV) sync --group dev

develop: ## Build the extension into the project venv
	$(UV) run maturin develop --uv --release

check: lint test ## Lint and test

lint: ## Ruff on Python sources
	$(UV) run ruff check tests
	$(UV) run ruff format --check tests

test: develop ## Run pytest against the built extension
	$(UV) run pytest

build: ## Build release wheels into dist/
	mkdir -p dist
	$(UV) run maturin build --release --out dist

clean: ## Remove build artefacts
	rm -rf dist target/wheels .pytest_cache .ruff_cache

# ---- local CI replay -------------------------------------------------------

ci: ## Replay ci.yml linux legs under act (macos is GitHub-only)
	$(ACT_RUNNER) $(ACT) $(ACT_FLAGS)

ci-job: ## Replay one job: make ci-job JOB=clippy
	@test -n "$(JOB)" || { echo "usage: make ci-job JOB=<job-id>"; exit 2; }
	$(ACT_RUNNER) $(ACT) $(ACT_FLAGS) -j $(JOB)

ci-list: ## List the jobs act would run
	$(ACT_RUNNER) $(ACT) $(ACT_FLAGS) -l

# act runs: linux ci.yml. GitHub-only: macos-latest legs; release.yml; publish.yml.
# ci-dryrun resolves action refs in the GitHub-only workflows.
preflight: ## Everything act can run, for this commit; required by make release
	@set -eu; \
	if [ -n "$$(git status --porcelain --untracked-files=no)" ]; then \
	  echo "tracked files are modified: preflight would not be testing the commit"; exit 1; \
	fi; \
	rm -f "$(PREFLIGHT_STAMP)"; \
	$(MAKE) --no-print-directory check; \
	$(MAKE) --no-print-directory ci; \
	$(MAKE) --no-print-directory ci-dryrun; \
	git rev-parse HEAD > "$(PREFLIGHT_STAMP)"; \
	echo "preflight passed for $$(git rev-parse --short HEAD)."; \
	echo "GitHub-only: macos-latest CI legs; release.yml; publish.yml (dry-run resolved)."

ci-dryrun: ## Dry-run release.yml and publish.yml, resolving every action ref
	@set -eu; \
	test -f $(ACT_DRYRUN_LEGS) || { echo "missing $(ACT_DRYRUN_LEGS)"; exit 1; }; \
	legs=$$(python3 -c "import json;[print(l['workflow'],l['event'],l.get('eventpath','-'),','.join(f'{k}={v}' for k,v in (l.get('inputs') or {}).items()) or '-') for l in json.load(open('$(ACT_DRYRUN_LEGS)'))['legs']]"); \
	test -n "$$legs" || { echo "no legs declared -- this gate would pass vacuously"; exit 1; }; \
	rm -f $(CURDIR)/.act-dryrun.rc; \
	echo "$$legs" | while read -r wf ev epath inputs; do \
	  args=""; \
	  [ "$$epath" = "-" ] || args="$$args -e $$epath"; \
	  if [ "$$inputs" != "-" ]; then \
	    for kv in $$(echo "$$inputs" | tr ',' ' '); do args="$$args --input $$kv"; done; \
	  fi; \
	  printf '%-13s %-18s %-40s ' "$$wf" "$$ev" "$$inputs"; \
	  if $(ACT_RUNNER) $(ACT) $(ACT_DRYRUN_FLAGS) -W ".github/workflows/$$wf" $$ev $$args \
	       >$(CURDIR)/.act-dryrun.log 2>&1; then echo "ok"; else \
	    echo "FAILED"; \
	    grep -iE "couldn.t find remote ref|failed to fetch|^Error:|invalid|unable to" $(CURDIR)/.act-dryrun.log \
	      | head -3 | sed 's/^/  /'; \
	    echo fail >> $(CURDIR)/.act-dryrun.rc; \
	  fi; \
	  rm -f $(CURDIR)/.act-dryrun.log; \
	done; \
	if [ -f $(CURDIR)/.act-dryrun.rc ]; then rm -f $(CURDIR)/.act-dryrun.rc; \
	  echo "one or more legs failed"; exit 1; \
	else echo "all legs dry-run clean; every action ref resolved"; fi

ci-dryrun-one: ## Dry-run one workflow: make ci-dryrun-one WF=release.yml
	@test -n "$(WF)" || { echo "set WF, e.g. make ci-dryrun-one WF=release.yml"; exit 1; }
	@case "$(WF)" in \
	  release.yml) ev="workflow_dispatch --input bump=patch" ;; \
	  publish.yml) ev="workflow_dispatch --input target=none --input dry_run=true" ;; \
	  *)           ev="push" ;; \
	esac; \
	$(ACT_RUNNER) $(ACT) $(ACT_DRYRUN_FLAGS) -W .github/workflows/$(WF) $$ev

# ---- releasing -------------------------------------------------------------

release: ## Cut a release: make release patch|minor|major
	@set -eu; \
	bump="$(_BUMP)"; \
	if [ -z "$$bump" ]; then \
	  echo "usage: make release patch|minor|major   (or make release BUMP=patch)"; \
	  exit 2; \
	fi; \
	case "$$bump" in patch|minor|major) ;; *) echo "unknown bump '$$bump'"; exit 2 ;; esac; \
	command -v $(GH) >/dev/null || { echo "gh is not installed"; exit 1; }; \
	$(GH) auth status >/dev/null 2>&1 || { echo "gh is not authenticated: run 'gh auth login'"; exit 1; }; \
	branch=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$branch" != "$(RELEASE_BRANCH)" ]; then \
	  echo "on '$$branch', not '$(RELEASE_BRANCH)' -- release.yml tags whatever it checks out"; exit 1; \
	fi; \
	if [ -n "$$(git status --porcelain --untracked-files=no)" ]; then \
	  echo "tracked files are modified. That work is NOT in the release."; \
	  git status --short --untracked-files=no; exit 1; \
	fi; \
	git fetch --quiet origin $(RELEASE_BRANCH); \
	if [ "$$(git rev-parse HEAD)" != "$$(git rev-parse origin/$(RELEASE_BRANCH))" ]; then \
	  echo "HEAD and origin/$(RELEASE_BRANCH) differ -- push or pull first."; \
	  echo "Local: $$(git rev-parse --short HEAD)  origin: $$(git rev-parse --short origin/$(RELEASE_BRANCH))"; \
	  exit 1; \
	fi; \
	sha=$$(git rev-parse HEAD); \
	if [ "$$(cat "$(PREFLIGHT_STAMP)" 2>/dev/null)" != "$$sha" ]; then \
	  echo "no local preflight for $$(git rev-parse --short HEAD): run 'make preflight' first"; exit 1; \
	fi; \
	runs=$$($(GH) run list --commit "$$sha" --json name,status,conclusion); \
	if [ "$$(echo "$$runs" | jq length)" -eq 0 ]; then \
	  echo "GitHub has no runs for $$sha yet -- CI must have run and passed"; exit 1; \
	fi; \
	red=$$(echo "$$runs" | jq -r '.[] | select(.status != "completed" or .conclusion != "success") | "\(.name): \(.status)/\(.conclusion)"'); \
	if [ -n "$$red" ]; then echo "CI on GitHub is not green for this commit:"; echo "$$red"; exit 1; fi; \
	latest=$$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1); \
	echo "  repo         $$($(GH) repo view --json nameWithOwner -q .nameWithOwner)"; \
	echo "  commit       $$(git rev-parse --short HEAD)"; \
	echo "  latest tag   $${latest:-<none>}"; \
	echo "  bump         $$bump"; \
	echo "  effect       bumps version if needed, waits for CI on that commit, tags, dispatches Publish"; \
	printf "\nType the bump to confirm: "; \
	read -r reply; \
	if [ "$$reply" != "$$bump" ]; then echo "aborted"; exit 1; fi; \
	$(GH) workflow run $(RELEASE_WORKFLOW) --ref $(RELEASE_BRANCH) -f bump="$$bump"; \
	echo; \
	echo "dispatched. Watch it with:  $(GH) run watch \$$($(GH) run list --workflow $(RELEASE_WORKFLOW) --limit 1 --json databaseId -q '.[0].databaseId')"

release-patch: ## Release a patch version
	@$(MAKE) --no-print-directory release BUMP=patch

release-minor: ## Release a minor version
	@$(MAKE) --no-print-directory release BUMP=minor

release-major: ## Release a major version
	@$(MAKE) --no-print-directory release BUMP=major

$(_BUMP_WORDS):
	@case " $(MAKECMDGOALS) " in \
	  *" release "*) : ;; \
	  *) echo "make: '$@' is not a target. Did you mean 'make release $@'?"; exit 2 ;; \
	esac
