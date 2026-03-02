# NexusAPI

NexusAPI is a multi-tenant, credit-gated backend API built with FastAPI, async SQLAlchemy, PostgreSQL, Redis, ARQ, and JWT authentication.

## Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

## Run Locally (Exact Commands)

Use these exact commands.

### 1) Start services in WSL (Ubuntu terminal)

```bash
sudo service postgresql start
sudo service postgresql status
sudo service redis-server start
redis-cli ping
```

### 2) Setup project in PowerShell

```powershell
cd C:\Users\laptop\OneDrive\Desktop\Backend\nexusapi
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install fastapi "uvicorn[standard]" sqlalchemy asyncpg psycopg2-binary alembic "python-jose[cryptography]" authlib pydantic redis arq structlog python-dotenv email-validator itsdangerous httpx
```

### 3) Run migrations in PowerShell

```powershell
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/nexusapi"
alembic upgrade head
```

### 4) Start API (PowerShell Terminal 1)

```powershell
cd C:\Users\laptop\OneDrive\Desktop\Backend\nexusapi
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/nexusapi"
$env:REDIS_URL="redis://localhost:6379/0"
python -m uvicorn app.main:app --reload --reload-dir app
```

### 5) Start worker (PowerShell Terminal 2)

```powershell
cd C:\Users\laptop\OneDrive\Desktop\Backend\nexusapi
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/nexusapi"
$env:REDIS_URL="redis://localhost:6379/0"
python -m arq app.worker.WorkerSettings
```

## Environment Variables

`APP_NAME` - API name shown in app metadata.
`ENVIRONMENT` - Environment label (`dev`, `prod`, etc.).
`DEBUG` - Debug mode toggle (`true`/`false`).
`DATABASE_URL` - PostgreSQL connection string used by the app.
`REDIS_URL` - Redis connection string for queue and rate limiting.
`SECRET_KEY` - Signing key for JWT/session security.
`JWT_ALGORITHM` - JWT signing algorithm (for example `HS256`).
`ACCESS_TOKEN_EXPIRE_MINUTES` - JWT expiry in minutes.
`GOOGLE_CLIENT_ID` - Google OAuth client ID.
`GOOGLE_CLIENT_SECRET` - Google OAuth client secret.
`OAUTH_REDIRECT_URI` - OAuth callback URL (`/auth/callback`).
`RATE_LIMIT_PER_MINUTE` - Per-organisation API rate limit.

If PostgreSQL is running inside WSL while API runs on Windows, `localhost` may not work.
In that case set `DATABASE_URL` with your WSL IP (for example `172.x.x.x`).

## Database Migrations

Run latest migrations:

`alembic upgrade head`

Rollback one migration:

`alembic downgrade -1`

## Important Deployment Note

`/api/summarise` is asynchronous and requires an ARQ worker process to be running.
If the API is live but no worker is running, jobs will stay pending and can later fail/timeout.

Current live setup used for this submission:
- API is hosted on Render.
- Redis is Upstash.
- Worker is run as a separate process using the same `DATABASE_URL` and `REDIS_URL`.

Start worker for live setup (local worker processing live queue):

```powershell
cd c:\Users\laptop\OneDrive\Desktop\Backend\nexusapi
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql+asyncpg://<render_db_user>:<render_db_password>@<render_db_host>/<render_db_name>"
$env:REDIS_URL="rediss://default:<upstash_password>@<upstash_host>:6379"
python -m arq app.worker.WorkerSettings
```

## Postman Example Calls

Use `Authorization: Bearer <jwt>` for protected endpoints.

### 1) Check credits balance

Method: `GET`  
URL: `http://localhost:8000/credits/balance`  
Headers: `Authorization: Bearer <jwt>`

### 2) Analyse text

Method: `POST`  
URL: `http://localhost:8000/api/analyse`  
Headers: `Authorization: Bearer <jwt>`, `Content-Type: application/json`  
Body:

```json
{
  "text": "This is a valid sample text for analysis endpoint."
}
```

### 3) Submit summarise job and poll status

Method: `POST`  
URL: `http://localhost:8000/api/summarise`  
Headers: `Authorization: Bearer <jwt>`, `Content-Type: application/json`  
Body:

```json
{
  "text": "This is a valid sample text for async summarisation endpoint."
}
```

Then poll:

Method: `GET`  
URL: `http://localhost:8000/api/jobs/<job_id>`  
Headers: `Authorization: Bearer <jwt>`


