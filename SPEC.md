# sds.gp3.app — Product Specification

## Product Summary

**sds.gp3.app** is a multi-tenant, AI-powered Safety Data Sheet management platform. It automates SDS parsing, maintains chemical inventories, generates GHS-compliant labels with direct printer support, answers safety questions in natural language, checks storage compatibility, and produces audit evidence packages on demand.

**Target:** Manufacturing EHS departments buried in SDS binders and manual label creation.
**Value Prop:** Upload an SDS, get structured data + printed labels + compliance tracking instantly.

---

## Architecture

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI + Python 3.11 | API, auth, agent orchestration, label generation |
| Database | PostgreSQL 15 | Multi-tenant data store with RLS |
| Frontend | React 18 + Vite | SPA served via Caddy |
| Reverse Proxy | Caddy 2 | Auto-SSL, static files, proxy (shared with n0v8v) |
| AI Engine | Claude Sonnet (Anthropic API) | SDS parsing, Q&A, evidence generation |
| Label Engine | ReportLab (PDF) + ZPL generation | GHS-compliant label output |
| Container | Docker Compose | Full-stack orchestration |

### Multi-Tenancy Model

**Phase 1 (MVP):** Path-based routing via JWT
- `sds.gp3.app` → Login → JWT-scoped access
- Row-Level Security (RLS) in PostgreSQL isolates all tenant data
- No tenant identifiers in URLs

---

## Core Features

### 1. SDS Upload & Parsing
- Drag-and-drop PDF Safety Data Sheets
- AI extracts all 16 GHS sections into structured JSON
- Auto-matches to chemical registry or creates new entry
- Stores PDF file + structured data
- Validates completeness (flags missing sections)

### 2. Chemical Registry
- Add/manage chemicals: name, CAS#, manufacturer, location, quantity
- Set storage class (flammable, corrosive, oxidizer, general, etc.)
- Track SDS revision dates and expiration (3-year rule)
- Mark high-hazard chemicals
- Location tracking by storage area

### 3. GHS Label Generation
- Generate labels from parsed SDS data
- Full GHS compliance: product name, signal word, pictograms, H/P-statements, supplier info
- Multiple label sizes: primary container, secondary container, pipe marker
- QR code linking to digital SDS
- Preview before printing

### 4. Label Printing
- Zebra ZPL direct printing (TCP/IP to thermal printers)
- PDF fallback for standard printers
- Configurable per tenant (printer IP, model, media, DPI)
- Template system via printer driver tool kernel

### 5. Natural Language Q&A
- "What PPE do I need for acetone?"
- "Which chemicals in Building 2 are flammable?"
- "What's the emergency procedure for a sulfuric acid spill?"
- Context-aware — agent sees full chemical registry + SDS data

### 6. Storage Compatibility
- Automatic compatibility checking when assigning locations
- Flags incompatible chemical pairs (acids + cyanides, oxidizers + flammables, etc.)
- Storage class recommendations
- Visual compatibility matrix

### 7. Compliance Dashboard
- Compliance rate at a glance
- Expired/expiring SDS counts
- Missing SDS alerts
- Chemical count by hazard class
- Recent activity timeline
- Right-to-Know access log

### 8. Audit Evidence Packages
- Branded PDF reports (tenant logo, colors, letterhead)
- Chemical inventory by location/hazard class
- SDS currency status report
- Label compliance verification
- Training record integration (future)

### 9. Emergency Quick Reference
- Rapid lookup: chemical → first aid, spill procedure, fire response, PPE
- Optimized for speed (no AI call — direct from parsed SDS)
- Mobile-friendly for floor access

---

## Database Schema

### Tables

