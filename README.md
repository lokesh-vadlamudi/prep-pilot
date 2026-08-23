# PrepPilot

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-SQLModel-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Vite%20%2B%20TS-61DAFB?logo=react&logoColor=black)
![LLM](https://img.shields.io/badge/LLM-local%20ollama-FFA94D)
![Self-hosted](https://img.shields.io/badge/self--hosted-Tailscale-555)

An adaptive interview-prep cockpit that turns daily learning evidence into an
explainable **Learn Next** plan. It combines spaced repetition, NeetCode 150,
mock interviews, a structured roadmap, and a local **DGX** tutor
(`qwen3.8-27b`) in one self-hosted workflow.

<p align="center">
  <img src="docs/preflight.jpg" alt="Daily pre-flight dashboard" width="49%">
  <img src="docs/problems.jpg" alt="NeetCode 150 coding problems" width="49%">
</p>

## What it does
- **Daily pre-flight** — one prioritized session combining due reviews, new concepts, and coding practice.
- **Adaptive "Learn Next"** — adjusts new-topic load from recent recall and due reviews, explains the choice, and previews what comes next.
- **SM-2 spaced repetition** — everything you learn is scheduled for review so it sticks.
- **DGX diagnosis** — on demand, the local model interprets recent mistakes, names a teaching focus, and asks a targeted retrieval question without controlling the scheduler.
- **Interview practice** — NeetCode 150 tracking, progressive hints, executable solutions, and coding/system-design/behavioral mocks.
- **Level-aware coaching** — separate new-grad and senior curricula, examples, and grading expectations.
- **Two graders** — MCQs graded instantly; free-text and whiteboard answers graded by the DGX brain.
- **Self-updating** — a nightly job authors fresh, stack-relevant concepts (Go / Python / TS / React / cloud / Terraform). Also on demand from the Syllabus page.
- **Ask the tutor** — free-form Q&A and system-design coaching.
- **Flight log** — accuracy, per-track mastery, 14-day activity.
- **Job search tracker** — manually log applications, set a daily target, manage the pipeline, and surface due follow-ups without scraping job boards.
- **Multi-user accounts** — invite-code registration with isolated progress, settings, reviews, and problem status.

## Architecture
```
Browser ──HTTPS (Tailscale Serve :10000)──▶ Mac mini
                                             └─ FastAPI + SQLite (uvicorn :8778, LaunchAgent)
                                                   └─ HTTP ──▶ DGX vLLM (qwen3.8-27b) @ $OLLAMA_URL
```
- **Backend:** FastAPI + SQLModel/SQLite, Python 3.12 via `uv`. `backend/app/`
- **Frontend:** React + Vite + TS, built to `frontend/dist`, served by FastAPI.
- **Brain:** `think=False` ollama chat calls (the model routes to hidden reasoning otherwise).

## Local development
```bash
# backend (terminal 1)
cd backend && uv sync && uv run uvicorn app.main:app --port 8899 --reload
# frontend (terminal 2) — proxies /api to :8899
cd frontend && npm install && npm run dev   # http://localhost:5177
```

## Environments

| Environment | Source | URL | Mac mini service | Data |
|---|---|---|---|---|
| Development | committed `main` (or an explicit branch preview) | `https://<mini>.<tailnet>.ts.net:10004` | `com.preppilot.dev` on `127.0.0.1:8779` | isolated `~/prep-pilot-dev/backend/data/prep.db` |
| Production | exact `vMAJOR.MINOR.PATCH` tag | `https://<mini>.<tailnet>.ts.net:10000` | `com.preppilot.server` on `127.0.0.1:8778` | live `~/prep-pilot/backend/data/prep.db` |

Development also has its own login cookie, secrets, logs, code directory, and
database. Its background content scheduler is disabled so it cannot duplicate
production jobs. A purple banner is always visible in the dev UI.

## Deploy / release workflow

Deploy the latest committed `main` to the isolated dev site:

```bash
bash deploy/deploy-dev.sh
```

For a temporary feature-branch preview, commit the branch first and use:

```bash
PREPPILOT_DEV_ALLOW_BRANCH=1 bash deploy/deploy-dev.sh
```

After verifying dev, merge to `main`, deploy dev once more, then create and
deploy an immutable production release:

```bash
bash deploy/release.sh v0.2.0
```

`release.sh` requires a clean `main` matching `origin/main`, creates and pushes
the annotated tag, and deploys that exact revision. Direct production deploys
are blocked unless `HEAD` is an exact semantic-version tag.

The deploy target is read from `deploy/deploy.env` (untracked) — see `deploy/deploy.env.example`.
The first dev visit prompts for a separate dev account; production credentials
and learner data are intentionally not copied.

## Tuning
`backend/app/config.py` — `new_topics_per_day`, `max_reviews_per_day`,
`daily_generation_hour`, `model`, `ollama_url`. Curated content lives in
`backend/app/content/curriculum.py`; add concepts there and restart to seed them.

## Service management (on the mini)
```bash
launchctl unload/load ~/Library/LaunchAgents/com.preppilot.server.plist
tail -f ~/Library/Logs/preppilot.log
```
