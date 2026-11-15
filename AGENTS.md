# CommerceLens engineering rules

- Keep business rules in the framework-free domain. Keep database connections, retrieval and model I/O in infrastructure adapters.
- Keep benchmarks and reference answers outside the installed agent package and its context. Never infer model performance from deterministic fixtures.
- Record data provenance and keep local datasets, credentials and raw model run outputs out of Git.
- For changes affecting metrics or evaluation, verify units, grain, denominators, time filters and sample scope. Include reproduction and test evidence in PRs.
- Work on feature branches. Remote merges, destructive repository operations and changes to visibility require user action.
