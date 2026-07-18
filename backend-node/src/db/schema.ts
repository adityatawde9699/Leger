import { randomUUID } from "node:crypto";
import {
  pgTable,
  varchar,
  text,
  numeric,
  date,
  integer,
  doublePrecision,
  boolean,
  timestamp,
  index,
  uniqueIndex,
} from "drizzle-orm/pg-core";

// Byte-compatible with backend/app/models.py — never `drizzle-kit push`
// against production; this schema documents the existing tables only.
const uid = () => randomUUID();
const now = () => new Date();

export const users = pgTable("users", {
  id: varchar("id", { length: 64 }).primaryKey(),
  email: varchar("email", { length: 255 }),
  displayName: varchar("display_name", { length: 128 }),
  avatarUrl: text("avatar_url"),
  currencyPreference: varchar("currency_preference", { length: 3 }).notNull().default("INR"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
});

export const accounts = pgTable("accounts", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  name: varchar("name", { length: 128 }).notNull(),
  accountType: varchar("account_type", { length: 32 }).notNull(),
  institution: varchar("institution", { length: 128 }),
  balance: numeric("balance", { precision: 14, scale: 2 }).notNull().default("0"),
  currency: varchar("currency", { length: 3 }).notNull().default("INR"),
  isActive: boolean("is_active").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().$defaultFn(now).$onUpdateFn(now),
}, (t) => [index("ix_accounts_user").on(t.userId)]);

export const transactions = pgTable("transactions", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  accountId: varchar("account_id", { length: 36 }).references(() => accounts.id),
  date: date("date", { mode: "string" }).notNull(),
  type: varchar("type", { length: 16 }).notNull(),
  category: varchar("category", { length: 64 }).notNull(),
  amount: numeric("amount", { precision: 12, scale: 2 }).notNull(),
  description: text("description").notNull(),
  merchantNormalized: varchar("merchant_normalized", { length: 128 }),
  source: varchar("source", { length: 32 }).notNull().default("cash"),
  sourceRef: varchar("source_ref", { length: 128 }),
  confidence: doublePrecision("confidence"),
  tags: varchar("tags", { length: 512 }),
  notes: text("notes"),
  gstRate: doublePrecision("gst_rate"),
  gstAmount: numeric("gst_amount", { precision: 10, scale: 2 }),
  hsnCode: varchar("hsn_code", { length: 16 }),
  runningBalance: numeric("running_balance", { precision: 14, scale: 2 }),
  stmtSeq: integer("stmt_seq"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
}, (t) => [
  index("ix_transactions_user_id").on(t.userId),
  index("ix_transactions_account_id").on(t.accountId),
  index("ix_transactions_date").on(t.date),
  index("ix_transactions_category").on(t.category),
  index("ix_transactions_source").on(t.source),
  index("ix_transactions_user_date").on(t.userId, t.date),
  index("ix_transactions_user_category").on(t.userId, t.category),
]);

export const budgets = pgTable("budgets", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  category: varchar("category", { length: 64 }).notNull(),
  monthlyLimit: numeric("monthly_limit", { precision: 12, scale: 2 }).notNull(),
  strategy: varchar("strategy", { length: 32 }).notNull().default("manual"),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().$defaultFn(now).$onUpdateFn(now),
}, (t) => [
  index("ix_budgets_user").on(t.userId),
  uniqueIndex("uq_budget_user_category").on(t.userId, t.category),
]);

export const importJobs = pgTable("import_jobs", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  status: varchar("status", { length: 32 }).notNull().default("pending"),
  fileName: varchar("file_name", { length: 255 }).notNull(),
  rowCount: integer("row_count"),
  errorMessage: text("error_message"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().$defaultFn(now).$onUpdateFn(now),
}, (t) => [index("ix_import_jobs_user").on(t.userId)]);

export const aiConversations = pgTable("ai_conversations", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  title: varchar("title", { length: 255 }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().$defaultFn(now).$onUpdateFn(now),
}, (t) => [index("ix_ai_conversations_user").on(t.userId)]);

export const aiMessages = pgTable("ai_messages", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  conversationId: varchar("conversation_id", { length: 36 }).notNull().references(() => aiConversations.id, { onDelete: "cascade" }),
  role: varchar("role", { length: 16 }).notNull(),
  content: text("content").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
}, (t) => [index("ix_ai_messages_conversation").on(t.conversationId)]);

export const auditLogs = pgTable("audit_logs", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull(),
  action: varchar("action", { length: 64 }).notNull(),
  resourceType: varchar("resource_type", { length: 64 }).notNull(),
  resourceId: varchar("resource_id", { length: 36 }),
  details: text("details"),
  ipAddress: varchar("ip_address", { length: 45 }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
}, (t) => [
  index("ix_audit_user").on(t.userId),
  index("ix_audit_user_time").on(t.userId, t.createdAt),
]);

export const webhooks = pgTable("webhooks", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  url: varchar("url", { length: 2048 }).notNull(),
  events: varchar("events", { length: 512 }).notNull(),
  secret: varchar("secret", { length: 64 }).notNull(),
  isActive: boolean("is_active").notNull().default(true),
  lastTriggered: timestamp("last_triggered", { withTimezone: true }),
  failureCount: integer("failure_count").notNull().default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
}, (t) => [index("ix_webhooks_user").on(t.userId)]);

export const portfolios = pgTable("portfolios", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  name: varchar("name", { length: 128 }).notNull(),
  portfolioType: varchar("portfolio_type", { length: 32 }).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
}, (t) => [index("ix_portfolios_user").on(t.userId)]);

export const holdings = pgTable("holdings", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  portfolioId: varchar("portfolio_id", { length: 36 }).notNull().references(() => portfolios.id, { onDelete: "cascade" }),
  symbol: varchar("symbol", { length: 32 }).notNull(),
  name: varchar("name", { length: 128 }).notNull(),
  quantity: numeric("quantity", { precision: 14, scale: 4 }).notNull(),
  buyPrice: numeric("buy_price", { precision: 14, scale: 2 }).notNull(),
  currentPrice: numeric("current_price", { precision: 14, scale: 2 }).notNull().default("0"),
  assetType: varchar("asset_type", { length: 32 }).notNull(),
  purchaseDate: date("purchase_date", { mode: "string" }),
  notes: text("notes"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().$defaultFn(now).$onUpdateFn(now),
}, (t) => [index("ix_holdings_portfolio").on(t.portfolioId)]);

export const categoryCorrections = pgTable("category_corrections", {
  id: varchar("id", { length: 36 }).primaryKey().$defaultFn(uid),
  userId: varchar("user_id", { length: 64 }).notNull().references(() => users.id),
  descriptionHash: varchar("description_hash", { length: 64 }).notNull(),
  category: varchar("category", { length: 64 }).notNull(),
  correctionCount: integer("correction_count").notNull().default(1),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().$defaultFn(now),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().$defaultFn(now).$onUpdateFn(now),
}, (t) => [
  index("ix_category_corrections_user").on(t.userId),
  uniqueIndex("uq_cat_correction_user_hash").on(t.userId, t.descriptionHash),
]);
