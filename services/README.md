# services/

Service boundaries for the AI Data Platform. The seven services below are normative and defined in `ai/SPECIFICATION.md` §5; they must not be collapsed into one another without an ADR and human approval.

- `ingestion/` — source adapters and event publication
- `processor/` — validation, normalization, Polars transformations
- `raw-writer/` — Bronze Parquet persistence
- `lake-writer/` — Silver Parquet persistence
- `warehouse-loader/` — Gold Parquet to PostgreSQL loading
- `api/` — FastAPI serving layer
- `agent/` — LangGraph data-engineer agent
