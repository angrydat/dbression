# Setup — a temp table and a procedure to test

Both DDL statements run inside the same suite transaction as the test, so they vanish
when SuiteTearDown rolls back.

### Execute

```sql
CREATE TEMP TABLE counter (id integer GENERATED ALWAYS AS IDENTITY, label text, hits integer NOT NULL DEFAULT 0)
```

### Execute

```sql
CREATE OR REPLACE FUNCTION bump_counter(p_label text)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE counter SET hits = hits + 1 WHERE label = p_label;
END;
$$
```
