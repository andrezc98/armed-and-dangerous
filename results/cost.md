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
| m8i.4xlarge | TODO | TODO |
| m9g.4xlarge | TODO | TODO |
| c7i.4xlarge | TODO | TODO |
| m7g.large | TODO | TODO |
| eks-control-plane | TODO | TODO |

- estimate_per_day_usd: TODO
- fixed_hours_per_day: TODO

`estimate_per_day_usd` es el presupuesto del día declarado ANTES de encender
nada (el plan dice ~$8 para el smoke gate). Si el ledger lo supera, marca
`OVER_ESTIMATE`: no es un error del runner, es la señal de parar y mirar qué
celda quedó encendida.

`fixed_hours_per_day` son las horas que el clúster estuvo vivo de punta a punta
(del `terraform apply` al `terraform destroy`). Es lo que se le cobra al loader,
al nodo de tools y al control plane, que nunca bajan a cero mientras el clúster
existe. Las celdas SUT no entran acá: cada una se cobra por los minutos que su
node group estuvo sobre `desired=0`, y eso lo registra el runner en
`results/<fecha>/<workload>/<celda>/cell.json`.
