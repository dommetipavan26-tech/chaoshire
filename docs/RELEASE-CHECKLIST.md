# v0.20.0 release checklist

## Automated

- [x] Ruff passes
- [x] 65 tests pass
- [x] Coverage exceeds 90%
- [x] Frontend JavaScript parses
- [x] Fairness gate returns PASS for LegacyCorp to MeritFirst
- [x] Render reports API version 0.20.0
- [x] Quality and fairness-gate workflows pass
- [x] Local dependency audit reports no known vulnerabilities
- [x] Workflow and Render YAML parse successfully

## Owner actions

- [ ] Confirm the new Security checks workflow passes after pushing this preparation commit
- [ ] Add the UptimeRobot `/api/ready` monitor and alert contact
- [ ] Decide whether to configure `CHAOSHIRE_API_KEY` in Render
- [ ] Test overview, Chaos, agent, guided demo, PDF, and evidence download on one Android or iPhone
- [ ] Create and push tag `v0.20.0`; the Release workflow will publish source, reports, evidence, checksums, and release notes
- [ ] Add the live URL and repository to résumé and LinkedIn

## Tag command

```bash
git tag -a v0.20.0 -m "ChaosHire v0.20.0 portfolio release"
git push origin v0.20.0
```

Do not create the tag until all workflows for the release-preparation commit are green.
