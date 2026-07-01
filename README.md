# SHL Conversational Assessment Recommender

Starter scaffold for the SHL AI Intern take-home assignment. This repo gives you a clean FastAPI shape, exact request/response schemas, basic guardrails, a sample local catalog, and clear extension points for real scraping, retrieval, and ranking.

## Project layout

```text
app/
  api/            # FastAPI routes and dependencies
  core/           # Settings
  models/         # Request and response schemas
  services/       # Catalog loading, guardrails, chat orchestration
  prompts/        # Agent prompt for LangChain
  utils/          # Shared text helpers
data/
  raw/            # Place raw scraped SHL data here
  processed/      # Normalized catalog used by the API
scripts/          # Data preparation utilities
tests/            # API tests
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Deployment

The repo is now deployment-ready for container-based hosting.

Included files:

- `Dockerfile`
- `.dockerignore`
- `APPROACH_DOCUMENT.md`
- `render.yaml`

Run the container locally:

```bash
docker build -t shl-recommender .
docker run --rm -p 8000:8000 --env-file .env shl-recommender
```

Deployment checklist:

1. Ensure `data/processed/shl_catalog.json` exists
2. Ensure `.env` contains the runtime values you want in production
3. Expose `GET /health` and `POST /chat`
4. Confirm the platform sends traffic to the container `PORT`
5. Submit the public base URL and the approach document

### Render

This repo includes a Render blueprint in `render.yaml`.

Deploy steps:

1. Push the repo to GitHub
2. In Render, create a new Blueprint deployment
3. Point it at the repo
4. Set the secret `DEEPSEEK_API_KEY` in Render
5. Deploy and verify:
   - `/health`
   - `/chat`

## Build the real SHL catalog

The repo includes a `requests + BeautifulSoup` crawler at `scraper.py`. It starts from the SHL assessments section, crawls assessment-related pages, stores raw HTML under `data/raw/shl_pages/`, and writes a normalized catalog JSON to `data/processed/shl_catalog.json`.

Run it with:

```bash
python scraper.py
```

Useful options:

```bash
python scraper.py --max-pages 40
python scraper.py --delay 0.2
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Chat request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I am hiring a mid-level Java developer who works with stakeholders"}
    ]
  }'
```

## What is already implemented

- Exact `/health` and `/chat` API contract from the brief
- Stateless conversation handling from full message history
- Basic scope guardrails for off-topic, legal, and prompt-injection attempts
- Clarification behavior for vague requests
- Sample comparison behavior for assessments in the local catalog
- Lightweight keyword-based retrieval over the local catalog
- Optional LangChain agent boilerplate using `create_agent` plus catalog tools

## What you should replace next

1. Scrape the full SHL Individual Test Solutions catalog into `data/raw/`.
2. Normalize it into the JSON shape expected by `scripts/build_catalog.py`.
3. Improve retrieval and ranking if you need stronger matching later.
4. Add evaluation against the provided conversation traces.
5. Deploy the API publicly and submit `APPROACH_DOCUMENT.md`

## Sample catalog note

`data/processed/shl_catalog.sample.json` is only there to make the scaffold runnable. It is not a substitute for the full SHL catalog required by the assignment.

## LangChain note

The app keeps the response schema deterministic for the evaluator, but it can also use a LangChain agent for the natural-language reply if `langchain` and `langchain-openai` are installed.

Supported env patterns:

```bash
# DeepSeek via OpenAI-compatible API
SHL_AGENT_MODEL=deepseek:deepseek-v4-flash
DEEPSEEK_API_KEY=your-deepseek-api-key

# OpenAI
SHL_AGENT_MODEL=openai:gpt-5.5
OPENAI_API_KEY=your-openai-api-key
```

If the LangChain model is not configured or the API key is missing, the app falls back to the local heuristic reply builder. The catalog service itself is cached through FastAPI dependencies, so the JSON catalog is loaded once and reused without adding a vector database.
