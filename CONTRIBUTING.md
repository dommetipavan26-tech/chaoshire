# Contributing to ChaosHire

Thank you for helping improve responsible testing of automated decisions.

## Local workflow

1. Fork and clone the repository.
2. Create a focused branch: `git checkout -b feature/short-description`.
3. Create and activate a virtual environment.
4. Install development dependencies: `python -m pip install -c constraints/requirements-py311.txt -r requirements-dev.txt`.
5. Run the same default quality checks as CI before opening a pull request:

   ```bash
   python -m ruff check .
   python -m ruff format --check .
   python scripts/check_repository.py --require-node --strict
   python -m mypy
   python -m pytest --cov=chaoshire --cov-report=json -q
   python scripts/check_build_info.py --coverage-json coverage.json
   python -m chaoshire train --check
   python -m build
   python scripts/check_distribution.py --wheel dist/chaoshire-*.whl --sdist dist/chaoshire-*.tar.gz --constraints constraints/requirements-py311.txt
   ```

The repository checker requires Node.js (20 or newer is sufficient) to check the
standalone dashboard script. It checks every tracked/non-ignored new file;
ignored virtual environments, secrets, databases, and generated reports are not
source files. See the [file inventory](docs/operations/REPOSITORY-INVENTORY.md)
and [dated audit report](docs/operations/REPOSITORY-AUDIT.md) for scope and evidence.

The Playwright tests require optional browser dependencies and run separately;
see the [documentation index](docs/README.md) for their commands and the
[repository layout](README.md#repository-layout) for where each area lives.

## Pull-request expectations

- Keep changes focused and explain the user or research problem they solve.
- Add tests for metric, scoring, API, or data-validation changes.
- Do not update deterministic reference values without documenting why they changed.
- Clearly distinguish synthetic demonstrations from empirical findings.
- Do not commit applicant data, credentials, `.env` files, or generated reports.
- Describe fairness trade-offs; do not present one metric as universally correct.

## Reporting problems

Open a GitHub issue with reproduction steps, expected behavior, actual behavior, Python version, and relevant logs. For security or privacy issues, do not include sensitive data in a public issue.

## Responsible development

ChaosHire must not be used to make autonomous employment decisions. Contributions should improve auditing, transparency, reproducibility, candidate recourse, or responsible human review.


Use `constraints/requirements-py312.txt` for Python 3.12. These are complete Linux x86_64 version constraints, not hash locks; refresh them intentionally with `scripts/compile_constraints.py` (requires maintenance tools), then rerun advisories, training, suites and distribution checks. Dependency compatibility ranges remain in the requirement manifests for library consumers.

Optional database tests use `requirements-postgres.txt` and a disposable local `CHAOSHIRE_TEST_POSTGRES_URL`; run `python -m pytest tests/integration --require-postgres -q`. Each case uses a random schema, and nonlocal hosts are refused. They are separate from the default collected-test count. Do not reuse production credentials.
