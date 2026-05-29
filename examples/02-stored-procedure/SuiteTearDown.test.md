# Teardown

The whole suite ran inside a single transaction. Roll it back to leave the database
untouched — even the temp table and function disappear.

### DatabaseEnvironment

| rollback |
|----------|
