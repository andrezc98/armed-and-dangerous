# Ledger 2026-09-25-cal-pg-amd

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| postgres | amd-stock | m8a.4xlarge | 1 | 14.6 | 0.24 |
| postgres | amd-tuned | m8a.4xlarge | 1 | 15.2 | 0.25 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **19.57** |

estimate_per_day_usd: 80.00 - OK
