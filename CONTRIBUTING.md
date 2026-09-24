# Contributing to ChaosHire

Thank you for helping improve responsible testing of automated decisions.

## Local workflow

1. Fork and clone the repository.
2. Create a focused branch: `git checkout -b feature/short-description`.
3. Create and activate a virtual environment.
4. Install development dependencies: `python -m pip install -r requirements-dev.txt`.
5. Run the same default quality checks as CI before opening a pull request:

   ```bash
   python -m ruff check .
   python -m ruff format --check .
   python -m mypy
   python -m pytest --cov=chaoshire --cov-report=json -q
   python scripts/check_build_info.py --coverage-json coverage.json
   python -m chaoshire train --check
   ```

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
