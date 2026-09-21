# Production Deployment & Runtime Hardening Guide

## 1. Architecture Overview

`company-ocr-service` is an enterprise-grade document extraction, verification, and AI visual reasoning microservice designed for high security and **100% on-premise local data isolation**.

```
                +-------------------------------------------------------------+
                |                       Public Traffic                        |
                |                      HTTP :80 / HTTPS                       |
                +------------------------------+------------------------------+
                                               |
                                               v
                +-------------------------------------------------------------+
                |                    Nginx Reverse Proxy                      |
                |   - Security Headers (DENY iframe, nosniff, XSS protection) |
                |   - Rate limit pass-through & IP forwarding                 |
                |   - Extended 300s proxy timeouts for OCR & AI analysis       |
                |   - 60MB client request body size limit                     |
                +------------------+-----------------------+------------------+
                                   |                       |
               / (SPA UI Traffic)  |                       | /api/*, /ocr/*, /health, /ready
                                   v                       v
                    +--------------------+   +------------------------------------+
                    |   Frontend SPA     |   |   FastAPI Backend (Gunicorn)       |
                    |   - React 19       |   |   - Non-root user (appuser:10001)  |
                    |   - Vite bundle    |   |   - AES-256-GCM authenticated enc  |
                    |   - Nginx static   |   |   - Sliding-window rate limiter    |
                    |     web server     |   |   - Automatic retention sweeper    |
                    +--------------------+   +-----------------+------------------+
                                                               |
                                            internal_net ONLY  | (http://ollama:11434)
                                            (No public ports!) |
                                                               v
                                             +------------------------------------+
                                             |       Local Ollama Engine          |
                                             |   - Private Docker bridge network  |
                                             |   - Isolated from host and web     |
                                             |   - Model: qwen2.5vl:3b            |
                                             +------------------------------------+
```

### Key Security & Isolation Guarantees
1. **Zero External API Dependencies**: No document bytes, extracted fields, or prompts leave the host machine or container network.
2. **Network Isolation for Local AI**: The `ollama` container is bound strictly to `internal_net` (an internal bridge network). It publishes **no host ports**, completely blocking external access to LLM APIs.
3. **Non-Root Execution**: Backend runs as `appuser` (UID 10001, GID 10001) with least-privilege permissions on `/app/uploads` and `/tmp/company_ocr_temp`.
4. **Data at Rest Authenticated Encryption**: Documents saved to `/app/uploads/original/` and `/app/uploads/results/` are encrypted with AES-256-GCM immediately upon receipt.
5. **PII Redaction in Logs**: Structured JSON audit logs redact PAN, Aadhaar, bank accounts, IFSC, GSTIN, raw OCR text, and AI prompts.

---

## 2. Configuration & Environment Variables

Create `.env` based on `.env.example`:

```bash
cp .env.example .env
```

| Variable | Description | Default | Production Recommendation |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime mode (`production` or `development`) | `development` | `production` |
| `DOCUMENT_ENCRYPTION_KEY` | 32-byte (64 hex characters) key for AES-256-GCM | *(Required)* | Generate via `openssl rand -hex 32` |
| `OLLAMA_HOST` | Host URL for the local Ollama instance | `http://127.0.0.1:11434` | In Docker: `http://ollama:11434` |
| `OLLAMA_MODEL` | Visual reasoning model tag | `qwen2.5vl:3b` | `qwen2.5vl:3b` |
| `MAX_IMAGE_SIZE_MB` | Maximum allowed image upload size | `20` | `20` |
| `MAX_PDF_SIZE_MB` | Maximum allowed PDF upload size | `50` | `50` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed web origins | `""` | `https://ocr.yourcompany.com,http://localhost:80` |
| `RATE_LIMIT_ENABLED` | Toggle in-memory sliding-window rate limiting | `true` | `true` |
| `RATE_LIMIT_UPLOAD_PER_MINUTE` | Max document uploads allowed per client IP per min | `60` | `30` - `60` |
| `RATE_LIMIT_AI_CHAT_PER_MINUTE` | Max AI chat queries allowed per client IP per min | `30` | `20` - `30` |
| `RATE_LIMIT_CLEANUP_PER_MINUTE` | Max manual cleanup runs allowed per client IP per min | `10` | `5` - `10` |
| `DOCUMENT_RETENTION_DAYS` | Number of days before expired documents are deleted | `30` | `30` (Set `0` to disable auto-cleanup) |
| `CLEANUP_INTERVAL_HOURS` | Interval between scheduled storage cleanup checks | `24` | `24` |
| `AUTH_MODE` | Authentication mode (`disabled`, `bearer`, `dual`) | `disabled` | `dual` or `bearer` |

