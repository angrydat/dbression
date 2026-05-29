# Bump counter

Demonstrates four DBFit conventions back-to-back:

1. **Insert** with a capture column (`>>row_id`) — Postgres `RETURNING` is generated automatically.
2. **Set Parameter** stores a constant in the symbol table.
3. **Execute Procedure** is dialect-aware: `SELECT name(args)` on Postgres, `EXEC name args` on SQL Server, `BEGIN name(args); END;` on Oracle.
4. **Query** with `<<symbol_read` inside the expected cell, and `:bind` inside the SQL.

### Insert counter

| label   | >>row_id |
|---------|----------|
| widgets |          |

### Set Parameter expected_hits 3

### Execute Procedure bump_counter p_label

| p_label |
|---------|
| widgets |
| widgets |
| widgets |

### Query

```sql
select hits from counter where id = :row_id
```

| hits           |
|----------------|
| <<expected_hits|
