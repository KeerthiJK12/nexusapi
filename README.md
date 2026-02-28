# NexusAPI

NexusAPI is a multi-tenant, credit-gated backend API built with FastAPI, async SQLAlchemy, PostgreSQL, Redis, ARQ, and JWT authentication.

## Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

## Run Commands

```bash
python -m venv venv
source venv/bin/activate
# Windows: venv\\Scripts\\activate

pip install fastapi uvicorn[standard] sqlalchemy asyncpg psycopg2-binary \
  alembic python-jose[cryptography] authlib pydantic redis arq structlog \
  python-dotenv email-validator

cd nexusapi
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run worker in a separate terminal:

```bash
cd nexusapi
arq app.worker.WorkerSettings
```

## Environment Variables

`APP_NAME`: API name.
`ENVIRONMENT`: Runtime env label.
`DEBUG`: FastAPI debug switch.
`DATABASE_URL`: PostgreSQL DSN.
`REDIS_URL`: Redis DSN for ARQ and rate limits.
`SECRET_KEY`: JWT + session signing key.
`JWT_ALGORITHM`: JWT signing algorithm.
`ACCESS_TOKEN_EXPIRE_MINUTES`: JWT lifetime; default 1440 (24h).
`GOOGLE_CLIENT_ID`: Google OAuth client id.
`GOOGLE_CLIENT_SECRET`: Google OAuth client secret.
`OAUTH_REDIRECT_URI`: Callback URI (`/auth/callback`).
`RATE_LIMIT_PER_MINUTE`: Per-org request limit on product endpoints.

Example `.env`:

```env
APP_NAME=NexusAPI
ENVIRONMENT=dev
DEBUG=false
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nexusapi
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OAUTH_REDIRECT_URI=http://localhost:8000/auth/callback
RATE_LIMIT_PER_MINUTE=60
```

If PostgreSQL is running inside WSL while API runs on Windows, `localhost` may not work.
In that case set `DATABASE_URL` with your WSL IP (for example `172.x.x.x`).

## Alembic Migration Commands

```bash
cd nexusapi
alembic upgrade head
alembic downgrade -1
```

## Local Startup Order

1. Start PostgreSQL and Redis.
2. Run `alembic upgrade head`.
3. Start API server (`uvicorn ...`).
4. Start worker (`arq app.worker.WorkerSettings`).

## cURL Examples

```bash
curl -X GET http://localhost:8000/health

curl -X GET http://localhost:8000/credits/balance \
  -H "Authorization: Bearer <jwt>"

curl -X POST http://localhost:8000/credits/grant \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"amount":100,"reason":"initial funding"}'

curl -X POST http://localhost:8000/api/analyse \
  -H "Authorization: Bearer <jwt>" \
  -H "Idempotency-Key: 90a5e2d8-bca6-467b-b254-6f2e46a81a86" \
  -H "Content-Type: application/json" \
  -d '{"text":"This is a valid sample text for analysis endpoint."}'

curl -X POST http://localhost:8000/api/summarise \
  -H "Authorization: Bearer <jwt>" \
  -H "Idempotency-Key: 453f89c2-b87f-42e7-b59c-470d45ec75f8" \
  -H "Content-Type: application/json" \
  -d '{"text":"This is a valid sample text for async summarisation endpoint."}'

curl -X GET http://localhost:8000/api/jobs/<job_id> \
  -H "Authorization: Bearer <jwt>"
```
