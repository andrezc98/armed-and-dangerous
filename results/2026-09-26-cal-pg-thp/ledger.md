# Ledger 2026-09-26-cal-pg-thp

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| postgres | amd-tuned | m8a.4xlarge | 1 | 15.4 | 0.25 |
| postgres | arm-tuned | m9g.4xlarge | 1 | 14.8 | 0.19 |
| postgres | x86-tuned | m8i.4xlarge | 1 | 15.5 | 0.22 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **19.74** |

estimate_per_day_usd: 80.00 - OK
