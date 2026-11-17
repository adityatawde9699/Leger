# Database Schema

## Entity Relationship Diagram

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐
│  users   │─1:N─│ transactions │     │  audit_logs   │
│──────────│     │──────────────│     │───────────────│
│ id  (PK) │     │ id      (PK) │     │ id       (PK) │
│ email    │     │ user_id (FK) │     │ user_id       │
│ created  │     │ account_id   │     │ action        │
└────┬─────┘     │ type         │     │ resource_type │
     │           │ category     │     │ resource_id   │
     │           │ amount       │     │ details       │
     │           │ description  │     │ ip_address    │
     │           │ date         │     │ created_at    │
     │           │ source       │     └───────────────┘
     │           │ gst_rate     │
     │           │ gst_amount   │
     │           │ hsn_code     │
     │           │ tags, notes  │
     │           └──────────────┘
     │
     ├──1:N──┌──────────────┐
     │       │   accounts   │
     │       │──────────────│
     │       │ id      (PK) │
     │       │ user_id (FK) │
     │       │ name         │
     │       │ account_type │
     │       │ balance      │
     │       │ is_active    │
     │       └──────────────┘
     │
     ├──1:N──┌──────────────┐
     │       │   budgets    │
     │       │──────────────│
     │       │ id      (PK) │
     │       │ user_id (FK) │
     │       │ category     │
     │       │ monthly_limit│
     │       └──────────────┘
     │
     ├──1:N──┌──────────────┐     ┌──────────────┐
     │       │ portfolios   │─1:N─│   holdings   │
     │       │──────────────│     │──────────────│
     │       │ id      (PK) │     │ id      (PK) │
     │       │ user_id (FK) │     │ portfolio_id │
     │       │ name         │     │ symbol       │
     │       │ type         │     │ name         │
     │       └──────────────┘     │ quantity     │
     │                            │ buy_price    │
     │                            │ current_price│
     │                            │ asset_type   │
     │                            └──────────────┘
     │
     └──1:N──┌──────────────┐
             │   webhooks   │
             │──────────────│
             │ id      (PK) │
             │ user_id (FK) │
             │ url          │
             │ events       │
             │ secret       │
             │ is_active    │
             │ failure_count│
             └──────────────┘
```

## Models Reference

### User
| Column | Type | Notes |
|---|---|---|
| `id` | `String(64)` | Primary key |
| `email` | `String(255)` | Nullable |
| `created_at` | `DateTime(tz)` | Auto-set |

### Transaction
| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` | UUID, primary key |
| `user_id` | FK → `users.id` | Indexed |
| `account_id` | FK → `accounts.id` | Nullable |
| `type` | `String(16)` | `income` or `expense` |
| `category` | `String(64)` | e.g., Dining, Groceries |
| `amount` | `Numeric(12,2)` | |
| `description` | `String(512)` | |
| `date` | `Date` | |
| `source` | `String(32)` | manual, sms, csv, pdf |
| `merchant_normalized` | `String(128)` | Nullable |
| `fingerprint` | `String(64)` | SHA256 dedup |
| `gst_rate` | `Float` | GST percentage |
| `gst_amount` | `Numeric(12,2)` | Computed |
| `hsn_code` | `String(16)` | HSN/SAC code |
| `tags` | `String(256)` | Comma-separated |
| `notes` | `Text` | Free text |

### Account
| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` | UUID |
| `user_id` | FK → `users.id` | |
| `name` | `String(128)` | e.g., "HDFC Savings" |
| `account_type` | `String(32)` | savings, credit, wallet, cash |
| `balance` | `Numeric(14,2)` | |
| `is_active` | `Boolean` | Default `true` |

### Portfolio
| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` | UUID |
| `user_id` | FK → `users.id` | |
| `name` | `String(128)` | |
| `portfolio_type` | `String(32)` | stocks, mutual_funds, crypto, fixed_deposit, gold |

### Holding
| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` | UUID |
| `portfolio_id` | FK → `portfolios.id` | Cascade delete |
| `symbol` | `String(32)` | Ticker symbol |
| `name` | `String(128)` | Full name |
| `quantity` | `Numeric(14,4)` | |
| `buy_price` | `Numeric(14,2)` | Per unit |
| `current_price` | `Numeric(14,2)` | Per unit |
| `asset_type` | `String(32)` | equity, mf, etf, crypto, fd, gold |

### AuditLog
| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` | UUID |
| `user_id` | `String(64)` | Indexed (no FK for immutability) |
| `action` | `String(64)` | create, update, delete |
| `resource_type` | `String(64)` | transaction, budget, account, webhook |
| `resource_id` | `String(36)` | Nullable |
| `details` | `Text` | JSON-serialized diff |
| `ip_address` | `String(45)` | Client IP |
| Indexes | | `(user_id, created_at)` composite |

### Webhook
| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)` | UUID |
| `user_id` | FK → `users.id` | |
| `url` | `String(2048)` | Endpoint URL |
| `events` | `String(512)` | Comma-separated event names |
| `secret` | `String(64)` | HMAC-SHA256 key |
| `is_active` | `Boolean` | Auto-disabled after 5 failures |
| `failure_count` | `Integer` | Consecutive failures |

## Migrations

Schema changes are Alembic revisions in `backend/migrations/versions`. Production
applies them on container start (`python -m app.migrate` in `entrypoint.sh`); local
development applies them on app startup unless `RUN_DB_BOOTSTRAP=false`.

```bash
cd backend

# After changing app/models.py, generate a revision and review it by hand
alembic revision --autogenerate -m "add portfolios and holdings"

# Apply migrations (uses DATABASE_URL from settings)
alembic upgrade head

# Roll back one revision (the 0001 baseline cannot be downgraded)
alembic downgrade -1
```

`0001_baseline` is idempotent: it creates whatever tables, columns and indexes are
missing, so databases created before Alembic was adopted upgrade without a manual
`alembic stamp`. `tests/test_migrations.py` fails if the migrations and the models
ever describe different schemas.
