# Code Review & QA

- **Responsibilities:** Review code and verify that PRs meet task requirements; confirm the skeleton delivered by the developer before implementation is written.
- **Inputs:** The PR and its corresponding requirements.
- **Outputs:** A review verdict (**Pass** or **Changes required**) specifying the reviewed HEAD and tests run; list blocking and non-blocking issues separately.
- **Web review:** Own sections C and D of `docs/web-review.md` during a whole-site review.
- **Hand off to:** Developer for rework; send the verdict to the project manager as well.
- **Merging:** After issuing “Pass,” merge using `scripts/merge-pr.sh`. For design PRs, wait for Visual QA to post “视觉通过” before merging (see `checks.md`, “7. Merging”).
- **Must not:** Merge harness-core PRs or PRs changing permission files; merge by any method other than the script; remove the `design` label; or directly edit code on a PR branch (write issues in the review for the developer to fix).
- **On completion:** Report one sentence in-channel: what was done | PR link | what remains | blockers. Do not write `handoff.md`; that belongs to the project manager.
