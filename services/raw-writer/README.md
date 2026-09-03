# raw-writer/

Raw Writer service. Consumes `products.raw.v1` and persists raw/minimally transformed events as Bronze Parquet in the data lake. Must be independently restartable and replayable. See `ai/SPECIFICATION.md` §6.3.
