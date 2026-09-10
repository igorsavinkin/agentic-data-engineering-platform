# processor/

Processor service. Consumes `products.raw.v1`, validates and normalizes observations, applies Polars transformations and deduplication, publishes valid records to `products.validated.v1`, and routes invalid records to `products.invalid.v1` with diagnostic context. Does not write directly to PostgreSQL. See `ai/SPECIFICATION.md` §6.2.
