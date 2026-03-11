# GitHub DevOps Scraper

Scrapes GitHub issues from major DevOps repositories → classifies them via rule-based filters + LLM → extracts structured **RAG entries** (JSONL) for a DevOps incident knowledge base.

Supports **OpenAI**, **Anthropic**, and **local Ollama** as LLM providers.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [GitHub Tokens](#1-github-tokens)
  - [LLM Provider](#2-llm-provider)
  - [Repository Config](#3-repository-config)
  - [Tuning Parameters](#4-tuning-parameters)
- [Running the Pipeline](#running-the-pipeline)
  - [Full Pipeline](#full-pipeline-recommended)
  - [Individual Phases](#individual-phases)
- [Docker Deployment](#docker-deployment)
- [Output Format](#output-format)
- [File Reference](#file-reference)
- [Troubleshooting](#troubleshooting)

---

## Architecture

The scraper runs as a **5-phase pipeline**. Each phase is independently restartable — progress is saved to `progress.json` after every batch. If any phase crashes, re-run the same command and it resumes from where it stopped.

```
Phase 0 ─► Phase 1 ─► Phase 2 ─► Phase 3 ─► Phase 4 ─► JSONL output
labels     discover    enrich     classify    extract     (RAG entries)
(verify)   (issue IDs) (full data) (rules+LLM) (LLM→JSON)
```

| Phase | What it does | API calls | Time estimate |
|---|---|---|---|
| **Phase 0** | Validates that your configured labels exist in each repo | GitHub only | ~1 min |
| **Phase 1** | Discovers all candidate issue numbers matching your filters | GitHub only | 30–60 min |
| **Phase 2** | Fetches full issue body, timeline, and linked PRs | GitHub only | 3–5 hours |
| **Phase 3** | Rule-based filters + LLM batch classification | GitHub + LLM | 1–2 hours |
| **Phase 4** | LLM extraction → structured RAG entries | LLM only | 2–3 hours |

---

## Prerequisites

- **Python 3.10+** (3.12 recommended)
- **GitHub Personal Access Tokens** (at least one; 5 recommended for throughput)
- **LLM provider** — one of:
  - [Ollama](https://ollama.ai/) installed locally (free, no API key)
  - OpenAI API key
  - Anthropic API key
- **Docker** (optional, for containerized deployment)

---

## Installation

### Option A: Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/Abdelhady-22/GitHub-DevOps-Scraper.git
cd GitHub-DevOps-Scraper

# 2. Create a virtual environment (recommended)
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install your LLM provider's package (pick one)
pip install openai        # for OpenAI
pip install anthropic     # for Anthropic
# Ollama needs no pip package — install it from https://ollama.ai
```

### Option B: Docker

```bash
docker compose build
```

See [Docker Deployment](#docker-deployment) for details.

---

## Configuration

All configuration is done in **two places**:

| What | Where |
|---|---|
| Pipeline settings (repos, thresholds, LLM models) | `scraper_config.yaml` |
| Secrets (API keys, tokens) | `.env` file or environment variables |

### 1. GitHub Tokens

You need at least one GitHub Personal Access Token. More tokens = higher throughput (each gives 5,000 API calls/hour).

**How to create a token:**
1. Go to GitHub → Settings → Developer Settings → **Personal Access Tokens** → **Tokens (classic)**
2. Click "Generate new token (classic)"
3. Name: `scraper-1`, Scopes: check `public_repo` only
4. Copy the token
5. Repeat for additional tokens (5 tokens = 25,000 requests/hour)

**Option A — tokens.txt file:**

Create a file called `tokens.txt` in the project directory with one token per line:

```
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
ghp_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
```

**Option B — .env file:**

Copy `.env.example` to `.env` and set your tokens as a comma-separated list:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
GITHUB_TOKENS=ghp_xxx,ghp_yyy,ghp_zzz
```

> **Note:** If both `tokens.txt` and `GITHUB_TOKENS` env var are set, the env var takes priority.

### 2. LLM Provider

Edit the `llm` section in `scraper_config.yaml`:

#### Ollama (local, free — recommended for testing)

```yaml
llm:
  provider: "ollama"
  ollama_base_url: "http://localhost:11434"
  ollama_classification_model: "llama3.1:8b"
  ollama_extraction_model: "llama3.1:8b"
```

Setup:
```bash
# Install Ollama from https://ollama.ai
ollama serve                  # start the server
ollama pull llama3.1:8b       # download the model (~4.7 GB)
```

#### OpenAI

```yaml
llm:
  provider: "openai"
  openai_classification_model: "gpt-4o-mini"
  openai_extraction_model: "gpt-4o"
```

Set your API key in `.env`:
```env
OPENAI_API_KEY=sk-...
```

#### Anthropic

```yaml
llm:
  provider: "anthropic"
  anthropic_classification_model: "claude-haiku-4-5-20251001"
  anthropic_extraction_model: "claude-sonnet-4-6"
```

Set your API key in `.env`:
```env
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Repository Config

The `repos` section in `scraper_config.yaml` defines which GitHub repos to scrape:

```yaml
repos:
  - owner: kubernetes
    repo: kubernetes
    bug_labels: "kind/bug"          # label that marks bug issues
    exclude_labels: [wontfix, invalid, duplicate, kind/feature]
    category: kubernetes            # category tag for RAG entries
```

**To add a new repo:**
1. Add an entry to the `repos` list in `scraper_config.yaml`
2. Run phase 0 to verify the label name is correct:
   ```bash
   python phase0_list_labels.py --repo owner/repo
   ```
3. If the label shows ✗, update `bug_labels` to the correct name

**Default repos:** Kubernetes, Grafana, Prometheus, Helm, Docker Compose, Istio, Redis, Nginx

### 4. Tuning Parameters

| Setting | Location | Default | Purpose |
|---|---|---|---|
| `llm.provider` | yaml | `ollama` | LLM backend: `ollama` / `openai` / `anthropic` |
| `llm.min_extraction_confidence` | yaml | `7` | Minimum confidence score (1-10) for RAG entries |
| `classification.llm_min_confidence` | yaml | `0.70` | LLM confidence threshold for keeping issues |
| `classification.batch_size` | yaml | `20` | Issues per LLM classification batch |
| `discovery.since` | yaml | `2020-01-01` | Only fetch issues created after this date |
| `discovery.min_body_length` | yaml | `150` | Minimum issue body length (chars) to keep |
| `tokens.request_delay` | yaml | `0.25` | Seconds between GitHub API calls |
| `enrichment.checkpoint_every` | yaml | `10` | Save progress every N issues |
| `run_phases.phase*` | yaml | `true` | Set `false` to skip a specific phase |

---

## Running the Pipeline

### Full Pipeline (Recommended)

```bash
# Run all phases in sequence
python run_all.py

# Run for a single repo only
python run_all.py --repo kubernetes/kubernetes

# Skip Phase 0 (label validation)
python run_all.py --skip-phase0

# Run only specific phases
python run_all.py --phases 3 4
```

The orchestrator:
- Runs each phase sequentially
- Stops on the first failure
- Prints a timing summary at the end
- Saves a `run_summary.json` file with full run details

### Individual Phases

You can also run each phase separately:

```bash
# Phase 0 — Validate labels (optional but recommended first time)
python phase0_list_labels.py
python phase0_list_labels.py --repo kubernetes/kubernetes

# Phase 1 — Discover candidate issue IDs
python phase1_discover.py
python phase1_discover.py --repo kubernetes/kubernetes --state closed

# Phase 2 — Fetch full issue data, timelines, PRs
python phase2_enrich.py
python phase2_enrich.py --repo kubernetes/kubernetes --state open

# Phase 3 — Classify: rule-based + LLM batch
python phase3_classify.py
python phase3_classify.py --repo kubernetes/kubernetes

# Phase 4 — Extract structured RAG entries via LLM
python phase4_extract.py
python phase4_extract.py --repo kubernetes/kubernetes
```

> **Safe to restart:** Every script saves progress after each batch. If it crashes, re-run the same command and it continues where it stopped.

---

## Docker Deployment

### Build and Run

```bash
# Build the image
docker compose build

# Run the full pipeline
docker compose up

# Run for a single repo (override command)
docker compose run scraper python run_all.py --repo kubernetes/kubernetes

# Run specific phases
docker compose run scraper python run_all.py --phases 3 4
```

### Volume Mounts

The `docker-compose.yml` mounts these directories:

| Container path | Host path | Purpose |
|---|---|---|
| `/app/tokens.txt` | `./tokens.txt` | GitHub tokens (read-only) |
| `/app/scraper_config.yaml` | `./scraper_config.yaml` | Config (read-only) |
| `/app/raw` | `./raw` | Raw scraped data |
| `/app/staging` | `./staging` | Intermediate classified data |
| `/app/processed` | `./processed` | Final RAG entries |
| `/app/logs` | `./logs` | Application logs |

### Using Ollama with Docker

If using Ollama as the LLM provider inside Docker, update `scraper_config.yaml` to point to your host Ollama:

```yaml
llm:
  provider: "ollama"
  ollama_base_url: "http://host.docker.internal:11434"  # Docker host
```

---

## Output Format

Final RAG entries are saved as JSONL files:

```
processed/
  kubernetes_kubernetes/
    closed_entries.jsonl    ← problem + fix + execution steps
    open_entries.jsonl      ← problem-only (no fix yet)
  grafana_grafana/
    closed_entries.jsonl
    ...
```

Each line is one JSON object. Example **closed entry**:

```json
{
  "source_repo": "kubernetes/kubernetes",
  "source_issue": 12345,
  "source_pr": 12350,
  "source_url": "https://github.com/kubernetes/kubernetes/issues/12345",
  "source_pr_url": "https://github.com/kubernetes/kubernetes/pull/12350",
  "problem_signature": "Kubernetes Pod OOMKilled",
  "problem_description": "Pods are being OOMKilled due to memory limits...",
  "error_indicators": ["OOMKilled", "exit code 137"],
  "root_cause": "Memory limits set too low for the workload",
  "proposed_fix": "Increase memory limits in the pod spec",
  "execution_steps": ["kubectl edit deployment myapp -n default", "increase resources.limits.memory to 512Mi"],
  "fix_type": "config",
  "environment_clues": ["kubernetes"],
  "category": "kubernetes",
  "confidence_in_extraction": 9
}
```

These entries are designed to be imported directly into a vector database like **Qdrant** for RAG queries.

---

## File Reference

### Core Modules
| File | Purpose |
|---|---|
| `config.py` | Loads `scraper_config.yaml`, validates all settings, supports `.env` |
| `llm.py` | Unified LLM caller with retry logic (OpenAI/Anthropic/Ollama) |
| `token_manager.py` | Rotates GitHub tokens, handles rate limits |
| `github_client.py` | GitHub REST API wrapper with pagination |
| `progress.py` | Crash-safe progress tracking via `progress.json` |
| `logger.py` | Centralized structured logging (console + file) |
| `schemas.py` | Pydantic validation models for RAG entries |

### Phase Scripts
| File | Purpose |
|---|---|
| `phase0_list_labels.py` | Validates that configured labels exist in repos |
| `phase1_discover.py` | Finds all candidate issue IDs |
| `phase2_enrich.py` | Fetches full issues, timelines, linked PRs |
| `phase3_classify.py` | Rule-based filtering + LLM batch classification |
| `phase4_extract.py` | LLM extraction → structured RAG entries |

### Deployment
| File | Purpose |
|---|---|
| `run_all.py` | Full pipeline orchestrator |
| `Dockerfile` | Container build definition |
| `docker-compose.yml` | Docker Compose with volume mounts |
| `.env.example` | Template for environment variables |
| `.gitignore` | Git ignore rules for output/secrets |
| `scraper_config.yaml` | All pipeline settings |
| `requirements.txt` | Python dependencies |

---

## Troubleshooting

### "No tokens found" error
- Make sure `tokens.txt` exists with at least one valid token, **OR**
- Set `GITHUB_TOKENS=ghp_xxx` in your `.env` file

### "Config file not found" error
- Make sure `scraper_config.yaml` is in the same directory as the scripts
- If using Docker, ensure the file is mounted correctly

### LLM timeouts with Ollama
- Ensure Ollama is running: `ollama serve`
- Ensure the model is downloaded: `ollama pull llama3.1:8b`
- Check the base URL in config: `ollama_base_url: "http://localhost:11434"`
- For Docker: use `http://host.docker.internal:11434`

### GitHub 429 / rate limit errors
- Add more tokens to increase throughput
- Increase `tokens.request_delay` in config (e.g., `0.5` or `1.0`)
- The scraper auto-handles rate limits: it will sleep and retry

### Pipeline stopped mid-run
- Just re-run the same command — all phases resume from their last checkpoint
- Check `progress.json` to see what was completed
- Check `logs/` for detailed error logs

### Schema validation warnings in Phase 4
- Some LLM responses may not meet the minimum quality threshold
- These entries are skipped and logged — not a critical error
- Lower `min_extraction_confidence` in config to keep more entries (default: 7)
