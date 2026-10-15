# Moving data between databases

There are two tools. Pick by what has to move.

| Need | Tool | Moves users and logins |
|---|---|---|
| Move a whole database (new host, provider change, disaster recovery) | `pg_dump` / `pg_restore`, below | Yes |
| Copy the business data between environments (for example production to staging) | **Settings → Data snapshot** in the app (Admin only) | No |

The app-level snapshot never carries credentials. It exports teams, employees, performance records and KPI values,
evaluation configuration, plans, actions and upload metadata, and it names users only by id and username. On import,
each named user is matched to an existing account with the same username. Accounts are never created by an import.
Create the accounts first, or use the full move below.

## Full database move with pg_dump / pg_restore

Run these from an operator machine with the PostgreSQL client tools, at the same major version as the server or newer.
Both URLs come from the deployment secrets. Never paste them into a ticket or a chat.

1. **Freeze writes.** Stop the backend and the worker, so no upload or job changes the source during the dump:

   ```bash
   docker compose --env-file DevOps/.env.hostinger -f compose.production.yml stop backend worker
   ```

2. **Check the schema revision** of the source. The target must end up at the same Alembic revision:

   ```bash
   psql "$SOURCE_DATABASE_URL" -At -c "SELECT version_num FROM alembic_version"
   ```

3. **Dump** in the custom format. It is compressed and lets `pg_restore` pick objects. No ownership or grants, because
   the target has its own roles:

   ```bash
   pg_dump "$SOURCE_DATABASE_URL" --format=custom --no-owner --no-privileges --file=pms-move.dump
   ```

   The dump holds password hashes and refresh-session hashes. Treat it as a secret: keep it on an encrypted disk,
   never commit it, never upload it to a shared drive.

4. **Restore** into an empty target database:

   ```bash
   pg_restore --dbname="$TARGET_DATABASE_URL" --no-owner --no-privileges --exit-on-error --single-transaction pms-move.dump
   ```

   `--single-transaction` makes the restore all or nothing. If it fails, the target is left empty, so fix the cause and run it again.

5. **Verify** the revision and a few counts on both sides:

   ```bash
   psql "$TARGET_DATABASE_URL" -At -c "SELECT version_num FROM alembic_version"
   for table in teams employees performance_records kpi_values actions users; do
     echo "$table: $(psql "$SOURCE_DATABASE_URL" -At -c "SELECT count(*) FROM $table") -> $(psql "$TARGET_DATABASE_URL" -At -c "SELECT count(*) FROM $table")"
   done
   ```

6. **Revoke the copied sessions** in the target, so a refresh token from the old host cannot be used on the new one:

   ```bash
   psql "$TARGET_DATABASE_URL" -c "UPDATE refresh_sessions SET revoked_at = now(), revocation_reason = 'database_move' WHERE revoked_at IS NULL"
   ```

7. **Point the app at the target.** Update `DATABASE_URL` in the deployment secrets, run the migrations (a no-op when the
   revisions match), and start the stack:

   ```bash
   DevOps/scripts/migrate.sh
   docker compose --env-file DevOps/.env.hostinger -f compose.production.yml up -d
   ```

8. **Delete the dump** once the target is verified:

   ```bash
   shred -u pms-move.dump   # or: rm -P on macOS; delete and empty the recycle bin on Windows
   ```

## Copying business data with the app snapshot

1. On the source, as an Admin: **Settings → Data snapshot → Download snapshot**. The file streams to your browser and
   is not stored on the server. Every export writes an audit entry with the row counts.
2. On the target, as an Admin: choose the file and a conflict policy, then **Check file**. The dry run shows per-table
   counts, existing ids, business-key conflicts, accounts that are missing and the revision check, and it saves nothing.
   - **Skip** keeps the target's rows where an id already exists.
   - **Replace** overwrites them with the snapshot's rows.
   - A business key that would be held twice (for example the same employee and month under two ids) always blocks
     the import. So does a required owner whose username has no account in the target.
3. **Import** commits everything in one transaction, or nothing. It writes an audit entry with the counts.
4. Delete the downloaded file from your computer when you are done.

Both databases must be at the same Alembic revision. The import refuses a snapshot from another revision. Migrate the
older database first, then export again.
