# AGENTS.md

Entrypoint and operating guide for every agent working in this repository
(Claude Code, Cursor agents, and others). Read this first.

This is a portfolio-grade data platform: weather × US crop-yield correlation on
GCP, orchestrated with Airflow. See [README.md](README.md) for the stack and
[docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the phased build.

## 1. Plan Mode by Default

- Enter plan mode for any non-trivial task — 3+ steps or an architectural
  decision.
- Write the spec upfront. Detailed, unambiguous specs beat mid-task guessing.
- Plan verification too, not just the build: how will you prove it works?
- If something goes sideways, stop and re-plan. Don't keep pushing a failing
  approach.

## 2. Subagent Strategy

- Use subagents liberally to keep the main context window clean.
- Offload research, codebase exploration, and parallel analysis to subagents.
- One task per subagent — focused scope, focused execution.
- For hard problems, throw more compute at them by fanning out across subagents.

## 3. Commit Message Convention

Every commit message is **a single subject line**. No body, no footer, no
trailers.

### Format

```
<type>(<scope>): <imperative, concise description>
```

- **type** — one of: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`,
  `perf`, `style`, `ci`, `build`, `eslint`.
- **scope** — optional, lowercase area of the codebase (`ingestion`, `dbt`,
  `raw`, `marts`, `terraform`, `airflow`, `ci`, …).
- **description** — imperative mood, lowercase, no trailing period.
- The whole subject line stays **≤ 72 characters**.

### Enforcement

Enforced by [.githooks/commit-msg](.githooks/commit-msg), wired in as a
`commit-msg`-stage [pre-commit](https://pre-commit.com) hook. It strips
agent-injected `Co-authored-by:` and "Generated with/by …" lines, then rejects
anything that isn't a single conventional-commit subject line.

Activate once per clone (also handled by `make install`):

```bash
uv run pre-commit install
```

## 4. Skills

These skills are installed in this repo and load automatically when the work
calls for them — apply them proactively, no need to be told each time.

- **tlc-spec-driven** — feature and project planning in four phases
  (Specify → Design → Tasks → Implement). Reach for it when starting any new
  feature, phase, or non-trivial change; it operationalizes §1 (Plan Mode).
- **coding-guidelines** — the team's coding standards. Apply when writing,
  refactoring, or reviewing code in this repo.
