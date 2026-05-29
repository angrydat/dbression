# Setup — a versioned table we want to lock down

This temp table is the contract that the SchemaSnapshotTest will pin down. It exists
only for the duration of the suite transaction.

### Execute

```sql
CREATE TEMP TABLE customer (
  id          serial PRIMARY KEY,
  email       text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
)
```
