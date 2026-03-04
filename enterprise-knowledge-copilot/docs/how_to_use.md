# How to Use Enterprise Knowledge Copilot

This guide covers all available interfaces and commands for using the Enterprise Knowledge Copilot system.

---

## Table of Contents
- [Initial Setup](#initial-setup)
- [CLI Usage](#cli-usage)
- [REST API Usage](#rest-api-usage)
- [Web UI Usage](#web-ui-usage)
- [Running Evaluations](#running-evaluations)
- [Monitoring & Metrics](#monitoring--metrics)
- [Configuration Options](#configuration-options)
- [Troubleshooting](#troubleshooting)

---

## Initial Setup

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Add Your Documents
```powershell
# Create the directory if it doesn't exist
mkdir data\raw_docs -Force

# Copy your PDF documents into:
# C:\MY PROJECTS\enterprise-knowledge-copilot\enterprise-knowledge-copilot\data\raw_docs\
```

### 3. (Optional) Configure OpenAI
```powershell
# Set your OpenAI API key for production LLM responses
$env:OPENAI_API_KEY = "sk-your-key-here"

# Optional: Set organization ID
$env:OPENAI_ORG = "org-your-org-id"
```

**Note:** Without `OPENAI_API_KEY`, the system uses a deterministic fallback summarizer.

---

## CLI Usage

### Start the CLI
```powershell
python -m src.main
```

### CLI Features
- **Multi-turn conversations**: Stay in one session with conversation history
- **Auto-clarification**: System asks follow-up questions when needed
- **Citations**: Every answer includes source documents and page numbers
- **Confidence scores**: See how confident the system is in its answers

### CLI Commands
```
Enter your question (or 'exit'): [Type your question]
exit                    # Quit the application
quit                    # Also quits the application
```

### Example Session
```powershell
PS> python -m src.main

Enter your question (or 'exit'): What is the the total no. of leaves this year?

Answer:
 [System provides answer with sources and confidence]

Enter your question (or 'exit'): What is the count of paid leaves out of those?

Answer:
 [System uses conversation history to understand context]

Enter your question (or 'exit'): exit
Goodbye!
```

---

## REST API Usage

### Start the API Server
```powershell
# Standard mode
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000

# Development mode (auto-reload on code changes)
python -m uvicorn src.api:app --reload

# Custom host and port
python -m uvicorn src.api:app --host 0.0.0.0 --port 8080
```

### API Endpoints

#### 1. Ask a Question
```powershell
# POST /ask
curl -X POST "http://localhost:8000/ask" `
  -H "Content-Type: application/json" `
  -d '{
    "question": "What is the paid time off policy?",
    "conversation_history": []
  }'
```

**Request Body:**
```json
{
  "question": "Your question here",
  "conversation_history": ["previous question 1", "previous question 2"]
}
```

**Response:**
```json
{
  "answer": "The answer text...",
  "sources": [
    {"source": "Policy.pdf", "page": 5, "chunk": 2}
  ],
  "confidence": 0.85,
  "status": "answered",
  "language": "en",
  "clarification_id": null
}
```

**Status Values:**
- `answered` - Successfully answered with context
- `clarification_needed` - Question needs more detail
- `no_context` - No sufficient context found
- `error` - Specialized tool failed (e.g., calculator input invalid)

#### Clarification Workflow
1. When the agent needs more detail you will get `status="clarification_needed"` plus a `clarification_id` and localized prompt.
2. Send your follow-up text to `POST /clarify/{clarification_id}` (JSON: `{ "detail": "More info..." }`).
3. For streaming UX call `POST /clarify/{clarification_id}/stream` and listen for `clarification`, `token`, and `complete` SSE events.
4. Every clarification retains the conversation history that triggered it, so you never lose context between CLI, REST, and the web UI.

#### 2. Health Check
```powershell
# GET /health
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "vector_store_ready": true,
  "llm_enabled": true
}
```

#### 3. Prometheus Metrics
```powershell
# GET /metrics
curl http://localhost:8000/metrics
```

**Returns:** Prometheus-formatted metrics

#### 4. API Documentation
Open in browser:
```
http://localhost:8000/docs          # Interactive Swagger UI
http://localhost:8000/redoc         # ReDoc alternative
```

### Python Client Example
```python
import requests

API_URL = "http://localhost:8000"

# Ask a question
response = requests.post(
    f"{API_URL}/ask",
    json={
        "question": "What is the leave policy?",
        "conversation_history": []
    }
)

data = response.json()
print(f"Answer: {data['answer']}")
print(f"Confidence: {data['confidence']:.2%}")
print(f"Sources: {[s['source'] for s in data['sources']]}")
```

### JavaScript/Fetch Example
```javascript
const API_URL = 'http://localhost:8000';

async function askQuestion(question, history = []) {
    const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question: question,
            conversation_history: history
        })
    });
    
    return await response.json();
}

// Usage
const answer = await askQuestion("What is the camera resolution?");
console.log(answer.answer);
```

---

## Web UI Usage

### Start the Web Interface

**Step 1:** Start the API server
```powershell
python -m uvicorn src.api:app --reload
```

**Step 2:** Open the web interface
```powershell
# Option 1: Open directly in browser
start ui\index.html

# Option 2: Navigate manually
# Open your browser and go to:
# file:///C:/MY%20PROJECTS/enterprise-knowledge-copilot/enterprise-knowledge-copilot/ui/index.html
```

### Web UI Features
- ✅ Real-time chat interface
- ✅ System health indicators (API, vector store, LLM status)
- ✅ Automatic conversation history tracking
- ✅ Source citations displayed with each answer
- ✅ Confidence scores shown
- ✅ Mobile-responsive design

### Using the Web UI
1. Wait for status indicators to show "✓ Online"
2. Type your question in the input box
3. Press Enter or click "Ask"
4. View answer with sources and confidence
5. Follow-up questions maintain conversation context

---

## Running Evaluations

### Run Evaluation Suite
```powershell
# Run with default settings
python evaluation\run_eval.py

# Run with custom question file
python evaluation\run_eval.py --questions path\to\questions.json

# Run with verbose logging
python evaluation\run_eval.py --verbose

# Custom vector cache location
python evaluation\run_eval.py --vector-cache data\custom_cache

# All options
python evaluation\run_eval.py `
  --questions evaluation\eval_questions.json `
  --raw-docs data\raw_docs `
  --vector-cache data\processed_chunks\vector_store `
  --verbose
```

### Evaluation Output
```json
{
  "total_cases": 12,
  "passed": 11,
  "failed": 1,
  "details": [
    "Behavior mismatch for question='...'"
  ]
}
```

**Exit Codes:**
- `0` - All tests passed
- `1` - One or more tests failed (blocks CI/CD)

### Integration with CI/CD

**GitHub Actions Example:**
```yaml
- name: Run Evaluations
  run: python evaluation/run_eval.py
  
- name: Check Exit Code
  if: failure()
  run: echo "Evaluation tests failed"
```

**Jenkins Example:**
```groovy
stage('Evaluate') {
    steps {
        sh 'python evaluation/run_eval.py'
    }
}
```

---

## Monitoring & Metrics

### Prometheus Metrics Endpoint
```powershell
# Start API with metrics enabled
python -m uvicorn src.api:app --host 0.0.0.0 --port 8000

# Access metrics
curl http://localhost:8000/metrics
```

### Available Metrics

**Request Metrics:**
- `agent_requests_total{status}` - Total requests by status
- `agent_request_duration_seconds{status}` - Request duration histogram
- `agent_active_requests` - Currently processing requests

**Retrieval Metrics:**
- `agent_retrieval_confidence` - Confidence score distribution
- `agent_chunks_retrieved` - Number of chunks per query

**Decision Metrics:**
- `agent_decisions_total{decision}` - Decisions by type (retrieve/clarify/answer/refuse)

**LLM Metrics:**
- `agent_llm_calls_total{success}` - LLM API calls
- `agent_llm_errors_total{error_type}` - LLM errors by type

**Cache Metrics:**
- `vector_cache_hits_total` - Cache hit count
- `vector_cache_misses_total` - Cache miss count
- `vector_cache_rebuild_duration_seconds` - Cache rebuild time
- `vector_store_chunks_total` - Total chunks indexed

### Configure Prometheus Scraper

**prometheus.yml:**
```yaml
scrape_configs:
  - job_name: 'enterprise_knowledge_copilot'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8000']
```

### Grafana Dashboard Queries

**Average Request Duration:**
```promql
rate(agent_request_duration_seconds_sum[5m]) / rate(agent_request_duration_seconds_count[5m])
```

**Request Rate by Status:**
```promql
rate(agent_requests_total[5m])
```

**Cache Hit Rate:**
```promql
rate(vector_cache_hits_total[5m]) / (rate(vector_cache_hits_total[5m]) + rate(vector_cache_misses_total[5m]))
```

**95th Percentile Retrieval Confidence:**
```promql
histogram_quantile(0.95, rate(agent_retrieval_confidence_bucket[5m]))
```

---

## Configuration Options

### Environment Variables
```powershell
# OpenAI Configuration
$env:OPENAI_API_KEY = "sk-..."          # Required for OpenAI LLM
$env:OPENAI_ORG = "org-..."             # Optional organization ID

# Logging Level
$env:LOG_LEVEL = "INFO"                  # DEBUG, INFO, WARNING, ERROR

# API Configuration
$env:API_HOST = "0.0.0.0"
$env:API_PORT = "8000"

# Optional: Log shipping + retention
$env:LOG_SHIPPER_ENDPOINT = "https://logs.example.com/ingest"
$env:LOG_SHIPPER_API_KEY = "token-here"
$env:LOG_SHIPPER_BATCH = "100"
$env:AGENT_LOG_MAX_BYTES = "8000000"
$env:AGENT_LOG_BACKUPS = "7"

# Toggle multilingual support (on by default)
$env:EKC_MULTILINGUAL = "false"
```

## Experiments & Multilingual Mode

### A/B Experiments
1. Define variants in `evaluation/experiments.json` (sample `advanced-vs-basic` included).
2. Call `/ask` or `/ask/stream` with headers:
  - `x-experiment-name`: Name from the JSON file.
  - `x-user-id`: Stable identifier (email, UUID, etc.) to keep assignments sticky.
3. Responses echo `experiment` and `variant` so you can fan out telemetry or UI logic per cohort.
4. Variant caches are isolated—repeat the same headers when calling `/cache/stats` if you want variant-specific hit rates.

### Multilingual Answers
- Questions + conversation history are auto-detected with langdetect, translated to English for retrieval, then translated back.
- The response includes `language` so front-ends can localize UI chrome.
- Disable translation with `EKC_MULTILINGUAL=false` if you only operate in English or want to avoid the optional dependencies.
- Chunk metadata (`metadata.language`) is now populated, enabling language-filtered analytics.

### Python Configuration

**Custom Initialization:**
```python
from src.main import initialize_agent
from pathlib import Path

agent = initialize_agent(
    raw_docs_dir=Path("data/raw_docs"),
    vector_cache_dir=Path("data/processed_chunks/vector_store"),
    log_path=Path("data/logs/agent_runs.jsonl"),
    enable_metrics=True,  # Enable Prometheus metrics
    llm_client=None  # Or pass custom LLM client
)

# Use the agent
response = agent.run("What is the policy?")
print(response.answer)
```

### Cache Management

**Clear Vector Cache:**
```powershell
# Force rebuild by deleting cache
Remove-Item -Recurse -Force data\processed_chunks\vector_store
```

**View Cache Manifest:**
```powershell
Get-Content data\processed_chunks\vector_store\manifest.json
```

### Audit Logs

**View Recent Runs:**
```powershell
# View last 10 runs
Get-Content data\logs\agent_runs.jsonl -Tail 10 | ConvertFrom-Json | Format-List
```

**Search Logs:**
```powershell
# Find specific question
Get-Content data\logs\agent_runs.jsonl | ConvertFrom-Json | Where-Object { $_.question -like "*policy*" }
```

---

## Troubleshooting

### Vector Store Issues

**Problem:** "No PDF documents found"
```powershell
# Solution: Add PDFs to raw_docs
Copy-Item yourfile.pdf data\raw_docs\
```

**Problem:** Cache won't rebuild
```powershell
# Solution: Delete cache manually
Remove-Item -Recurse -Force data\processed_chunks\vector_store
python -m src.main
```

### API Issues

**Problem:** API won't start / Port already in use
```powershell
# Solution: Use different port
python -m uvicorn src.api:app --port 8001

# Or kill existing process
Get-Process -Name python | Where-Object { $_.Modules.FileName -like "*uvicorn*" } | Stop-Process
```

**Problem:** CORS errors in Web UI
```powershell
# Solution: Configure CORS in src/api.py (already configured for local development)
```

### LLM Issues

**Problem:** "OPENAI_API_KEY not found"
```powershell
# Solution 1: Set environment variable
$env:OPENAI_API_KEY = "sk-..."

# Solution 2: Use fallback (already works by default)
# System will use deterministic summarizer
```

**Problem:** Rate limit errors
```powershell
# The OpenAI client automatically retries with exponential backoff
# Check logs for retry attempts
```

### Clarification Loop Issues

**Problem:** System always asks for clarification
```powershell
# Common causes:
# 1. Question too short (< 3 words)
# 2. Contains pronouns without conversation history
# 3. Too ambiguous (e.g., "tell me more")

# Solution: Be more specific
# Bad:  "What about it?"
# Good: "What are the camera specifications?"
```

### Evaluation Issues

**Problem:** Tests failing
```powershell
# Run with verbose logging
python evaluation\run_eval.py --verbose

# Check specific failure details in output
```

**Problem:** Expected sources don't match
```powershell
# Ensure the PDF filenames in eval_questions.json match actual files
# Update expected_sources in evaluation\eval_questions.json
```

### Performance Issues

**Problem:** First query is slow
```powershell
# This is normal - first run builds the vector index
# Subsequent queries use cached embeddings and are fast
```

**Problem:** Every query rebuilds cache
```powershell
# Check manifest matches PDFs
Get-Content data\processed_chunks\vector_store\manifest.json

# If PDFs changed, rebuild is expected
# If not, check file permissions on cache directory
```

---

## Quick Reference Commands

```powershell
# Start CLI
python -m src.main

# Start API Server
python -m uvicorn src.api:app --reload

# Run Evaluations
python evaluation\run_eval.py

# Open Web UI (after starting API)
start ui\index.html

# View Metrics
curl http://localhost:8000/metrics

# Check Health
curl http://localhost:8000/health

# View API Docs
start http://localhost:8000/docs

# Clear Cache
Remove-Item -Recurse -Force data\processed_chunks\vector_store

# View Logs
Get-Content data\logs\agent_runs.jsonl -Tail 10
```

---

## Additional Resources

- **Architecture:** See [architecture.md](architecture.md)
- **Design Decisions:** See [decisions.md](decisions.md)
- **Planning Notes:** See [planning.md](planning.md)
- **API Documentation:** http://localhost:8000/docs (when server running)
