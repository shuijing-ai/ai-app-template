<div align="center">

# ai-app-template

**One command to forge a production-ready AI app skeleton**

Model gateway · Fallback chains · Cost-aware routing · Observability · Automated evaluation

[![CI](https://github.com/shuijing-ai/ai-app-template/actions/workflows/ci.yml/badge.svg)](https://github.com/shuijing-ai/ai-app-template/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)

[简体中文](README.md) | **English**

</div>

---

## Why

Most AI app templates are static repos you `git clone` and then hand-edit forever.
**ai-app-template is an interactive CLI scaffold**: one command generates a project
that is already production-shaped — and every generated module ships with
Chinese tutorials explaining the engineering trade-offs.

- **A real CLI, not a repo to clone** — project name, template variant and config are handled for you
- **Full capability combo** — cost-aware routing + fallback chains + structured-output conventions + automated evaluation, all baked in
- **Offline green tests** — the generated project passes `pytest -q` with **zero API keys**; fake gateways and scripted clients are part of the template
- **Teaching-oriented** — eight in-depth tutorials (in Chinese) covering every design decision, ideal for interviews and courses

## Quick start

```bash
git clone https://github.com/shuijing-ai/ai-app-template.git
cd ai-app-template
pip install -e .        # a PyPI package (pip install ai-app-template) is on the roadmap

ai-app-template list                              # list built-in templates
ai-app-template create my-app                    # interactive
ai-app-template create my-app -t rag-agent --yes # non-interactive (scripts/CI)
```

Inside the generated project:

```bash
cd my-app
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env       # add your API key
pytest -q                  # all green, offline, costs nothing
uvicorn app.main:app --reload
python -m app.eval.run_eval --mock   # offline eval smoke run
```

## Built-in templates

| Template | Graph | Best for |
| --- | --- | --- |
| `review-flow` (default) | `parse -> extract ->(retry) review -> summary` | Getting started; document review apps |
| `rag-agent` | `retrieve -> generate(citations) -> verify` | Knowledge-base Q&A with deterministic citation checks |
| `multi-agent` | `supervisor -> researcher/writer/critic loop` | Supervisor-pattern agent teams with a round budget |
| `voice-flow` | `ingest -> summarize -> extract_todos -> finalize` | Meeting transcripts to summaries/topics/deduped todos; ASR stays external |

## What's inside every generated project

| Capability | Implementation | In one line |
| --- | --- | --- |
| Model gateway | `app/llm/gateway.py`: exponential backoff, per-model circuit breaker, cross-provider fallback chains | Single entry point for every LLM call |
| Cost-aware routing | `app/llm/router.py`: task/length/structure -> light/standard/heavy, with explainable reasons | Don't burn a frontier model on trivial tasks |
| Structured output | `app/schema/wrappers.py`: the `XxxSet` convention + strict `json_schema` | The model side guarantees valid JSON |
| Safe unwrapping | `app/utils/extractor.py`: fences/noise/renamed keys/bare lists, never raises | Whatever the model returns, you get a list |
| Observability | `GatewayStats` + optional LangFuse via client-class substitution (zero code intrusion) | Tokens, cost and latency always accounted for |
| Automated evaluation | `app/eval/`: dataset + one-command scoring + CI gate via exit code | Quality is regression-tested, not vibes |
| Graceful degradation | Every node has a fallback path; the workflow survives a full LLM outage | LLM-enhanced, not LLM-dependent |
| Containers | Dockerfile + docker-compose (optional self-hosted LangFuse stack) | One command to run dependencies |

## Documentation

The tutorials are currently written in Chinese (English translations are on the roadmap — PRs welcome):

- [Architecture & ADRs](docs/architecture.md) — overall design and 10 architecture decision records
- [Design review](docs/design-review.md) — how the original 6-week plan was reviewed and improved
- [Tutorials](docs/tutorials/) — eight deep-dives: CLI internals, model gateway, LangGraph workflows, structured output, observability & evaluation, and an interview-prep guide
- [Publishing guide](docs/publishing.md) — shipping to GitHub / PyPI and content platforms

## Developing this repo

```bash
pip install -e ".[dev]"
pytest -q          # repo tests (generation/rendering/compile checks for all templates)
ruff check src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the three-step guide to adding a new template.

## Roadmap

- [x] `ai-app-template doctor` — environment check (version/git/structure/deps/API keys/ports)
- [x] Fourth template `voice-flow`: transcripts -> summary/topics/deduped todos
- [x] Template marketplace: install third-party templates from any git repo (`-t <git-url>[#subdir]`)
- [ ] Publish to PyPI (`pip install ai-app-template`)
- [ ] English translations of the tutorials

## License

[MIT](LICENSE)
