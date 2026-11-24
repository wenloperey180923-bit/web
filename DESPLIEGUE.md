# Subir a GitHub, Aiven y Render

Se publica la versión **Python (Flask)**. En tu computadora sigue usando
SQLite (`instance/awos.sqlite3`); en Render usa **PostgreSQL de Aiven** (plan
gratis) en cuanto existe la variable `DATABASE_URL`. Las tablas se crean solas.

> Aiven ya no permite crear MySQL gratis (desde el 6 de noviembre de 2026);
> por eso se usa PostgreSQL. El código también acepta `mysql://` por si algún
> día usas un MySQL de pago.

## 1. GitHub (repositorio nuevo)

1. En GitHub: **New repository** → ponle nombre → **sin** README ni .gitignore.
2. En la carpeta del proyecto:

```bash
git init
git add .
git commit -m "Prácticas de servicios web: Flask + PostgreSQL"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

`instance/*.sqlite3`, `.venv/` y `.env` están en `.gitignore`: no se suben.

## 2. Aiven (PostgreSQL gratis)

1. <https://console.aiven.io> → **Create service** → **PostgreSQL** → plan **Free**.
2. Espera a que diga **Running**.
3. En **Overview → Connection information** copia el **Service URI**:
   `postgres://avnadmin:CONTRASEÑA@pg-xxxx.aivencloud.com:12345/defaultdb?sslmode=require`

## 3. Render

1. <https://dashboard.render.com> → **New → Web Service** → conecta el repo nuevo.
2. **Language: Docker** (detecta el `Dockerfile`). Plan **Free**.
3. **Environment Variables**:

   | Variable       | Valor                              |
   |----------------|------------------------------------|
   | `DATABASE_URL` | el Service URI de Aiven            |
   | `SECRET_KEY`   | cualquier texto largo y aleatorio  |

4. **Deploy**. Al terminar abre la URL `https://….onrender.com`.

Con **New → Blueprint** Render lee `render.yaml`, genera `SECRET_KEY` solo y
pide `DATABASE_URL`.

## Notas

- Plan Free de Render: el sitio "se duerme" tras 15 min sin visitas; la primera
  carga después tarda ~50 s.
- Sin `DATABASE_URL`, Render usaría SQLite y los datos se borrarían en cada
  despliegue o reinicio. Por eso va Aiven.
- `ADMIN_P9_PASSWORD_HASH` (opcional) cambia la contraseña `admin` del panel p9.
