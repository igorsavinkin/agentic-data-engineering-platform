# ingestion/

Ingestion service. Executes source adapters and publishes canonical product observations to `products.raw.v1`. Owns source communication, authentication, pagination, retries/backoff, rate limiting, parsing, source-specific normalization, and source health information. Must not write directly to PostgreSQL. See `ai/SPECIFICATION.md` §6.1.
