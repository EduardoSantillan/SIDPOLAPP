# SIDPOLAPP

Plataforma web para consultar y evaluar el pronóstico mensual de denuncias registradas de robo y hurto en los 43 distritos de Lima. Los datos vienen de SIDPOL y van de enero de 2018 a julio de 2026. Es nuestro proyecto de Taller de Proyecto en la UPC (Ingeniería de Sistemas de Información), con Christian Cipriano como asesor.

Autores: Eduardo Santillán Taboada y Miguel Barzola Dolmos.

## De qué trata

Uno elige un distrito y un delito (robo o hurto) y ve cuántas denuncias se registraron cada mes, junto a lo que el modelo había estimado para ese mismo mes y cuánto se equivocó. Cada estimación se hizo solo con los datos de los meses anteriores, desde enero de 2023 hasta julio de 2026.

Comparamos cuatro maneras de estimar: un modelo para cada distrito, un solo modelo con todo Lima, repetir el mes anterior y repetir el mismo mes del año pasado. Los dos primeros usan XGBoost. La plataforma no declara cuál es mejor; muestra los números y deja que cada quien saque su conclusión.

Algo que se repite en toda la aplicación: son denuncias registradas, no la cantidad real de delitos ni el riesgo de un distrito.

Lo que más cuidamos al diseñar las pantallas fue que cualquier persona las entienda a la primera, sin glosario ni explicación aparte.

## Qué datos lee

Lee un archivo CSV de SIDPOL con las denuncias registradas. Cada fila dice cuántas denuncias de un tipo se registraron en un distrito durante un mes, y trae estas columnas: `ANIO`, `MES`, `DPTO_HECHO_NEW`, `PROV_HECHO`, `DIST_HECHO`, `UBIGEO_HECHO`, `P_MODALIDADES` y `cantidad`. De todo el archivo usa solo Lima Metropolitana (los 43 distritos, códigos `150101` a `150143`) y solo las modalidades Robo y Hurto; el resto se ignora. Con eso arma una serie mensual de denuncias por cada distrito y cada delito, 86 series en total.

El archivo lo sube el administrador desde la pantalla de versiones de datos, indicando cuál es el último mes que cubre (el periodo de corte). Antes de usarlo, la plataforma le calcula su huella SHA-256 y lo revisa:

- que tenga todas las columnas y que los números sean números;
- que no falte ningún mes, que empiece en enero de 2018 y que termine en el mes de corte indicado;
- que los conteos sean enteros positivos y que no haya filas repetidas para un mismo mes, distrito y delito;
- que estén los 43 distritos y que haya registros de robo y de hurto;
- que todos los códigos de distrito sean conocidos.

Si algo de eso falla, la versión queda como no válida y no se puede calcular con ella. Si solo hay códigos de distrito que no reconoce, queda con distritos por resolver, hasta que el administrador diga a qué distrito corresponde cada uno. Solo una versión que pasó todas las revisiones sirve para calcular.

Si un distrito no tiene ninguna denuncia de robo o de hurto en un mes, ese mes se toma como cero y queda anotado como valor reconstruido. Un archivo ya registrado no se edita ni se borra: si tenía un error, se registra una versión nueva.

El archivo que usa el entorno de prueba está en `BackEnd/tests/fixtures/sidpol_lima.csv` (enero de 2018 a julio de 2026, 26.527 filas).

## Qué hay en esta carpeta

- `BackEnd/`: la API y los servicios que revisan los archivos de datos y calculan los pronósticos (Python con FastAPI y PostgreSQL). Incluye Docker, Nginx y los respaldos. Tiene su propio README.
- `FrontEnd/`: las pantallas (React con TypeScript). También tiene su propio README.

## Quién puede hacer qué

Hay tres tipos de cuenta:

- **Usuario:** elige un distrito, mira cuántas denuncias hubo y qué estimaba el modelo, ve los 43 distritos juntos, lee cómo se calculó todo y descarga los datos en CSV o PDF.
- **Analista:** hace lo mismo y además inicia los cálculos, sigue su avance y compara los modelos, con el detalle de dónde sale cada valor.
- **Administrador:** registra y revisa los archivos de datos, resuelve los códigos de distrito que no se reconocen y crea las cuentas.

Los permisos se validan en el servidor, no solo en la pantalla.

## Cómo probarlo en tu computadora

Necesitas Docker Desktop abierto, Node y una terminal con `sh` (Git Bash en Windows).

1. En `BackEnd/`, copia `.env.example` como `.env` y cambia las claves por valores aleatorios. En ese mismo archivo está el comando para generarlas.
2. Desde esta carpeta corre `sh BackEnd/scripts/preparar_prueba.sh`. Arma un entorno aparte con datos reales, tres cuentas de prueba y los cálculos de robo y hurto ya hechos. La primera vez tarda unos minutos.
3. Entra a `FrontEnd/`, corre `npm install` y luego `npm run dev`. Abre http://localhost:5173.

Las cuentas son `usuario@prueba.pe`, `analista@prueba.pe` y `admin@prueba.pe`, las tres con la contraseña `clave-de-prueba-123`.

Cuando termines, `sh BackEnd/scripts/preparar_prueba.sh borrar` elimina ese entorno.

Para montarlo en un servidor de verdad (HTTPS, respaldos, sin cuentas de prueba) está explicado en `BackEnd/README.md`.

## Pruebas

- Frontend: `npm test` dentro de `FrontEnd/` (22 pruebas).
- Backend: 211 pruebas. Necesitan una PostgreSQL de prueba; los comandos están en `BackEnd/README.md`.

## Lo que falta

- Aprobar la configuración del experimento en el entorno real. Eso lo tenemos que decidir con el asesor, y mientras no se apruebe la plataforma se niega a calcular. En el entorno de prueba la aprobamos solo para poder mostrarla.
- Decidir dónde se aloja el servidor (dominio y certificado HTTPS) y a dónde se copian los respaldos fuera de la máquina.
- Probar las pantallas con personas que no conozcan el proyecto.
- Las estimaciones llegan hasta julio de 2026, el último mes con dato. Todavía no hay una estimación para un mes que aún no tiene dato registrado.
