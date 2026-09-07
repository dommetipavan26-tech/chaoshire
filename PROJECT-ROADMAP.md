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
- [x] 95% Wilson confidence intervals
- [x] Exploratory two-proportion significance indicators
- [x] Pairwise intersectional group analysis
- [x] Statistical methodology and limitations documentation
- [x] SQLite-backed aggregate audit runs and history
- [x] Raw-row non-persistence privacy boundary
- [ ] Managed PostgreSQL adapter for durable cloud history

## Phase 3 — Chaos Lab framework

- [x] Reusable test interface: transform → score → compare → verdict
- [x] Candidate-level evidence for every changed decision
- [x] User-configurable test thresholds
- [x] Reproducible experiment IDs
- [x] Comparison between model versions
- [x] Fairness regression gate for CI/CD
- [x] Pluggable decision-source adapter contract
- [ ] Authenticated remote REST scoring connector

## Phase 4 — Reports and product polish

- [x] Downloadable self-contained HTML audit report
- [x] Native dependency-free PDF summary export
- [x] Guided demonstration mode
- [x] Deterministic evidence-grounded fairness review agent
- [x] Tamper-evident aggregate evidence bundles
- [x] Optional API-key write protection
- [x] Accessibility and mobile/PWA hardening
- [x] Request IDs, operational metrics, rate limiting, and privacy controls
- [ ] User accounts and auditor/reviewer roles
- [ ] Structured external log shipping
- [ ] Architecture diagram and short demonstration video

## Definition of portfolio-ready

A new user can understand the problem, clone the repository, run the application, execute the tests, audit a synthetic dataset, reproduce the published results, and understand the system's limitations without assistance.
