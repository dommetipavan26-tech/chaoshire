# Release checklist

Template used for every tagged ChaosHire release (v0.20.0, v0.20.1, v0.21.0,
v0.22.0 and v0.23.0 all followed it). Substitute the target version for `vX.Y.Z`.

This is a **blank template for a future release**, not an attestation that any
check has passed for the next tag. Tick items only after verifying the exact
release commit and deployment.

Counts and percentages are deliberately *not* written into this checklist. They
live in `chaoshire/build_info.py`, which `scripts/check_build_info.py` verifies
against a real pytest run in CI, so a stale number here cannot outlive the release
it described.

## Automated

- [ ] Ruff format and Ruff check pass
- [ ] Mypy passes (`python -m mypy`)
- [ ] Every collected test passes
- [ ] Coverage exceeds the 90% gate
- [ ] `python scripts/check_build_info.py --coverage-json coverage.json` reports no drift
- [ ] `python -m chaoshire train --check` confirms the pinned TalentFit v3 digest
- [ ] Frontend JavaScript parses
- [ ] Fairness gate returns PASS for LegacyCorp to MeritFirst
- [ ] Render reports the tagged API version
- [ ] Quality, fairness-gate, security, and browser workflows pass
- [ ] Local dependency audit reports no known vulnerabilities
- [ ] Workflow, Render, and Dependabot YAML parse successfully

## Owner actions

- [ ] Confirm the Security checks workflow passes after pushing the release-preparation commit
- [ ] Add the UptimeRobot `/api/ready` monitor and alert contact
- [ ] Verify `render.yaml` generates `CHAOSHIRE_API_KEY` at deploy time and sets non-zero read/write rate limits
- [ ] Confirm the generated key is stored somewhere the owner can retrieve it, and that `CHAOSHIRE_TRUST_FORWARDED_FOR=1` is active behind the Render proxy
- [ ] Test overview, Chaos, fairness review, guided demo, PDF, and evidence download on one Android or iPhone
- [ ] Create and push tag `vX.Y.Z`; the Release workflow publishes source, reports, evidence, checksums, and release notes
- [ ] Add the live URL and repository to résumé and LinkedIn

## Tag command

```bash
git tag -a vX.Y.Z -m "ChaosHire vX.Y.Z portfolio release"
git push origin vX.Y.Z
```

Do not create the tag until all workflows for the release-preparation commit are green.
