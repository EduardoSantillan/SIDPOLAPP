# SIDPOL: frontend

Las pantallas de la plataforma. React con TypeScript y Vite, React Router para las rutas y TanStack Query para pedir los datos. Los tipos se generan desde el `/openapi.json` de la API, así que si el backend cambia algo, el compilador avisa.

La idea que mandó en todo el diseño: una persona que abre la aplicación por primera vez tiene que entender qué ve, qué significa y qué puede hacer, sin glosario ni guía. Si una pantalla necesita un manual, hay que rehacerla.

## Pantallas

| Ruta | Quién la ve | Qué responde |
|---|---|---|
| `/login`, `/activar?token=` | todos | entrar, o elegir contraseña con el enlace que da el administrador |
| `/` | todos | ¿de qué distrito quieres saber? |
| `/distrito/:ubigeo?delito=&periodo=` | todos | cuántas denuncias hubo y qué tanto se parecía lo estimado |
| `/distritos?delito=` | todos | los 43 distritos juntos, en orden alfabético, para marcar y comparar |
| `/ficha?seccion=` | todos | cómo se calculó, en palabras sencillas |
| `/comparar`, `/ejecuciones` | Analista | los modelos lado a lado (sin declarar ganador); iniciar un cálculo y seguirlo |
| `/versiones`, `/usuarios` | Administrador | registrar y revisar los datos; crear cuentas |

Las direcciones se pueden compartir y el botón Atrás funciona. La sesión vive solo en memoria, así que si recargas la página hay que volver a entrar.

## Lenguaje

En las pantallas del Usuario no aparecen nombres técnicos. Se habla de «Modelo por distrito», «Modelo con todo Lima», «Repetir el mes anterior», «Repetir el mismo mes del año pasado» y «antes / desde nov 2024». El MASE sale junto al error en denuncias y siempre con su explicación, que viene de la API para que sea la misma en todos lados. Las huellas SHA-256, las versiones y la configuración solo se ven como Analista o Administrador. Hay una prueba (`pantallas.test.tsx`) que revisa que la pantalla del Usuario no tenga jerga ni etiquetas de riesgo.

## Comandos

```
npm install
npm run dev               # http://localhost:5173; /api se reenvía a la API (variable API_URL, por defecto http://localhost:8000)
npm run tipos:desde-api   # baja los tipos de la API de desarrollo a src/api/esquema.d.ts
npm run tipos             # los regenera desde la copia guardada en src/api/openapi.json
npm test                  # Vitest y Testing Library
npm run build             # revisa los tipos y deja el resultado en dist/
```

Para trabajar con la API: `cd ../BackEnd && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`. Si cambia un modelo de respuesta del backend (`BackEnd/api_plataforma/schemas.py`), baja el `openapi.json` nuevo y corre `npm run tipos`; si el frontend se quedó atrás, `npm run build` falla.

## Producción

Se compila con `npm run build` y la carpeta `dist/` se monta en Nginx con `FRONT_DIST=../FrontEnd/dist` (los detalles están en `../BackEnd/README.md`). Nginx sirve las pantallas en `/` y la API en `/api/`. No hay datos de ejemplo ni modo demo: si no hay resultados, la pantalla lo dice.