> [!WARNING]
> Never commit `.env` to Git or expose `DOCUMENT_ENCRYPTION_KEY` to client-side code. If the encryption key is changed or lost, previously encrypted documents cannot be decrypted.

---

## 3. Deployment with Docker Compose

### Prerequisites
- Docker Engine 24.0+
- Docker Compose 2.20+
- 8 GB+ RAM and multi-core CPU (recommended for RapidOCR and Ollama visual reasoning)

### Step 1: Generate Encryption Key
```bash
# Generate a cryptographically secure 32-byte encryption key
openssl rand -hex 32
```
Paste this value into `.env`:
```env
DOCUMENT_ENCRYPTION_KEY=c3f1a2b4...32byteshex...
```

### Step 2: Build and Start Services
```bash
docker compose up -d --build
```

### Step 3: Pull Ollama Vision Model
Because Ollama runs locally inside the isolated network, download the visual model once:
```bash
docker exec -it company_ocr_ollama ollama pull qwen2.5vl:3b
```

### Step 4: Verify Deployment & Readiness
Test the readiness endpoint through the Nginx reverse proxy:
```bash
curl http://localhost/ready
```

Expected output:
```json
{
  "status": "ok",
  "ready": true,
  "checks": {
    "rapidocr": true,
    "storage": true,
    "encryption_key": true,
    "ollama": true,
    "ollama_model": true
  },
  "details": {
    "ocr_engine": "rapidocr",
    "ollama_host": "http://ollama:11434",
    "ollama_model": "qwen2.5vl:3b"
  }
}
```

---

## 4. Operational Endpoints & Health Monitoring

| Endpoint | Method | Purpose | Healthy Status | Degraded Status | Failure Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/health` | `GET` | Service liveness probe | `200 {"status":"healthy"}` | N/A | `503` |
| `/ready` | `GET` | Production readiness probe | `200 {"status":"ok"}` | `200 {"status":"degraded"}` (Ollama offline; Offline mode works) | `503 {"status":"error"}` (RapidOCR/Storage/Key missing) |
| `/api/documents/cleanup`| `POST` | Trigger manual retention cleanup | `200 {"success":true,"deleted_count":N}` | N/A | `429` (Rate limited) |

### Monitoring Guidelines
- **Kubernetes / Load Balancer Liveness**: Point to `GET /health` with `initialDelaySeconds: 15`, `periodSeconds: 30`.
- **Kubernetes / Load Balancer Readiness**: Point to `GET /ready` with `initialDelaySeconds: 10`, `periodSeconds: 10`.

---

## 5. Storage Persistence, Backup & Disaster Recovery

### Volume Management
Data is stored in Docker named volumes:
- `document_uploads`: Maps to `/app/uploads` in backend container.
  - `uploads/original/*.enc`: AES-256-GCM encrypted original files.
  - `uploads/results/*.json.enc`: AES-256-GCM encrypted OCR results.
  - `uploads/processed/*`: Preview thumbnails.
  - `uploads/documents.json`: Non-sensitive document metadata registry.
- `ollama_models`: Maps to `/root/.ollama` in ollama container.

### Backup Procedure
To back up encrypted documents and metadata:
```bash
docker run --rm \
  --volumes-from company_ocr_backend \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/document_vault_$(date +%Y%m%d_%H%M%S).tar.gz /app/uploads
```
> [!IMPORTANT]
> Always securely back up the corresponding `DOCUMENT_ENCRYPTION_KEY` alongside any volume backup.

---

## 6. Rate Limiting & Protection Defaults

When rate limits are exceeded, the API responds with HTTP 429:
```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 45

{
  "detail": "Rate limit exceeded for ai_chat. Max 30 requests per minute. Try again in 45s."
}
```

Client IP is resolved via:
1. `X-Forwarded-For` header (first IP in chain forwarded by Nginx)
2. `X-Real-IP` header
3. Direct socket connection IP
