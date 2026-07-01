# SHL Conversational Assessment Recommender

Starter scaffold for the SHL AI Intern take-home assignment. This repo gives you a clean FastAPI shape, exact request/response schemas, basic guardrails, a sample local catalog, and clear extension points for real scraping, retrieval, and ranking.

## Project layout

```text
app/
  api/            # FastAPI routes and dependencies
  core/           # Settings
  models/         # Request and response schemas
  services/       # Catalog loading, guardrails, chat orchestration, LLM agent
  prompts/        # Agent system prompt for LangChain
  utils/          # Shared text normalization and tokenization helpers
data/
  raw/            # Raw scraped SHL HTML pages and crawl manifest
  processed/      # Scraped catalog (shl_catalog.json) + sample catalog
scripts/          # Catalog validation utility
tests/            # API tests (5 tests, all passing)
scraper.py        # BFS crawler that builds the catalog from shl.com
Dockerfile        # Container build instructions for Render
render.yaml       # Render Blueprint for one-click deploy
APPROACH_DOCUMENT.md  # 2-page approach document for submission
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

## What is implemented

- Exact `/health` and `/chat` API contract matching the assignment spec
- Stateless conversation handling from full message history
- All four required conversational behaviors: clarify, recommend, refine, compare
- Scope guardrails: blocks prompt-injection, legal advice, and off-topic queries
- Catalog scraper (`scraper.py`): crawls shl.com and extracts 10 individual assessments
- Weighted heuristic retrieval with domain-intent scoring and diversification
- Optional LangChain agent with catalog-grounded tools (DeepSeek V4 Flash)
- Dockerfile + render.yaml for one-click Render deployment
- 5 automated API tests covering all core behaviors

## What remains

- Evaluation against the 10 public conversation traces (Recall@10 measurement)
- Fine-tuning scraper test_type classification for edge cases

## Catalog

`data/processed/shl_catalog.json` contains 10 scraped SHL assessments with real URLs. `data/processed/shl_catalog.sample.json` is a smaller hand-crafted sample for quick local development.

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
