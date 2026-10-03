# Ledger 2026-09-26-task7-d2

| workload | cell | instancia | nodos | minutos | USD |
|---|---|---|---|---|---|
| inference | amd-stock | m8a.4xlarge | 1 | 28.1 | 0.46 |
| inference | amd-tuned | m8a.4xlarge | 1 | 27.5 | 0.45 |
| inference | arm-stock | m9g.4xlarge | 1 | 26.3 | 0.34 |
| inference | arm-tuned | m9g.4xlarge | 1 | 28.3 | 0.37 |
| inference | x86-stock | m8i.4xlarge | 1 | 32.9 | 0.46 |
| inference | x86-t8 | m8i.4xlarge | 1 | 27.4 | 0.39 |
| inference | x86-tuned | m8i.4xlarge | 1 | 28.4 | 0.40 |
| mongo | amd-stock | m8a.4xlarge | 1 | 43.3 | 0.70 |
| mongo | amd-tuned | m8a.4xlarge | 1 | 45.0 | 0.73 |
| mongo | arm-stock | m9g.4xlarge | 1 | 43.0 | 0.56 |
| mongo | arm-tuned | m9g.4xlarge | 1 | 43.2 | 0.56 |
| mongo | x86-stock | m8i.4xlarge | 1 | 44.7 | 0.63 |
| mongo | x86-tuned | m8i.4xlarge | 1 | 43.8 | 0.62 |
| mongo | arm-stock | m9g.4xlarge | 1 | 57.2 | 0.75 |
| mongo | arm-tuned | m9g.4xlarge | 1 | 4.8 | 0.06 |
| net | amd-stock | m8a.4xlarge | 2 | 14.0 | 0.45 |
| net | amd-tuned | m8a.4xlarge | 2 | 15.1 | 0.49 |
| net | arm-stock | m9g.4xlarge | 2 | 13.6 | 0.35 |
| net | arm-tuned | m9g.4xlarge | 2 | 14.8 | 0.39 |
| net | x86-stock | m8i.4xlarge | 2 | 14.1 | 0.40 |
| net | x86-tuned | m8i.4xlarge | 2 | 15.0 | 0.42 |
| postgres | amd-stock | m8a.4xlarge | 1 | 40.2 | 0.65 |
| postgres | amd-tuned | m8a.4xlarge | 1 | 41.2 | 0.67 |
| postgres | arm-stock | m9g.4xlarge | 1 | 40.0 | 0.52 |
| postgres | arm-tuned | m9g.4xlarge | 1 | 40.5 | 0.53 |
| postgres | x86-stock | m8i.4xlarge | 1 | 41.4 | 0.58 |
| postgres | x86-tuned | m8i.4xlarge | 1 | 41.1 | 0.58 |
| postgres | arm-stock | m9g.4xlarge | 1 | 40.7 | 0.53 |
| postgres | arm-tuned | m9g.4xlarge | 1 | 40.4 | 0.53 |
| (fijo) | loader + tools + control plane | c8i.16xlarge, m7g.large, eks-control-plane | 1 | 360.0 | 19.08 |
| **total** | | | | | **33.66** |

estimate_per_day_usd: 80.00 - OK