| Table | Purpose |
|-------|---------|
| `tenants` | Multi-tenant registry (slug, company, subscription, token budget) |
| `users` | Authentication (email/password, role, tenant association) |
| `chemicals` | Chemical registry (name, CAS#, manufacturer, location, hazard class, storage) |
| `sds_documents` | Uploaded SDS files (PDF path, revision date, extracted JSON, status) |
| `sds_sections` | Parsed SDS sections (16 per document, section_number, content JSON) |
| `labels` | Generated label records (chemical_id, label_type, content, print_count) |
| `chemical_locations` | Where chemicals are stored (chemical → location mapping + quantity) |
| `compatibility_rules` | Custom compatibility overrides per tenant |
| `compliance_events` | Audit trail (uploads, prints, alerts, access logs) |
| `token_usage` | API cost tracking per tenant |

### Security
- All data tables have RLS policies keyed on `tenant_id`
- `SET LOCAL app.current_tenant_id` per request
- JWT tokens encode `tenant_id`
- Restricted `sds_app` DB user (non-superuser, FORCE RLS)

---

## API Endpoints

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Email/password login → JWT |
| POST | `/auth/register` | Create user for existing tenant |

### Agent (Tenant-Scoped via JWT)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/sds/upload` | Upload SDS PDF → AI extraction |
| POST | `/sds/question` | Natural language Q&A |
| POST | `/sds/download` | Generate audit evidence package |
| GET | `/sds/chemicals` | List chemicals + latest SDS status |
| POST | `/sds/chemicals` | Add chemical to registry |
| POST | `/sds/label` | Generate GHS label for chemical |
| POST | `/sds/print` | Send label to printer |
| GET | `/sds/emergency/{chemical_id}` | Quick emergency reference |
| GET | `/sds/compatibility` | Storage compatibility check |
| GET | `/sds/dashboard` | Dashboard stats + activity |
| POST | `/sds/upload-logo` | Upload tenant logo |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

---

## Infrastructure

### VPS: Maggie (Co-located)
- **IP:** 89.116.157.23 (SSH port 22)
- **Co-located with:** KERNEL platform, cal-agent
- **Incremental cost:** $0

### DNS
- A record: `sds.gp3.app` → `89.116.157.23`
- SSL handled by existing `n0v8v-caddy` container

### Containers
| Container | Image | Port | Network |
|-----------|-------|------|---------|
| sds-postgres | postgres:15-alpine | 5436 (host) → 5432 | sds-net |
| sds-backend | custom (Python 3.11) | 8201 (host) → 8000 | sds-net + n0v8v-net |

### Key Paths on VPS
- Project: `/opt/sds-agent/`
- Frontend static: `/opt/sds-web/`
- Caddy config: `/opt/n0v8v/Caddyfile` (shared)

---

## Three-Layer Kernel Architecture

```
Layer 1 — Agent Kernel (shared)
  kernels/sds_v1.0.ttc.md
  └── SDS parsing, GHS classification, label rules, compliance logic

Layer 2 — Tool Kernel (shared)
  kernels/tools/printerdrivers.ttc.md
  └── Zebra ZPL, Brother, Dymo, EPSON, PDF templates

Layer 3 — Tenant Kernel (per-customer)
  kernels/tenants/{slug}-sds.ttc.md
  └── Their printer, locations, chemical categories, branding, business rules
```

---

## Economics

### Cost Per Tenant (Monthly)
| Item | Cost |
|------|------|
| VPS allocation | $0 (co-located) |
| Anthropic tokens | $1-3 (SDS parsing is heavier) |
| **Total COGS** | **~$3** |

### Revenue
- Platform fee: **$500-700/month** per tenant
- Label printer hardware: markup on Zebra ZD421 ($450 MSRP → $650 installed)
- Gross margin: **99%**

---

## File Structure

```
sds-agent/
├── SPEC.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── index.css
│       └── App.jsx
├── database/
│   └── init.sql
├── kernels/
│   ├── sds_v1.0.ttc.md
│   ├── tools/
│   │   └── printerdrivers.ttc.md
│   └── tenants/
│       └── bunting-sds.ttc.md
└── scripts/
    ├── deploy.sh
    └── add-tenant.sh
```
