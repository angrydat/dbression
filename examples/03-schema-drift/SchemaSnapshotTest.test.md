# Lock the public shape of `customer`

The `Inspect Table` fixture queries `information_schema.columns` (PG/MSSQL) or
`all_tab_columns` (Oracle) and compares the result against the expected rows below.
A new column, a renamed column, a different data type — anything that drifts will
fail this test loudly.

This is the *anti-flake* DBFit pattern: instead of writing a brittle `SELECT *` test
that just checks values, you pin down the contract.

### Inspect Table pg_temp.customer

| column_name | data_type                |
|-------------|--------------------------|
| id          | integer                  |
| email       | text                     |
| created_at  | timestamp with time zone |
