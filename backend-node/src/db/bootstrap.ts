import postgres from "postgres";
import { config } from "../config.js";

// Dev-only DDL bootstrap (RUN_DB_BOOTSTRAP=true), mirrors backend/entrypoint.sh.
// Production tables already exist (created by the Python service) and are
// never touched here — this only runs against fresh local/dev databases.
export async function bootstrap() {
  const sql = postgres(config.DATABASE_URL, { prepare: false, max: 1 });
  try {
    await sql.unsafe(`
      CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(64) PRIMARY KEY,
        email VARCHAR(255),
        display_name VARCHAR(128),
        avatar_url TEXT,
        currency_preference VARCHAR(3) NOT NULL DEFAULT 'INR',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );

      CREATE TABLE IF NOT EXISTS accounts (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        name VARCHAR(128) NOT NULL,
        account_type VARCHAR(32) NOT NULL,
        institution VARCHAR(128),
        balance NUMERIC(14,2) NOT NULL DEFAULT 0,
        currency VARCHAR(3) NOT NULL DEFAULT 'INR',
        is_active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_accounts_user ON accounts(user_id);

      CREATE TABLE IF NOT EXISTS transactions (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        account_id VARCHAR(36) REFERENCES accounts(id),
        date DATE NOT NULL,
        type VARCHAR(16) NOT NULL,
        category VARCHAR(64) NOT NULL,
        amount NUMERIC(12,2) NOT NULL,
        description TEXT NOT NULL,
        merchant_normalized VARCHAR(128),
        source VARCHAR(32) NOT NULL DEFAULT 'cash',
        source_ref VARCHAR(128),
        confidence DOUBLE PRECISION,
        tags VARCHAR(512),
        notes TEXT,
        gst_rate DOUBLE PRECISION,
        gst_amount NUMERIC(10,2),
        hsn_code VARCHAR(16),
        running_balance NUMERIC(14,2),
        stmt_seq INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_transactions_user_id ON transactions(user_id);
      CREATE INDEX IF NOT EXISTS ix_transactions_account_id ON transactions(account_id);
      CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions(date);
      CREATE INDEX IF NOT EXISTS ix_transactions_category ON transactions(category);
      CREATE INDEX IF NOT EXISTS ix_transactions_source ON transactions(source);
      CREATE INDEX IF NOT EXISTS ix_transactions_user_date ON transactions(user_id, date);
      CREATE INDEX IF NOT EXISTS ix_transactions_user_category ON transactions(user_id, category);

      CREATE TABLE IF NOT EXISTS budgets (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        category VARCHAR(64) NOT NULL,
        monthly_limit NUMERIC(12,2) NOT NULL,
        strategy VARCHAR(32) NOT NULL DEFAULT 'manual',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_budget_user_category UNIQUE (user_id, category)
      );
      CREATE INDEX IF NOT EXISTS ix_budgets_user ON budgets(user_id);

      CREATE TABLE IF NOT EXISTS import_jobs (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        file_name VARCHAR(255) NOT NULL,
        row_count INTEGER,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_import_jobs_user ON import_jobs(user_id);

      CREATE TABLE IF NOT EXISTS ai_conversations (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        title VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_ai_conversations_user ON ai_conversations(user_id);

      CREATE TABLE IF NOT EXISTS ai_messages (
        id VARCHAR(36) PRIMARY KEY,
        conversation_id VARCHAR(36) NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
        role VARCHAR(16) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_ai_messages_conversation ON ai_messages(conversation_id);

      CREATE TABLE IF NOT EXISTS audit_logs (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL,
        action VARCHAR(64) NOT NULL,
        resource_type VARCHAR(64) NOT NULL,
        resource_id VARCHAR(36),
        details TEXT,
        ip_address VARCHAR(45),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_logs(user_id);
      CREATE INDEX IF NOT EXISTS ix_audit_user_time ON audit_logs(user_id, created_at);

      CREATE TABLE IF NOT EXISTS webhooks (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        url VARCHAR(2048) NOT NULL,
        events VARCHAR(512) NOT NULL,
        secret VARCHAR(64) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT true,
        last_triggered TIMESTAMPTZ,
        failure_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_webhooks_user ON webhooks(user_id);

      CREATE TABLE IF NOT EXISTS portfolios (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        name VARCHAR(128) NOT NULL,
        portfolio_type VARCHAR(32) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_portfolios_user ON portfolios(user_id);

      CREATE TABLE IF NOT EXISTS holdings (
        id VARCHAR(36) PRIMARY KEY,
        portfolio_id VARCHAR(36) NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
        symbol VARCHAR(32) NOT NULL,
        name VARCHAR(128) NOT NULL,
        quantity NUMERIC(14,4) NOT NULL,
        buy_price NUMERIC(14,2) NOT NULL,
        current_price NUMERIC(14,2) NOT NULL DEFAULT 0,
        asset_type VARCHAR(32) NOT NULL,
        purchase_date DATE,
        notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS ix_holdings_portfolio ON holdings(portfolio_id);

      CREATE TABLE IF NOT EXISTS category_corrections (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(64) NOT NULL REFERENCES users(id),
        description_hash VARCHAR(64) NOT NULL,
        category VARCHAR(64) NOT NULL,
        correction_count INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_cat_correction_user_hash UNIQUE (user_id, description_hash)
      );
      CREATE INDEX IF NOT EXISTS ix_category_corrections_user ON category_corrections(user_id);

      ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(128);
      ALTER TABLE users ADD COLUMN IF NOT EXISTS currency_preference VARCHAR(3) NOT NULL DEFAULT 'INR';
      ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
    `);
    console.log("Bootstrap OK");
  } finally {
    await sql.end();
  }
}
