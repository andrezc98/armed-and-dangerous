# Ledger 2026-09-25-cal-pg-x86

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| postgres | x86-stock | m8i.4xlarge | 1 | 14.8 | 0.21 |
| postgres | x86-tuned | m8i.4xlarge | 1 | 14.3 | 0.20 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **19.49** |

estimate_per_day_usd: 80.00 - OK
