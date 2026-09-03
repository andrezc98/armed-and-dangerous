# CLAUDE.md — ARMed and Dangerous (Graviton5 medido en EKS)

## Verify every API against current docs, every task, every agent
This stack moves monthly (Karpenter, Pyroscope, k6 v2, terraform-aws-modules/eks,
image tags, Graviton families). Do NOT rely on training memory for versions,
CRD fields, flags, chart versions or image tags. Before writing or changing any
code, manifest or config: Context7 / official docs / GitHub releases of the
day, pin what you verify, and cite it in README. Every dispatched subagent gets
this instruction verbatim.

## AWS is the speaker's personal sandbox only
The default credentials on this machine belong to a client. Every script that
touches AWS calls `require_sandbox()` first (AWS_PROFILE must contain
"sandbox"). Never run `tofu apply`/`destroy`, push images, or start benchmark
phases without the speaker saying go. Budget ceiling: $200 total. The cluster
is DOWN between phases — verify (describe-instances by project tag = 0 running)
before leaving it unattended.

## Language
Code, tests, commits: English. Everything the audience sees (slides, README,
speaker notes, result comments): neutral Spanish — never localized to the host
country (voseo only if the stage is in Uruguay).

## Deliverable boundary
Spec: `docs/superpowers/specs/2026-09-02-armed-and-dangerous-design.md`.
Plan: `docs/superpowers/plans/2026-09-02-armed-and-dangerous.md`.
The speaker owns the official Google Slides template; we hand over
`slides/contenido.md` and image assets only.

## Sanitization
No account IDs, sensitive ARNs, or credentials in anything committed. Run
`demo/sanitize-check.sh` before committing any result or asset; it must print
`sanitize-check: clean`.