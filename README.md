# CodeSentinel — 24/7 Intelligent Code Reviewer

> A production-grade, AI-powered code reviewer built entirely on **Google Cloud Platform**.  
> Automatically reviews every Pull Request using **Gemini 1.5 Pro on Vertex AI**, posts inline comments with quality scores, and learns from historical reviews stored in **Firestore**.

---

## Features

| Feature | Description |
|---|---|
| 🤖 **AI Code Review** | Gemini 1.5 Pro reviews diffs in Python, JS, TS, Go, Java, Rust, and more |
| 📊 **Quality Scoring** | Structured 0–100 score across Correctness, Security, Performance, Style |
| 💬 **Inline Comments** | Posts directly on PR diff lines with severity levels |
| 🧠 **Historical Learning** | Firestore stores past reviews; context injected into future reviews |
| 🌐 **Live Dashboard** | Real-time web UI showing review feed, stats, and architecture |
| 🔄 **24/7 Always-On** | Cloud Run with auto-scaling; zero infrastructure management |
| 🔐 **Secure** | Webhook signature verification; secrets via Secret Manager |

---

## Architecture

```
GitHub PR (opened/sync) 
    │
    ▼
Cloud Run (FastAPI webhook server)
    │
    ├──► Vertex AI (Gemini 1.5 Pro) — review generation
    │
    ├──► Firestore — save review + fetch historical context
    │
    └──► GitHub PR Review API — post inline comments + summary
```

### GCP Services Used
- **Cloud Run** — serverless container, always-on webhook listener
- **Vertex AI / Gemini 1.5 Pro** — code review intelligence
- **Firestore** — historical review storage & pattern learning
- **Secret Manager** — GitHub token, webhook secret
- **Artifact Registry** — Docker image storage
- **Cloud Build** — CI/CD pipeline

---

## Setup

### 1. Prerequisites

```bash
# Install gcloud CLI and authenticate
gcloud auth login
gcloud config set project gen-lang-client-0531791614

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

### 2. Create Firestore database

```bash
gcloud firestore databases create --region=us-central1
```

### 3. Store secrets

```bash
# GitHub Personal Access Token (needs repo + pull_requests write scope)
echo -n "ghp_your_token_here" | gcloud secrets create github-token --data-file=-

# Webhook secret (generate any random string)
echo -n "your_webhook_secret" | gcloud secrets create webhook-secret --data-file=-
```

### 4. Create Artifact Registry repository

```bash
gcloud artifacts repositories create code-reviewer \
  --repository-format=docker \
  --location=us-central1
```

### 5. Deploy via Cloud Build

```bash
gcloud builds submit --config cloudbuild.yaml
```

### 6. Configure GitHub Webhook

1. Go to your GitHub repo → **Settings → Webhooks → Add webhook**
2. **Payload URL**: `https://your-cloud-run-url/webhook/github`
3. **Content type**: `application/json`
4. **Secret**: the same value you stored in Secret Manager
5. **Events**: Select "Pull requests"

---

## Local Development

```bash
# Clone and install
git clone https://github.com/YOUR_USERNAME/code-sentinel
cd code-sentinel
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env
# Edit .env with your values

# Run locally
uvicorn app.main:app --reload --port 8080

# Test with demo endpoint (no GitHub webhook needed)
curl -X POST http://localhost:8080/api/demo-review \
  -H "Content-Type: application/json" \
  -d '{"repo": "demo/myrepo", "pr_number": 1, "commit_sha": "abc123"}'
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard UI |
| `GET` | `/health` | Cloud Run health check |
| `POST` | `/webhook/github` | GitHub PR webhook receiver |
| `GET` | `/api/reviews` | List recent reviews |
| `GET` | `/api/reviews/{owner}/{repo}` | Per-repo reviews & stats |
| `POST` | `/api/demo-review` | Trigger a demo review |

---

## Review Output Example

When a PR is opened, CodeSentinel posts:

```
## ✅ AI Code Review — Score: 82/100 (Grade: A)

### 📊 Score Breakdown
| Category     | Score | Max |
|---|---|---|
| Correctness  | 22    | 25  |
| Security     | 18    | 25  |
| Performance  | 20    | 25  |
| Style        | 22    | 25  |
| **Total**    | **82**| **100** |

### 🔍 Summary
The code implements a solid REST endpoint with good error handling.
A potential SQL injection risk was found on line 47 and should be addressed before merging.

💬 5 inline comments posted · Historical patterns applied
```

---

## Built For

**Code Kitchen S01** — An AIM Originals reality series for India's working developers.  
Track: *The 24/7 Intelligent Code Reviewer*  
Presented by **Google Cloud**.

---

## License

MIT
