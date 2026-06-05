# Rules Directory

`rules/rules.example.json` is a sanitized sample rule set used by tests and quick-start examples.

Runtime deployments should copy it to `rules/rules.json` and then edit the local copy:

```bash
mkdir -p rules
cp rules/rules.example.json rules/rules.json
```

`rules/rules.json` is intentionally ignored because local strategy settings can become user-specific research state. Do not commit personal rules, production parameters, broker outputs, or trade history.
