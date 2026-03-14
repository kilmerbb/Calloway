# PostgreSQL Stack Reference Guide (2025-2026)

**Research by:** Oracle (@research)
**Date:** 2026-03-14
**Scope:** PostgreSQL 16, pgvector, Supabase, asyncpg — optimization patterns for Calloway's multi-tenant SaaS architecture

---

## 1. PostgreSQL 16 — Query Optimization & Configuration

### 1.1 PG16 Planner Improvements

PostgreSQL 16 includes 10 query planner improvements enabled by default:
- **Incremental sort optimization** — exploits partially sorted result sets, reducing sort effort
- **LEFT JOIN removal** — now works with partitioned tables, particularly useful with views
- All improvements are applied automatically when the planner determines they will help

**Confidence: High** — [PostgreSQL 16 planner docs](https://www.citusdata.com/blog/2024/02/08/whats-new-in-postgres-16-query-planner-optimizer/)

### 1.2 Memory Configuration

| Parameter | Recommended Value | Notes |
|-----------|------------------|-------|
| `shared_buffers` | 25% of RAM | Shared memory for caching |
| `effective_cache_size` | 50-75% of RAM | Informs planner about OS cache availability |
| `work_mem` | 4-16 MB (OLTP) | Per-operation memory; keep low for high-concurrency |
| `random_page_cost` | 1.1-2.0 (SSD) | Lower from default 4 to favor index scans on SSDs |
| `maintenance_work_mem` | 256 MB-1 GB | Higher = faster index builds and VACUUM |

**Anti-pattern:** Setting `work_mem` too high with many concurrent connections. With 200 connections and `work_mem = 256MB`, a single complex query with multiple sorts could theoretically consume gigabytes.

### 1.3 Query Optimization Checklist

1. **Measure first** — enable `pg_stat_statements` to identify slow/frequent queries
2. **Use EXPLAIN ANALYZE** — understand execution plans before optimizing
3. **Avoid SELECT \*** — select only needed columns to reduce I/O
4. **Use indexed columns in WHERE** — ensure predicates align with available indexes
5. **Minimize complex joins** — restructure queries that join too many tables

### 1.4 Maintenance

- Configure autovacuum aggressively for high-write tables: lower `autovacuum_vacuum_scale_factor` (e.g., 0.05 instead of default 0.2)
- Run `ANALYZE` regularly to keep planner statistics current
- Monitor bloat on heavily updated tables

**Confidence: High** — [PostgreSQL Performance Tuning Best Practices 2025](https://www.mydbops.com/blog/postgresql-parameter-tuning-best-practices), [Instaclustr Top 10 Best Practices](https://www.instaclustr.com/education/postgresql/top-10-postgresql-best-practices-for-2025/)

---

## 2. Indexing Strategies

### 2.1 Index Type Selection

| Index Type | Use Case | Notes |
|-----------|----------|-------|
| **B-tree** (default) | Equality, range, sorting | Default; best for most queries |
| **GIN** | JSONB, arrays, full-text search | Multi-value columns |
| **BRIN** | Time-series, append-only tables | Tiny size; great for sequential data |
| **Hash** | Equality only | Rarely preferred over B-tree |

### 2.2 Key Practices

- **Partial indexes** — index only the rows that matter: `CREATE INDEX ON orders(status) WHERE status = 'pending'`
- **Expression indexes** — index computed values: `CREATE INDEX ON contacts(lower(email))`
- **Composite indexes** — put high-selectivity columns first
- **Monitor usage** — query `pg_stat_user_indexes` to find unused indexes (they slow writes)
- **CREATE INDEX CONCURRENTLY** — always use for production to avoid locking

### 2.3 For Calloway Specifically

Given our multi-tenant model with `tenant_id` on every table:
- Include `tenant_id` as the **leading column** in composite indexes (matches RLS filter)
- Use partial indexes for hot-path queries (e.g., active conversations, pending triggers)

**Confidence: High** — [PostgreSQL Index Documentation](https://www.postgresql.org/docs/current/indexes.html), [FreeCodeCamp Indexing Strategies](https://www.freecodecamp.org/news/postgresql-indexing-strategies/)

---

## 3. Connection Pooling

### 3.1 Why Pooling Is Essential

PostgreSQL creates a **process per connection**. At 200+ connections, context switching overhead degrades performance severely. Connection pooling maintains a small pool of actual database connections shared across application instances.

### 3.2 Pooling Modes

| Mode | Connection Returned | Use Case | Prepared Statements |
|------|-------------------|----------|-------------------|
| **Transaction** | After each transaction | Most web apps, serverless | Requires special handling |
| **Session** | When client disconnects | Long-lived connections, migrations | Supported |
| **Statement** | After each statement | Simple queries only | Not supported |

**Transaction mode** is recommended for Calloway's workload (short HTTP requests, background workers).

### 3.3 Supabase (Supavisor) Specifics

**Critical 2025 change:** Supabase deprecated session mode on port 6543 (Feb 2025). Current setup:
- **Port 6543** — Transaction mode only (via Supavisor)
- **Port 5432** — Direct connections / session mode

**Pool sizing rule:** If using Supabase PostgREST API heavily, limit pool to 40% of `max_connections`. Otherwise, up to 80% is fine. Reserve 20% for Auth server and utilities.

**Anti-pattern:** Using `SET SESSION` in transaction mode — use `SET LOCAL` instead (scoped to current transaction).

### 3.4 PgBouncer Configuration

If running your own PgBouncer:
- Pools are per (database, user) pair — 2 users × 2 databases = 4 pools
- `default_pool_size` should match your actual concurrent query needs (typically 10-20)
- Security: Update to PgBouncer 1.25.1+ (fixes CVE-2025-12819)

### 3.5 asyncpg Built-in Pool vs External Pooler

asyncpg includes its own connection pool that is often **preferred over PgBouncer** for async Python apps:

| Aspect | asyncpg pool | PgBouncer/Supavisor |
|--------|-------------|-------------------|
| Prepared statements | Full support (within acquire cycle) | Must disable (`statement_cache_size=0`) |
| Async native | Yes | Proxy layer adds latency |
| Setup | In-process | Separate service |
| Multi-app sharing | No (per-process) | Yes |

**Recommendation for Calloway:** Use Supavisor (transaction mode, port 6543) as the entry point, with asyncpg connecting through it. Set `statement_cache_size=0` on asyncpg to avoid prepared statement conflicts.

**Confidence: High** — [Supabase Connection Docs](https://supabase.com/docs/guides/database/connecting-to-postgres), [Supavisor FAQ](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI), [PgBouncer Best Practices](https://techcommunity.microsoft.com/blog/adforpostgresql/pgbouncer-best-practices-in-azure-database-for-postgresql-%E2%80%93-part-1/4453323)

---

## 4. asyncpg Best Practices

### 4.1 Pool Configuration

```python
pool = await asyncpg.create_pool(
    dsn=DATABASE_URL,
    min_size=5,             # Pre-established connections
    max_size=20,            # Max concurrent connections
    max_queries=50000,      # Recycle connections after N queries
    max_inactive_connection_lifetime=300,  # Close idle connections after 5 min
    statement_cache_size=0,  # REQUIRED when using external pooler (Supavisor/PgBouncer)
)
```

**Pool sizing formula:** `max_size = expected_concurrency × 1.5`, targeting 70-85% utilization at peak.

### 4.2 Connection Lifecycle

Always use `async with` for automatic acquire/release:

```python
async with pool.acquire() as conn:
    async with conn.transaction():
        result = await conn.fetchval('SELECT count(*) FROM contacts WHERE tenant_id = $1', tenant_id)
```

### 4.3 Prepared Statements

- asyncpg maintains an **automatic LRU cache** for `fetch()`, `fetchrow()`, `fetchval()` — manual `prepare()` is rarely needed
- **Critical:** Prepared statements become invalid when a connection is released back to the pool
- When using external poolers, **always** set `statement_cache_size=0`

### 4.4 Batch Operations

Use `executemany()` for bulk inserts/updates:

```python
async with pool.acquire() as conn:
    await conn.executemany(
        'INSERT INTO messages(tenant_id, contact_id, body) VALUES($1, $2, $3)',
        list_of_tuples
    )
```

### 4.5 RLS Context Setting

For Calloway's RLS pattern with Supavisor transaction mode:

```python
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute("SET LOCAL app.tenant_id = $1", tenant_id)
        # All subsequent queries in this transaction are tenant-scoped
        rows = await conn.fetch("SELECT * FROM contacts")
```

`SET LOCAL` is scoped to the current transaction only — safe with connection pooling.

### 4.6 Performance

2025 benchmarks: asyncpg achieves ~18k QPS vs ~3k for synchronous approaches (5.7x improvement). 2.1x memory efficiency via async multiplexing.

**Confidence: High** — [asyncpg Documentation](https://magicstack.github.io/asyncpg/current/api/index.html), [asyncpg FAQ](https://magicstack.github.io/asyncpg/current/faq.html), [Tiger Data asyncpg Guide](https://www.tigerdata.com/blog/how-to-build-applications-with-asyncpg-and-postgresql)

---

## 5. Row-Level Security (RLS) for Multi-Tenancy

### 5.1 Recommended Pattern

```sql
-- Enable RLS
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts FORCE ROW LEVEL SECURITY;  -- Critical: also applies to table owner

-- Create policy using session variable
CREATE POLICY tenant_isolation ON contacts
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

**Key design decisions:**
- Use runtime session variables (`SET LOCAL app.tenant_id`), NOT per-tenant database users
- Apply `FORCE ROW LEVEL SECURITY` — without it, table owners and superusers bypass RLS
- Create a dedicated `app_user` role (non-owner) for application connections
- Enable RLS on **every** table containing tenant data

### 5.2 Performance Implications

- Simple `tenant_id = current_setting(...)` policies add minimal overhead (essentially an automatic WHERE clause)
- **Ensure `tenant_id` is the leading column in indexes** — the RLS policy becomes an implicit filter on every query
- Complex policies (subqueries, function calls) can significantly degrade performance
- RLS does NOT limit per-tenant resource consumption (CPU, memory, disk) — only row access

### 5.3 Policy Combination Rules

- Multiple permissive policies (default) combine with **OR** — if any policy allows, row is visible
- Restrictive policies (`AS RESTRICTIVE`) combine with **AND**
- For Calloway's simple tenant isolation, a single permissive policy per table is sufficient

### 5.4 Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Forgetting `FORCE ROW LEVEL SECURITY` | Table owners bypass all policies | Always add FORCE |
| Not resetting session context | Cross-tenant data leakage | Use `SET LOCAL` (auto-resets on transaction end) |
| Complex policy expressions | Query performance degradation | Keep policies to simple equality checks |
| Missing index on `tenant_id` | Full table scans on every query | `tenant_id` must be leading index column |
| Using RLS as sole auth layer | Insufficient for complex permissions | Layer with application-level authorization |

### 5.5 RLS + AI-Generated Queries

RLS is **especially critical** when SQL queries are generated by AI/LLM systems (as in Calloway). The database-level enforcement prevents any malformed or adversarial query from leaking tenant data, regardless of application-layer bugs.

**Confidence: High** — [AWS RLS Guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/rls.html), [Crunchy Data RLS for Tenants](https://www.crunchydata.com/blog/row-level-security-for-tenants-in-postgres), [Permit.io RLS Guide](https://www.permit.io/blog/postgres-rls-implementation-guide)

---

## 6. pgvector — Vector Search Optimization

### 6.1 Index Types Comparison

| Aspect | HNSW | IVFFlat |
|--------|------|---------|
| Query speed | Faster (logarithmic scaling) | Slower (linear with probes) |
| Build time | Much slower (30x) | Fast |
| Memory usage | 2-5x more | Lower |
| Needs training data | No | Yes (build after data loaded) |
| Update handling | Good (incremental) | Poor (requires rebuild) |
| **Recommended for** | **Most use cases** | Large static datasets, memory-constrained |

**Default recommendation: HNSW** — less tuning required, handles writes well, better recall.

### 6.2 HNSW Tuning Parameters

| Parameter | Default | Recommended Start | Notes |
|-----------|---------|------------------|-------|
| `m` | 16 | 16 | Max connections per layer; higher = better recall, more memory |
| `ef_construction` | 64 | 200 | Build-time candidate list; higher = better graph quality |
| `hnsw.ef_search` | 40 | 100-200 | Query-time candidate list; tune for speed/recall tradeoff |

```sql
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- At query time:
SET hnsw.ef_search = 100;
```

### 6.3 IVFFlat Tuning (If Used)

- `lists` = rows / 1000 (up to 1M rows) or rows / 200 for better recall
- `probes` = 10-50 at query time (default 1 gives terrible recall)
- **Only build after data is loaded** — IVFFlat quality depends on training data

### 6.4 Distance Metrics

| Metric | Operator | Index Ops Class | Best For |
|--------|----------|----------------|----------|
| Cosine | `<=>` | `vector_cosine_ops` | Text/document embeddings (default choice) |
| L2 (Euclidean) | `<->` | `vector_l2_ops` | Spatial data, image features |
| Inner Product | `<#>` | `vector_ip_ops` | Pre-normalized vectors (best performance) |

**Critical anti-pattern:** Index/operator mismatch. If your index uses `vector_cosine_ops` but your query uses `<->` (L2), PostgreSQL silently falls back to sequential scan. No error — just catastrophic performance (5ms vs 30s on 1M rows).

**For Calloway:** Use cosine distance (`<=>`) with `vector_cosine_ops`. If using OpenAI or Anthropic embeddings (which are normalized), inner product gives equivalent results with slightly better performance.

### 6.5 Dimension Considerations

- pgvector supports up to **2000 dimensions** for indexed columns
- Fewer dimensions = less storage, faster queries, less memory
- OpenAI `text-embedding-3-small`: 1536 dims (can be truncated to 512 or 256)
- At 1536 dims, each vector = ~6 KB; at 50M vectors = 300 GB + 2-3x index overhead
- **For Calloway's scale** (thousands of contacts/conversations, not millions): 1536 dims is fine

### 6.6 pgvector vs Dedicated Vector DBs

| Criteria | pgvector | Pinecone / Weaviate |
|----------|----------|-------------------|
| < 1M vectors | Excellent | Overkill |
| 1-100M vectors | Good (with pgvectorscale) | Good |
| > 100M vectors | Struggles | Purpose-built |
| Transactional consistency | Full ACID | Eventually consistent |
| Operational complexity | None (same DB) | Additional service |
| Cost | Free (open source) | $70-700+/month |
| Hybrid relational+vector | Native | Requires joins across systems |

**For Calloway:** pgvector is the clear choice. Our vector corpus (contact notes, conversation embeddings, listing descriptions) will remain well under 1M vectors. Keeping vectors in PostgreSQL gives us transactional consistency and eliminates an external dependency.

**Confidence: High** — [pgvector GitHub](https://github.com/pgvector/pgvector), [Neon pgvector Optimization](https://neon.com/docs/ai/ai-vector-search-optimization), [AWS pgvector Deep Dive](https://aws.amazon.com/blogs/database/optimize-generative-ai-applications-with-pgvector-indexing-a-deep-dive-into-ivfflat-and-hnsw-techniques/), [pgvector vs Dedicated DBs](https://zenvanriel.com/ai-engineer-blog/pgvector-vs-dedicated-vector-db/)

---

## 7. Schema Migration Best Practices

### 7.1 Zero-Downtime Migration Techniques

1. **Always set `lock_timeout`** — prevents DDL from blocking all queries indefinitely
   ```sql
   SET lock_timeout = '5s';
   ```
2. **CREATE INDEX CONCURRENTLY** — non-blocking index creation
3. **Add columns with defaults** — PG11+ adds columns with defaults without rewriting the table
4. **NOT VALID constraints** — add constraint without validating existing rows, validate later
   ```sql
   ALTER TABLE contacts ADD CONSTRAINT valid_email CHECK (email ~* '^.+@.+$') NOT VALID;
   -- Later, during low traffic:
   ALTER TABLE contacts VALIDATE CONSTRAINT valid_email;
   ```
5. **Expand-and-contract pattern** — add new schema alongside old, migrate data, remove old

### 7.2 Multi-Tenant Schema Design Rules

- **`tenant_id` on every tenant table** — denormalize deliberately for isolation and future sharding
- **Always join on `tenant_id`** — even if logically redundant, it enables partition pruning and index usage
- **Composite primary keys** — `(tenant_id, id)` enables future partitioning by tenant

### 7.3 Tools

- **pgroll** (by Xata) — safe, reversible migrations with dual-schema versioning
- **Framework migrations** (Alembic for Python/SQLAlchemy) — good for smaller scale
- **Bytebase** — collaborative schema change management

### 7.4 Future Scaling Path

Start with shared schema on single PostgreSQL instance. If scale demands it:
- **Citus extension** — transparent sharding by `tenant_id`, turns PG into distributed DB
- **Schema-based sharding** — move high-value tenants to dedicated schemas
- Calloway's current scale does not require sharding; the shared-schema + RLS model is appropriate

**Confidence: High** — [Xata Zero-Downtime Migrations](https://xata.io/blog/zero-downtime-schema-migrations-postgresql), [Bytebase Migration Guide](https://www.bytebase.com/blog/postgres-schema-migration-without-downtime/), [Crunchy Data Multi-Tenancy](https://www.crunchydata.com/blog/designing-your-postgres-database-for-multi-tenancy)

---

## 8. Anti-Patterns Summary

| Anti-Pattern | Why It's Bad | Correct Approach |
|-------------|-------------|-----------------|
| High `work_mem` with many connections | Memory exhaustion | 4-16 MB for OLTP |
| `SELECT *` everywhere | Wasted I/O and bandwidth | Select specific columns |
| Missing `FORCE ROW LEVEL SECURITY` | Superusers/owners bypass RLS | Always add FORCE |
| `SET SESSION` with transaction pooling | Session state leaks across requests | Use `SET LOCAL` |
| IVFFlat index built on empty table | Terrible recall | Load data first, then build |
| pgvector index/operator mismatch | Silent sequential scan fallback | Match index ops class to query operator |
| Not setting `statement_cache_size=0` with pooler | Prepared statement errors | Always disable when using Supavisor/PgBouncer |
| Unused indexes | Slows writes, wastes storage | Monitor `pg_stat_user_indexes`, drop unused |
| Complex RLS policies with subqueries | Query plan degradation | Simple equality checks only |
| `CREATE INDEX` without `CONCURRENTLY` | Locks table for duration of build | Always use CONCURRENTLY in production |

---

## 9. Calloway-Specific Recommendations

Based on this research, here are actionable recommendations for Calloway:

### Immediate

1. **Verify RLS configuration** — ensure `FORCE ROW LEVEL SECURITY` is set on all tenant tables
2. **Audit indexes** — confirm `tenant_id` is the leading column in all composite indexes
3. **Set `statement_cache_size=0`** on asyncpg if connecting through Supavisor
4. **Use `SET LOCAL app.tenant_id`** in every transaction (never `SET SESSION`)

### Connection Architecture

5. **Connect via Supavisor port 6543** (transaction mode) for all application traffic
6. **Pool sizing:** asyncpg `max_size` = 15-20 for the application; leave headroom for Supabase Auth and PostgREST
7. **Set `idle_in_transaction_session_timeout`** on the database to prevent connection starvation

### pgvector

8. **Use HNSW indexes** with `vector_cosine_ops` for all embedding columns
9. **Start with defaults** (`m=16`, `ef_construction=64`) and tune only if recall is insufficient
10. **Stick with pgvector** — Calloway's scale does not justify a dedicated vector database

### Migrations

11. **Always use `lock_timeout` and `CONCURRENTLY`** for DDL in production
12. **Adopt expand-and-contract** for schema changes affecting tenant data
13. **Keep `tenant_id` on every new table** from day one

---

## Sources

- [PostgreSQL 16 Query Planner — Citus Data](https://www.citusdata.com/blog/2024/02/08/whats-new-in-postgres-16-query-planner-optimizer/)
- [PostgreSQL Performance Tuning Best Practices 2025 — Mydbops](https://www.mydbops.com/blog/postgresql-parameter-tuning-best-practices)
- [Top 10 PostgreSQL Best Practices 2025 — Instaclustr](https://www.instaclustr.com/education/postgresql/top-10-postgresql-best-practices-for-2025/)
- [PostgreSQL Indexing Strategies — FreeCodeCamp](https://www.freecodecamp.org/news/postgresql-indexing-strategies/)
- [PgBouncer Configuration](https://www.pgbouncer.org/config.html)
- [PgBouncer Best Practices — Azure](https://techcommunity.microsoft.com/blog/adforpostgresql/pgbouncer-best-practices-in-azure-database-for-postgresql-%E2%80%93-part-1/4453323)
- [Connection Pooling Best Practices — Azure](https://learn.microsoft.com/en-us/azure/postgresql/connectivity/concepts-connection-pooling-best-practices)
- [AWS RLS Recommendations](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/rls.html)
- [AWS Multi-Tenant RLS Guide](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/)
- [Postgres RLS Implementation Guide — Permit.io](https://www.permit.io/blog/postgres-rls-implementation-guide)
- [RLS for Tenants — Crunchy Data](https://www.crunchydata.com/blog/row-level-security-for-tenants-in-postgres)
- [RLS Limitations — Bytebase](https://www.bytebase.com/blog/postgres-row-level-security-limitations-and-alternatives/)
- [Multi-Tenant RLS — Nile](https://www.thenile.dev/blog/multi-tenant-rls)
- [pgvector GitHub Repository](https://github.com/pgvector/pgvector)
- [pgvector Search Optimization — Neon](https://neon.com/docs/ai/ai-vector-search-optimization)
- [pgvector Indexing Deep Dive — AWS](https://aws.amazon.com/blogs/database/optimize-generative-ai-applications-with-pgvector-indexing-a-deep-dive-into-ivfflat-and-hnsw-techniques/)
- [pgvector HNSW vs IVFFlat — Medium](https://medium.com/@bavalpreetsinghh/pgvector-hnsw-vs-ivfflat-a-comprehensive-study-21ce0aaab931)
- [pgvector Distance Functions — DEV Community](https://dev.to/philip_mcclarence_2ef9475/pgvector-distance-functions-cosine-vs-l2-vs-inner-product-57pd)
- [pgvector vs Dedicated Vector DBs](https://zenvanriel.com/ai-engineer-blog/pgvector-vs-dedicated-vector-db/)
- [pgvector vs Pinecone — Tiger Data](https://www.tigerdata.com/blog/pgvector-vs-pinecone)
- [Supabase Connection Docs](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supavisor FAQ — Supabase](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI)
- [Supavisor Session Mode Deprecation — GitHub](https://github.com/orgs/supabase/discussions/32755)
- [Supabase Connection Management](https://supabase.com/docs/guides/database/connection-management)
- [asyncpg API Reference](https://magicstack.github.io/asyncpg/current/api/index.html)
- [asyncpg FAQ](https://magicstack.github.io/asyncpg/current/faq.html)
- [asyncpg Pool Source](https://magicstack.github.io/asyncpg/current/_modules/asyncpg/pool.html)
- [Building Apps with asyncpg — Tiger Data](https://www.tigerdata.com/blog/how-to-build-applications-with-asyncpg-and-postgresql)
- [Zero-Downtime Schema Migrations — Xata](https://xata.io/blog/zero-downtime-schema-migrations-postgresql)
- [Schema Migration Without Downtime — Bytebase](https://www.bytebase.com/blog/postgres-schema-migration-without-downtime/)
- [Designing Postgres for Multi-Tenancy — Crunchy Data](https://www.crunchydata.com/blog/designing-your-postgres-database-for-multi-tenancy)
