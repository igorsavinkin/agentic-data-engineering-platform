# warehouse-loader/

Warehouse Loader service. Loads curated Gold Parquet datasets into PostgreSQL with idempotent loading that preserves the historical observation model. It is the only component responsible for the Parquet-to-PostgreSQL loading boundary. See `ai/SPECIFICATION.md` §6.5.
