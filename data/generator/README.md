# data/generator

Seeded synthetic-data generator (Faker, `--seed`): customers, accounts, 90 days of transactions, fixed personas, mailboxes, PDFs, and RAG articles. Identical seed => byte-identical DB dumps and ISO archive.

Defined in SPEC §16. Implemented in **M2**.

```
uv run python data/generator/generate.py --seed 42
```

`make seed` runs that command (override with `SEED=`). It writes `data/state/` and `data/manifest.json`, both gitignored, and a snapshot that `make reset` restores in under 30 seconds.
