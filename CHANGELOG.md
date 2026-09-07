# Changelog

All notable changes to ChaosHire will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use semantic versioning.

## [Unreleased]

### Added
- Modular `chaoshire` Python package with dedicated data, model, metric, chaos, schema, service, state, and route layers
- Ruff linting and a 90% minimum coverage gate in GitHub Actions
- End-to-end tests for explanations, filtered candidates, appeals, uploads, mitigations, and repeatable chaos experiments
- Organized OpenAPI tags and bounded request validation

### Changed
- `backend.py` is now a backward-compatible deployment shim; `uvicorn backend:app` remains supported
- Privilege-keyword injection now uses a local deterministic random generator, so repeated Chaos Lab calls are identical
- Test suite expanded from 12 to 19 tests with more than 97% package coverage

### Planned
- Configurable CSV schema mapping
- Persistent audit history
- Intersectional fairness analysis
- Downloadable audit reports
- Fairness regression gates for model releases

## [0.1.0] - 2026-09-06

### Added
- Deterministic 1,000-candidate synthetic demonstration
- LegacyCorp and MeritFirst reference scoring models
- Disparate-impact, demographic-parity, and equal-opportunity analysis
- Five-test counterfactual Chaos Lab and resilience score
- Candidate explanations, mitigation simulations, and appeals workflow
- CSV outcome upload and sample dataset download
- Responsive web dashboard and public Render deployment
- API health endpoint, automated tests, GitHub Actions, and Docker support

### Documentation
- Professional quick-start and responsible-use guidance
- Explicit disclosure that all built-in people, employers, and results are synthetic
- Methodology limitations and product roadmap
