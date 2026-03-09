# GitHub DevOps Scraper

Scrapes GitHub issues → structured RAG entries for the DevOps SDK.
Supports **OpenAI**, **Anthropic**, and **local Ollama** as LLM providers.

---

## Files

```
scraper_config.yaml   ← configure everything here (repos, labels, LLM, thresholds)
config.py             ← reads the yaml, used by all scripts
llm.py                ← single LLM caller (openai / anthropic / ollama)
token_manager.py      ← GitHub token rotation + rate limit handling
github_client.py      ← GitHub REST API wrapper
progress.py           ← crash-safe progress tracker (progress.json)

phase0_list_labels.py ← see all labels in a repo, validate your config
phase1_discover.py    ← find all candidate issue IDs
phase2_enrich.py      ← fetch full issue body, timeline, linked PR
phase3_classify.py    ← rule-based filter + LLM batch classify
phase4_extract.py     ← LLM extraction → final RAG entries (JSONL)
```

---

## Setup

### 1. Install dependencies

```bash
pip install requests pyyaml

# add one of these depending on your LLM provider:
pip install openai        # for openai
pip install anthropic     # for anthropic
# ollama needs no pip package — just install ollama and run it locally
```

### 2. Add GitHub tokens

Create `tokens.txt` — one token per line:
```
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ghp_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

How to create a token:
- GitHub → Settings → Developer Settings → Personal Access Tokens → Classic
- Name: `scraper-1`, scopes: `public_repo` only
- Repeat for each token (5 tokens = 25,000 requests/hour)

### 3. Configure your LLM in `scraper_config.yaml`

**Ollama (local, free):**
```yaml
llm:
  provider: "ollama"
  ollama_base_url: "http://localhost:11434"
  ollama_classification_model: "llama3.1:8b"
  ollama_extraction_model: "llama3.1:8b"
```
Start ollama first: `ollama serve` then `ollama pull llama3.1:8b`

**OpenAI:**
```yaml
llm:
  provider: "openai"
```
```bash
export OPENAI_API_KEY=sk-...
```

**Anthropic:**
```yaml
llm:
  provider: "anthropic"
```
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Run Order

```bash
# Step 0 — verify your label config is correct (optional but recommended)
python phase0_list_labels.py
python phase0_list_labels.py --repo kubernetes/kubernetes   # single repo

# Step 1 — discover candidate issue IDs (~30-60 min)
python phase1_discover.py
python phase1_discover.py --repo kubernetes/kubernetes      # single repo

# Step 2 — fetch full issue, timeline, PR (~3-5 hours, runs unattended)
python phase2_enrich.py

# Step 3 — classify: rules + LLM batch (~1-2 hours)
python phase3_classify.py

# Step 4 — extract to RAG entries (~2-3 hours)
python phase4_extract.py
```

Every script is **safe to restart** — progress is saved to `progress.json` after every 10 issues.
If it crashes, just re-run the same command and it continues where it stopped.

---

## Add or remove a repo

Edit the `repos:` section in `scraper_config.yaml`:

```yaml
repos:
  - owner: hashicorp
    repo: vault
    bug_labels: "bug"
    exclude_labels: [wontfix, invalid, duplicate]
    category: infrastructure
```

Then run `phase0_list_labels.py --repo hashicorp/vault` to confirm the label name is correct before scraping.

---

## Output

Final RAG entries are saved as JSONL files:
```
processed/
  kubernetes_kubernetes/
    closed_entries.jsonl    ← full entries: problem + fix + execution steps
    open_entries.jsonl      ← problem-only entries (no fix yet)
  grafana_grafana/
    closed_entries.jsonl
    ...
```

Each line is one RAG entry ready to import into Qdrant.

---

## Key config options

| Setting | Where | What it does |
|---|---|---|
| `llm.provider` | yaml | Switch between ollama / openai / anthropic |
| `llm.ollama_extraction_model` | yaml | Use larger model for better quality (e.g. `llama3.1:70b`) |
| `llm.min_extraction_confidence` | yaml | Raise to 8-9 for stricter quality, lower to 5 for more entries |
| `discovery.since` | yaml | Only fetch issues after this date |
| `classification.llm_min_confidence` | yaml | LLM confidence threshold for keeping an issue |
| `run_phases.phase2_enrichment` | yaml | Set `false` to skip a phase |
| `tokens.request_delay` | yaml | Increase if hitting secondary rate limits |
