# apps/java: spring-petclinic-rest sobre JDK 25

Workload Java de alta concurrencia (spec §4). Hechos verificados el
2026-09-03 contra las fuentes indicadas; re-verificar el día del lab.

## Qué se construye

| Elemento | Valor | Fuente |
|---|---|---|
| Código | `spring-petclinic/spring-petclinic-rest` master @ `4cd8e1b0cd42` (2026-09-01) | https://github.com/spring-petclinic/spring-petclinic-rest |
| Versión del proyecto | 4.0.2 (jar `target/spring-petclinic-rest-4.0.2.jar`) | `pom.xml` del commit |
| Spring Boot | **4.1.1** en master; el tag `v4.0.2` aún apunta a Boot 4.0.2, por eso se pinnea el SHA y no el tag | `pom.xml` (`spring-boot-starter-parent`) |
| Java de compilación | `--release 17` (heredado del parent de Boot; el pom no define `java.version`) | `spring-boot-starter-parent-4.1.1.pom` |
| Soporte JDK 25 | Boot 4.1.1 "requires at least Java 17 and is compatible with versions up to and including Java 26" | https://docs.spring.io/spring-boot/4.1/system-requirements.html |
| CI upstream | solo JDK 17 (`java-version: '17'` en los cuatro workflows). Correr en 25 está dentro del rango declarado por Boot, pero el proyecto no lo prueba | `.github/workflows/*.yml` |
| Imagen de build | `maven:3.9.16-eclipse-temurin-25-noble` (amd64 + arm64; el pom exige Maven ≥ 3.9.9) | Docker Hub, tags `2026-08-25` |
| Imagen de runtime | `eclipse-temurin:25.0.4_7-jre-noble` (amd64 + arm64) | Docker Hub, tag `2026-08-22` |
| JDK 25 GA | 2025-09-16 | https://openjdk.org/projects/jdk/25/ |

## Contrato de la app

- Puerto `9966`, context path `/petclinic/`, API en `/petclinic/api`, health en
  `/petclinic/actuator/health` (`application.properties`).
- Perfiles por defecto `h2,spring-data-jpa`: H2 en memoria poblada al arrancar
  (`db/h2/schema.sql` + `data.sql`: 10 owners, 13 pets, 6 vets, 4 visits; ids
  desde 1).
- Endpoints que usa `runner/k6/java.js` (todos de lectura, del `openapi.yml`):
  `GET /petclinic/api/owners`, `GET /petclinic/api/owners/{1..10}`,
  `GET /petclinic/api/pets/{1..13}`, `GET /petclinic/api/vets`,
  `GET /petclinic/api/pettypes`. Sin escrituras: una H2 en memoria que crece
  durante 57 min de celda cambiaría el workload entre corridas (n≥3 deja de ser
  comparable).
- Virtual threads (twist, spec §4): propiedad `spring.threads.virtual.enabled=true`
  (Boot ≥ 3.2; "For the best experience, Java 24 or later is strongly
  recommended"). En el overlay se pasa como env `SPRING_THREADS_VIRTUAL_ENABLED=true`.
  Fuente: https://docs.spring.io/spring-boot/4.1/reference/features/spring-application.html
- Seguridad desactivada por defecto (`petclinic.security.enable=false`).

## Controles fijos en la imagen (iguales en todas las celdas)

- `SPRING_JPA_SHOW_SQL=false`: el perfil h2 trae `show-sql=true`; loguear cada
  sentencia no es el workload.
- `JAVA_TOOL_OPTIONS=""`: heap (`-Xms=-Xmx`), G1 y las flags stock/tuned de
  `java.md` las fija el overlay de cada celda (Task 5), nunca la imagen.

## Fallback (time-box 2 h, spec §4)

Si Boot 4.1.1 no compila o no arranca en JDK 25: `apps/java-min/` (JDK 25
`HttpServer` + Jackson, `POST /api/transform` con JSON de 2 KB). No fue
necesario: ver "Smoke local" abajo.

## Smoke local (2026-09-03, Mac arm64, Docker 29.4)

- `docker build` compila PetClinic (Boot 4.1.1) con Maven 3.9.16 sobre JDK 25 y
  empaqueta el jar en un solo intento; imagen final 405 MB. Fallback `java-min`
  descartado.
- Arranque: `Starting PetClinicApplication v4.0.2 using Java 25.0.4`,
  `Started PetClinicApplication in 3.229 seconds`; health `{"status":"UP"}`.
- Los cinco endpoints del mix devuelven 200 (`/owners` 2.9 KB, `/owners/1`
  233 B, `/pets/1` 99 B, `/vets` 533 B, `/pettypes` 143 B).
- `grafana/k6:2.2.0` `MODE=fixed` 200 rps × 30 s: 6001 requests, 0 % errores,
  p99 4.6 ms. `MODE=knee` (escalera 100→300 rps): una sub-métrica
  `http_req_duration{rate:N}` por escalón con su p(99) y su umbral; exit 99
  cuando el SLO falla (esperado, el runner lo trata como corrida completa).
  Los números de la Mac no son datos del lab: solo prueban el pipeline.
