# lake-writer/

Lake Writer service. Consumes `products.validated.v1` and persists validated/normalized records as Silver Parquet. Owns the validated-event-to-Silver boundary and is not coupled to PostgreSQL. See `ai/SPECIFICATION.md` §6.4.
