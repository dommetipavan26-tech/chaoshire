# ChaosHire development roadmap

## Product objective

Build an honest, reproducible, portfolio-grade platform for testing fairness risks in automated hiring decisions. ChaosHire is an auditing and decision-support tool—not an autonomous hiring system or legal certification service.

## Phase 1 — Engineering foundation

- [x] Deterministic reference demonstration
- [x] API and metric regression tests
- [x] GitHub Actions test workflow
- [x] Docker image and health endpoint
- [x] Professional README, license, changelog, security and contribution guidance
- [x] Split the monolithic backend into data, models, metrics, chaos, and API modules
- [x] Add linting and coverage reporting (Ruff + 90% CI coverage gate)
- [ ] Add automated formatting and static type checking
- [ ] Create the `v0.1.0` GitHub release

## Phase 2 — Real audit workflow

- [x] Configurable CSV column mapping
- [x] Configurable protected attributes and favorable outcome
- [x] Strong file and value validation
- [x] Configurable minimum group size and missing-data warnings
- [x] Downloadable JSON audit evidence
- [ ] Confidence intervals and statistical significance indicators
- [ ] Persistent audit runs and audit history
- [ ] Intersectional group analysis

## Phase 3 — Chaos Lab framework

- [ ] Reusable test interface: transform → score → compare → verdict
- [ ] Candidate-level evidence for every changed decision
- [ ] User-configurable test thresholds
- [ ] Reproducible experiment IDs
- [ ] Comparison between model versions
- [ ] Fairness regression gate for CI/CD

## Phase 4 — Reports and product polish

- [ ] Downloadable HTML/PDF audit report
- [ ] Guided demonstration mode
- [ ] Authentication and auditor/reviewer roles
- [ ] Accessibility and mobile QA
- [ ] Structured logging, rate limiting, and privacy controls
- [ ] Architecture diagram and short demonstration video

## Definition of portfolio-ready

A new user can understand the problem, clone the repository, run the application, execute the tests, audit a synthetic dataset, reproduce the published results, and understand the system's limitations without assistance.
