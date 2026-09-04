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
phases without the speaker saying go. Scaling a SUT node group from 0 is gated
like `tofu apply`. Budget ceiling: $200 total (v2 estimate $40-70). The cluster
is DOWN between lab days; between cells only the SUT node groups scale to 0.
Verify (describe-instances by project tag = 0 running) before leaving it
unattended. The runner never runs tofu.

## Language
Code, tests, commits: English. Everything the audience sees (slides, README,
speaker notes, result comments): neutral Spanish — never localized to the host
country, no voseo.

## Deliverable boundary
Spec: `docs/superpowers/specs/2026-09-02-armed-and-dangerous-design.md`.
Plan: `docs/superpowers/plans/2026-09-02-armed-and-dangerous.md`.
The speaker owns the official Google Slides template; we hand over
`slides/contenido.md` and image assets only.

## Sibling repos (read-only precedents, do not modify)
- `../kcd/kcd-argentina-2026-brainstorm-recap.md`: the submitted abstracts
  (§9 Argentina v1, §11b Perú v2) and the speaker's framing rules (§12).
  Its "no public Graviton5 inference evidence" line is outdated (Spare Cores,
  2026-06-12); never repeat it on a slide.
- `../rompe-tu-agente/`: copy `agent/config.py::require_sandbox()` and
  `demo/sanitize-check.sh` verbatim; `slides/contenido.md` + `slides/armado.md`
  are the deliverable pattern for the official Google Slides template.
- `../kcd/infra-eks/`: the EKS + Bottlerocket OpenTofu pattern that already ran
  m9g on EKS 1.36 (existing VPC, own public subnets, access entries API).

## Sanitization
No account IDs, sensitive ARNs, or credentials in anything committed. Run
`demo/sanitize-check.sh` before committing any result or asset; it must print
`sanitize-check: clean`.