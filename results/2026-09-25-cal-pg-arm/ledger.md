# Ledger 2026-09-25-cal-pg-arm

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| postgres | arm-stock | m9g.4xlarge | 1 | 23.1 | 0.30 |
| postgres | arm-tuned | m9g.4xlarge | 1 | 14.9 | 0.19 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **19.58** |

estimate_per_day_usd: 80.00 - OK
