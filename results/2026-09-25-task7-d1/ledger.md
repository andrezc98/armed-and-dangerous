# Ledger 2026-09-25-task7-d1

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| go | amd-stock | m8a.4xlarge | 1 | 63.5 | 1.03 |
| go | arm-stock | m9g.4xlarge | 1 | 62.9 | 0.82 |
| go | x86-stock | m8i.4xlarge | 1 | 63.0 | 0.89 |
| java | amd-stock | m8a.4xlarge | 1 | 59.0 | 0.96 |
| java | amd-tuned | m8a.4xlarge | 1 | 58.6 | 0.95 |
| java | amd-tuned-vthreads | m8a.4xlarge | 1 | 58.6 | 0.95 |
| java | arm-stock | m9g.4xlarge | 1 | 58.2 | 0.76 |
| java | arm-tuned | m9g.4xlarge | 1 | 58.0 | 0.76 |
| java | arm-tuned-vthreads | m9g.4xlarge | 1 | 57.7 | 0.75 |
| java | x86-smtoff | m8i.4xlarge | 1 | 57.6 | 0.81 |
| java | x86-stock | m8i.4xlarge | 1 | 58.4 | 0.82 |
| java | x86-tuned | m8i.4xlarge | 1 | 59.0 | 0.83 |
| java | x86-tuned-vthreads | m8i.4xlarge | 1 | 59.1 | 0.83 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **30.25** |

estimate_per_day_usd: 80.00 - OK
