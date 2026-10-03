# Ledger 2026-09-27-task7-d3

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| go | amd-stock | m8a.4xlarge | 1 | 63.5 | 1.03 |
| go | arm-stock | m9g.4xlarge | 1 | 63.0 | 0.82 |
| go | x86-stock | m8i.4xlarge | 1 | 62.9 | 0.89 |
| inference | amd-stock | m8a.4xlarge | 1 | 29.2 | 0.47 |
| inference | amd-tuned | m8a.4xlarge | 1 | 28.2 | 0.46 |
| inference | arm-stock | m9g.4xlarge | 1 | 27.6 | 0.36 |
| inference | arm-tuned | m9g.4xlarge | 1 | 29.0 | 0.38 |
| inference | x86-stock | m8i.4xlarge | 1 | 27.7 | 0.39 |
| inference | x86-tuned | m8i.4xlarge | 1 | 27.3 | 0.39 |
| java | amd-stock | m8a.4xlarge | 1 | 58.1 | 0.94 |
| java | amd-tuned | m8a.4xlarge | 1 | 58.7 | 0.95 |
| java | amd-tuned-vthreads | m8a.4xlarge | 1 | 59.0 | 0.96 |
| java | arm-stock | m9g.4xlarge | 1 | 57.6 | 0.75 |
| java | arm-tuned | m9g.4xlarge | 1 | 58.1 | 0.76 |
| java | arm-tuned-vthreads | m9g.4xlarge | 1 | 57.9 | 0.76 |
| java | x86-stock | m8i.4xlarge | 1 | 58.6 | 0.83 |
| java | x86-tuned | m8i.4xlarge | 1 | 58.9 | 0.83 |
| java | x86-tuned-vthreads | m8i.4xlarge | 1 | 58.9 | 0.83 |
| mongo | amd-stock | m8a.4xlarge | 1 | 43.2 | 0.70 |
| mongo | amd-tuned | m8a.4xlarge | 1 | 43.7 | 0.71 |
| mongo | arm-stock | m9g.4xlarge | 1 | 43.3 | 0.56 |
| mongo | arm-tuned | m9g.4xlarge | 1 | 42.6 | 0.56 |
| mongo | x86-stock | m8i.4xlarge | 1 | 44.0 | 0.62 |
| mongo | x86-tuned | m8i.4xlarge | 1 | 43.8 | 0.62 |
| postgres | amd-stock | m8a.4xlarge | 1 | 40.2 | 0.65 |
| postgres | amd-tuned | m8a.4xlarge | 1 | 41.1 | 0.67 |
| postgres | arm-stock | m9g.4xlarge | 1 | 40.2 | 0.52 |
| postgres | arm-tuned | m9g.4xlarge | 1 | 40.2 | 0.52 |
| postgres | x86-stock | m8i.4xlarge | 1 | 40.6 | 0.57 |
| postgres | x86-tuned | m8i.4xlarge | 1 | 41.4 | 0.58 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **39.17** |

estimate_per_day_usd: 80.00 - OK
