# Universal Options Market Dashboard

Production-grade derivatives market-data, Greeks calculation, and options analytics system built for Angel One SmartAPI, Oracle Cloud, PostgreSQL, Redis, FastAPI, and Google Sheets.

---

## Current Status: Phase 1 — Foundation Completed

- [x] **Phase 1: Foundation** (Project skeleton, configuration, security redaction, logging, FastAPI, PostgreSQL & Redis client resilience, Docker, health & status endpoints, unit tests)
- [ ] **Phase 2: Angel One Authentication**
- [ ] **Phase 3: Instrument Master**
- [ ] **Phase 4: Token Manager & WebSocket**
- [ ] **Phase 5: Option Chain Engine**
- [ ] **Phase 6: OI Engine**
- [ ] **Phase 7: ATM Engine**
- [ ] **Phase 8: IV Engine**
- [ ] **Phase 9: Greeks Engine**
- [ ] **Phase 10: Analytics**
- [ ] **Phase 11: Historical Data**
- [ ] **Phase 12: FastAPI Routes Expansion**
- [ ] **Phase 13: Google Sheets Apps Script**
- [ ] **Phase 14: Dashboard & Charts**
- [ ] **Phase 15: Deployment & Full Integration**

---

## Quickstart (Development & Testing)

### 1. Run Unit Tests
```bash
PYTHONPATH=. python3 -m unittest discover -s backend/tests/unit -v
```

### 2. Launch Local Docker Stack
```bash
cp .env.example .env
cd docker
docker compose up -d --build
```

### 3. Verify Health & Status Endpoints
```bash
curl http://localhost:8000/health
curl http://localhost:8000/status
```

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       └── status.py
│   │   ├── models/
│   │   │   ├── schemas/
│   │   │   │   ├── health.py
│   │   │   │   └── status.py
│   │   │   └── db/
│   │   │       ├── base.py
│   │   │       └── session.py
│   │   └── services/
│   │       └── storage/
│   │           ├── redis_client.py
│   │           └── db_client.py
│   ├── tests/
│   │   └── unit/
│   │       ├── test_config.py
│   │       ├── test_health.py
│   │       └── test_status.py
│   └── requirements.txt
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── nginx/
│   └── nginx.conf
├── docs/
│   ├── architecture.md
│   └── deployment.md
├── .env.example
├── .gitignore
└── README.md
```
