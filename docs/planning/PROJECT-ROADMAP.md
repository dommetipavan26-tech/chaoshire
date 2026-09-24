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
- [x] Add automated formatting and static type checking (Ruff and mypy in CI)
- [x] Tagged GitHub releases (v0.20.0, v0.20.1, v0.21.0, v0.23.0, v0.23.3; v0.22.0, v0.23.1, v0.23.2 and v0.23.4 tags pending owner)

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
- [x] Non-assessable audit verdicts and strict reference-model validation
- [x] Optional PostgreSQL adapter for durable cloud history (behind env; SQLite stays default)

## Phase 3 — Chaos Lab framework

- [x] Reusable test interface: transform → score → compare → verdict
- [x] Candidate-level evidence for every changed decision
- [x] User-configurable test thresholds
- [x] Reproducible experiment IDs
- [x] Comparison between model versions
- [x] Fairness regression gate for CI/CD
- [x] Pluggable decision-source adapter contract
- [x] Authenticated remote REST scoring connector (`RemoteDecisionAdapter`, operator-configured via `CHAOSHIRE_REMOTE_MODELS`)

## Phase 4 — Reports and product polish

- [x] Downloadable self-contained HTML audit report
- [x] Native dependency-free PDF summary export
- [x] Guided demonstration mode
- [x] Deterministic evidence-grounded fairness review (a transparent rules engine — not an AI agent)
- [x] Tamper-evident aggregate evidence bundles
- [x] Optional API-key write protection
- [x] Accessibility and mobile/PWA hardening
- [x] Request IDs, operational metrics, rate limiting, and privacy controls
- [x] Installable PWA icons, manifest metadata, and offline icon caching
- [ ] User accounts and auditor/reviewer roles
- [x] Structured external log shipping (`CHAOSHIRE_LOG_WEBHOOK_URL`, HMAC-signed JSON events)
- [x] Architecture diagram (`docs/engineering/ARCHITECTURE.svg`)
- [ ] Short demonstration video

## Definition of portfolio-ready

A new user can understand the problem, clone the repository, run the application, execute the tests, audit a synthetic dataset, reproduce the published results, and understand the system's limitations without assistance.
