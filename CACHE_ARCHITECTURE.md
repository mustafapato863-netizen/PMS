# Cache Architecture

Date: 2026-07-29

## Current layers

| Layer | Scope | TTL/retention | Invalidation | Risk |
|---|---|---|---|---|
| TanStack Query | Browser tab/application | 2 min stale, 10 min GC | mutations plus awaited cancel/clear at session boundary | Isolated on logout and terminal 401 |
| Serialization cache | Backend process | 5 min | explicit global clear only | Process-local and not user-scoped |
| CacheService Redis | Shared when Redis works; lazy connection | endpoint-defined | key/prefix/pub-sub helpers | Key scope is incomplete |
| CacheService fallback | One backend process | bounded LRU | local only | Diverges across instances |
| Config loader | None before optimisation | N/A | N/A | Re-reads and validates files per record |

## Cacheability rules

| Data | Cacheable | Required key dimensions |
|---|---|---|
| Static team JSON config | Yes | resolved file path, mtime/content version |
| Public schema/registry | Yes | application version |
| Authorized filter options | Conditional | user authorization fingerprint, config version, data version |
| Team performance | Conditional | logical team, level, position, region, period, configuration version, scope |
| Employee performance | Conditional | employee, period, configuration version, authorization scope |
| Generated reports | Persist, do not treat as ephemeral cache | immutable report/version ID |
| Presence | No as process cache authority | durable `last_seen_at`; socket is best-effort |

## Unsafe current key examples

- `team_performance:{team}:{month}:{year}` omits region, performance level, position, configuration version and user scope.
- `performance:{employee}:{month}:{year}` assumes employee identity alone captures authorization and configuration.

These keys must not wrap scoped response bodies until their dimensions are complete.

## Proposed configuration cache

- Cache parsed and validated configuration by canonical file path plus `mtime_ns` and size.
- Return an isolated copy so callers cannot mutate shared cached data.
- A file replacement or edit naturally changes the key.
- Bound the cache and expose a clear function for tests/onboarding writes.
- Cache all-config discovery by a directory signature rather than a permanent process lifetime.
- Do not cache validation failures.

Status: implemented and measured on 2026-07-29.

## Redis connection lifecycle

- One shared proxy is imported by auth, RBAC, cache, monitoring, and health code.
- Construction performs no network I/O.
- First feature use connects with a bounded timeout.
- Connection or command failure starts a retry cooldown and allows the caller's existing database/JWT/in-memory fallback.
- Redis is an optimization/session-revocation accelerator, not the source of performance or authorization truth.

## Stampede and TTL policy

For Redis-backed derived views:

- base TTL: 120–300 seconds depending on freshness requirement,
- add 10–20% random jitter,
- use a short lock/single-flight for expensive recomputation,
- serve stale data only when the response explicitly carries an `as_of` time and authorization remains valid,
- never use `FLUSHDB` in a request path,
- record cache hit/miss/recompute duration.

## Invalidation events

Invalidate affected keys after:

- successful PMS upload promotion,
- upload deletion/rollback,
- KPI config publication,
- employee assignment/deactivation,
- corrective action mutation if present in the cached response,
- permission/team assignment change,
- report/config version activation.

Invalidation must happen after transaction commit. Failed transactions must not evict or publish a new data version as if the mutation succeeded.

## Browser cache isolation

On logout or terminal 401:

1. cancel active queries,
2. clear TanStack Query data,
3. clear authentication storage,
4. redirect to login.

Do not persist user-scoped query data across authenticated users unless the storage namespace includes a stable user ID and is encrypted/approved.

Status: implemented for logout, invalid stored JWT, and terminal non-login 401.

## Metrics

Track by cache name, not raw employee identifiers:

- hit/miss/error,
- lookup latency,
- compute latency,
- entry count/bytes,
- invalidation reason,
- stale serves,
- lock wait/contention,
- fallback-to-local occurrences.
