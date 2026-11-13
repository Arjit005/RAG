# RAG Intelligence — Render Deployment Guide

## Required Environment Variables (Add on Render Dashboard)

| Variable | Description | Where to Get |
|----------|-------------|--------------|
| `DATABASE_URL` | Neon PostgreSQL | Neon Dashboard → Connection String |
| `JWT_SECRET_KEY` | Random secret (min 32 chars) | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `QDRANT_URL` | Qdrant Cloud cluster URL | Qdrant Dashboard → Cluster → REST API Endpoint |
| `QDRANT_API_KEY` | Qdrant API Key | Qdrant Dashboard → API Keys |
| `GROQ_API_KEY` | Groq LLM API | console.groq.com |
| `GEMINI_API_KEY` | Google Gemini | aistudio.google.com |
| `OPENROUTER_API_KEY` | OpenRouter | openrouter.ai |
| `ENV` | Set to `production` | (literal value) |

## After Setting Env Vars

1. Trigger a new deploy on Render
2. Run stuck job reset if needed:
   - Open Render Shell → `python scripts/reset_stuck_jobs.py`
3. Re-upload your documents

## Resetting Stuck Documents

SSH into Render shell and run:
```bash
python scripts/reset_stuck_jobs.py
```

## Demo Credentials
- Email: `admin@enterprise.internal`
- Password: `EnterpriseAdmin2026!`
