# Universal Options Market Dashboard - Architecture

## 1. System Overview

The **Universal Options Market Dashboard** is an enterprise-grade quantitative derivatives market-data and analytics platform. It captures streaming real-time quotes via Angel One SmartAPI WebSocket, computes analytical metrics (IV, Greeks, PCR, Max Pain, ATM), caches the latest state in Redis, persists periodic snapshots into PostgreSQL, and serves high-density dashboards to Google Sheets and web clients via FastAPI.

```
[Angel One SmartAPI REST / WebSocket]
               │
               ▼
   [Oracle Cloud Backend Engine]
   ├── Authentication & Session Manager (Safe Auto-Reconnect)
   ├── Dynamic Instrument Master (Zero hardcoding of strikes/expiries)
   ├── Token & Subscription Manager
   ├── WebSocket Stream Worker
   ├── Quantitative Analytics Pipeline (IV, Greeks, PCR, Max Pain, ATM)
   └── Snapshot Ingestion Engine (Configurable: 1s, 5s, 10s, 30s, 1m)
               │
      ┌────────┴────────┐
      ▼                 ▼
[Redis Cache]     [PostgreSQL DB]
(Real-time State) (Historical Snapshots)
      │                 │
      └────────┬────────┘
               ▼
      [FastAPI REST API]
               │
      ┌────────┴────────┐
      ▼                 ▼
[Google Sheets API]  [Web Options Terminal]
(Apps Script UI)     (Interactive Dashboard)
```

## 2. Key Architecture Principles

1. **Google Sheets is a Presentation Layer, Not a Database**:
   - Sheets never ingests raw WebSocket ticks directly.
   - Sheets polls the FastAPI backend periodically (default: 5 seconds) or on manual trigger.
   - The backend continues uninterrupted if Google Sheets is unreachable.

2. **Strict Security Isolation**:
   - Angel One API key, client code, password/PIN, and TOTP secret are restricted to backend environment variables.
   - Credentials are **never** stored in Google Sheets, frontend code, version control, or application logs.
   - Log formatters automatically redact sensitive token keys.

3. **Dynamic Instrument Discovery**:
   - Contracts, expiries, strikes, CE tokens, and PE tokens are dynamically discovered from Angel One's instrument master.
   - No hardcoded strikes or intervals.

4. **Fault Tolerance & Graceful Degradation**:
   - The backend operates in standalone mode if Redis or PostgreSQL is temporarily unreachable.
   - One invalid tick or malformed strike does not crash the entire market-data stream.

5. **Provider Independence**:
   - Market data is normalized into an internal broker-agnostic schema before processing, making it trivial to connect additional market-data feeds in the future.
