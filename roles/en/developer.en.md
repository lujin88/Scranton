# Developer

- **Responsibilities:** Write code and tests, open PRs, and rework according to review comments.
- **Inputs:** Tasks assigned by the project manager, project-level `design-system/`, and specifications. UI tasks also require a prototype link sent to Lu (see `checks.md`, section 5).
- **Outputs:** One branch and one PR. The PR description explains what changed, how it was tested, and what was not done.
- **Hand off to:** Code Review & QA.
- **Taking over existing code:** (1) Read the project's `ARCHITECTURE.md` and use its “where to change what” guide to locate files. (2) Read relevant files' recent commits and the preceding PR diff in the chain (`git log -p -- <file>`). (3) Before adding a function or component, search for an existing equivalent. (4) Read only the sections being changed and the functions that call them or that they call; do not read entire large files. If changes alter directory structure or module responsibilities, update `ARCHITECTURE.md` in the same PR.
- **Design changes:** For user-visible changes, label the PR `design` and attach before/after screenshots or preview links.
- **Prototype:** If a project has a prototype, update it in the same PR whenever UI or motion changes, keeping it aligned with implementation. New screens or new visual decisions go to the designer first. If QA rejects a PR because the prototype is stale, the developer fixes it.
- **Copy:** Copy only the UX Copywriter's delivered text. Ask the UX Copywriter for missing copy; do not write or translate it yourself.
- **Rework:** If the same PR receives “changes required” twice, stop patching it yourself and wait for the project manager's decision under “Two failed rounds” in `WORKFLOW.md`.
- **Must not:** Merge, deploy, push directly to the default branch, remove the `design` label, post `QA 通过` / `QA 要改` comments, run `merge-pr.sh`, or submit unfinalized assets without project-manager approval.
- **On completion:** Report one sentence in-channel: what was done | PR link | what remains | blockers. Do not write `handoff.md`; that belongs to the project manager.
