# Tarifas del lab

Este archivo es la única fuente de precios del proyecto. Se completa **a mano el
día del lab**, leyendo la tarifa on-demand vigente para la región que realmente
se usó, y recién entonces corre el ledger: `runner/cost.py` se niega a calcular
mientras alguna celda diga `TODO`. Un precio viejo en un slide de `$/kop` no es
un número aproximado, es un número equivocado.

Dónde leerlos (los dos, el mismo día, y anotar cuál se usó en la columna
`captured`):

```bash
# Precio on-demand por hora, Linux, sin tenancy dedicada
aws pricing get-products --region us-east-1 --service-code AmazonEC2 \
  --filters Type=TERM_MATCH,Field=instanceType,Value=m9g.4xlarge \
            Type=TERM_MATCH,Field=location,Value='US East (N. Virginia)' \
            Type=TERM_MATCH,Field=operatingSystem,Value=Linux \
            Type=TERM_MATCH,Field=preInstalledSw,Value=NA \
            Type=TERM_MATCH,Field=tenancy,Value=Shared \
            Type=TERM_MATCH,Field=capacitystatus,Value=Used
# o, más rápido de leer: https://aws.amazon.com/ec2/pricing/on-demand/
```

`eks-control-plane` es la hora de clúster de EKS
(https://aws.amazon.com/eks/pricing/), que se factura desde el `apply` hasta el
`destroy` igual que el loader y el nodo de tools.

| instance | usd_per_hour | captured (date, source) |
|---|---|---|
| m8i.4xlarge | 0.84672 | 2026-09-04, aws pricing get-products (us-east-1, Linux, Shared, Used) |
| m9g.4xlarge | 0.78272 | 2026-09-04, aws pricing get-products (us-east-1, Linux, Shared, Used) |
| c7i.4xlarge | 0.714 | 2026-09-04, aws pricing get-products (us-east-1, Linux, Shared, Used) |
| m7g.large | 0.0816 | 2026-09-04, aws pricing get-products (us-east-1, Linux, Shared, Used) |
| eks-control-plane | 0.10 | 2026-09-04, https://aws.amazon.com/eks/pricing/ (standard support, por clúster-hora) |

- estimate_per_day_usd: 80
- fixed_hours_per_day: 6

`estimate_per_day_usd` es el presupuesto del día declarado ANTES de encender
nada. Está en 80 desde el 2026-09-04, cuando el speaker relajó el techo de $200
del proyecto; el plan estimaba ~$8 para el día del smoke gate, así que un día
normal queda holgado y el número sigue siendo un freno real para un día de
corrida completa. Si el ledger lo supera, marca `OVER_ESTIMATE`: no es un error
del runner, es la señal de parar y mirar qué celda quedó encendida.

Ese número además **frena**: antes de subir cualquier node group el runner suma
lo que el día ya lleva comprometido (las `cell.json` escritas más la línea fija) y
se niega a arrancar otra celda si eso ya pasó `estimate_per_day_usd`, salvo que se
pase `--override-budget` a propósito. Una tarifa en `TODO` frena igual: sin
precios no hay guard, y sin guard el presupuesto es una nota al pie.

`fixed_hours_per_day` son las horas que el clúster estuvo vivo de punta a punta
(del `terraform apply` al `terraform destroy`). Es lo que se le cobra al loader,
al nodo de tools y al control plane, que nunca bajan a cero mientras el clúster
existe. Las celdas SUT no entran aquí: cada una se cobra por los minutos que su
node group estuvo sobre `desired=0`, y eso lo registra el runner en
`results/<fecha>/<workload>/<celda>/cell.json`.
