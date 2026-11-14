# AI Powered Retail Connect (Objectives O1 & O2)

Agentic AI-Powered Hyperlocal Commerce Platform connecting customers with verified Kirana stores.

> **Current Phase:** Stage 1 — Project Foundation (Frontend PWA, Express + SQLite Local Preview Runtime, FastAPI + SQLAlchemy 2 + Alembic Backend, Vision Service Boundary, 18-Table PostgreSQL/Supabase Schema, Deterministic Synthetic Seeder `SEED=42`).

## Architecture Overview

- **Frontend PWA (`src/`, `apps/web/`)**: React 19, TypeScript, Vite, Tailwind CSS v4, React Router, TanStack Query, Recharts, `react-i18next` (`en`, `hi`, `kn`), and `vite-plugin-pwa`.
- **Integrated Preview Server (`server.ts`)**: Express + Node 22 `node:sqlite` + Vite middleware on port `3000`, plus server-side `@google/genai` (`gemini-4-hydrogen`) with deterministic fallback.
- **Python Backend (`services/api/`)**: FastAPI, Pydantic v2, SQLAlchemy 2, Alembic migrations targeting Supabase PostgreSQL (`pgvector`, `pg_trgm`, `PostGIS`).
- **Computer Vision Service (`services/vision/`)**: Separate FastAPI boundary reserved for RT-DETR, YOLO11 baseline, DINOv2/CLIP embeddings, and EasyOCR (Stage 3).
- **ML Workspace (`ml/`)**: Reserved for demand forecasting (Seasonal Naive, Moving Average, Croston/TSB, LightGBM) and Smart Pricing (elasticity, expiry markdown, competition, stock pressure) in Stages 4–5.

## Windows PowerShell Commands

### Option A: Integrated Full-Stack Runtime (Node 22+ & Python 3.10+)
```powershell
Copy-Item .env.example .env
npm install
python database\seed\generate_synthetic_data.py
npm run dev
```
Open: `http://localhost:3000`

### Option B: Docker Compose (PostgreSQL pgvector + FastAPI + Vision + Web)
```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
```
- Frontend: `http://localhost:3000`
- FastAPI Backend: `http://localhost:8000/docs`
- Vision Service: `http://localhost:8001/docs`

### Option C: Local Python FastAPI & Vision Virtual Environments (Windows PowerShell)
```powershell
python -m venv .venv-api
.\.venv-api\Scripts\Activate.ps1
pip install -r services\api\requirements.txt
cd services\api
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Linux / macOS Commands

```bash
cp .env.example .env
npm install
python3 database/seed/generate_synthetic_data.py
npm run dev
```

## Verification & Tests

```bash
npm run lint
npm run build
npm test
```
