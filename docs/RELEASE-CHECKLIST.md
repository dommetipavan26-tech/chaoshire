# Release checklist

Template used for every tagged ChaosHire release (v0.20.0, v0.20.1, v0.21.0, and
v0.22.0 all followed it). Substitute the target version for `vX.Y.Z`.

## Automated

- [x] Ruff passes
- [x] 98 tests pass
- [x] Coverage exceeds 90% (verified baseline: 97.65%)
- [x] Frontend JavaScript parses
- [x] Fairness gate returns PASS for LegacyCorp to MeritFirst
- [x] Render reports the tagged API version
- [x] Quality, fairness-gate, security, and browser workflows pass
- [x] Local dependency audit reports no known vulnerabilities
- [x] Workflow, Render, and Dependabot YAML parse successfully

## Owner actions

- [x] Confirm the Security checks workflow passes after pushing the release-preparation commit
- [ ] Add the UptimeRobot `/api/ready` monitor and alert contact
- [ ] Decide whether to configure `CHAOSHIRE_API_KEY` in Render
- [ ] Test overview, Chaos, agent, guided demo, PDF, and evidence download on one Android or iPhone
- [ ] Create and push tag `vX.Y.Z`; the Release workflow publishes source, reports, evidence, checksums, and release notes
- [ ] Add the live URL and repository to résumé and LinkedIn

## Tag command

```bash
git tag -a vX.Y.Z -m "ChaosHire vX.Y.Z portfolio release"
git push origin vX.Y.Z
```

Do not create the tag until all workflows for the release-preparation commit are green.
