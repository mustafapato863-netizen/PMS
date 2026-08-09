import os
from sqlalchemy import create_engine, text


def required_database_url(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required and must be supplied through the environment")
    if not value.lower().startswith(("postgresql://", "postgresql+")):
        raise RuntimeError(f"{name} must be a PostgreSQL connection string")
    return value

def normalize_emp_id(id_str: str) -> str:
    if not id_str:
        return ""
    cleaned = str(id_str).strip().upper()
    if cleaned.startswith("SGHD"):
        cleaned = cleaned[4:]
    if cleaned.endswith(".0"):
        cleaned = cleaned[:-2]
    return cleaned.lstrip("0")

def main():
    local_db = required_database_url("LOCAL_DATABASE_URL")
    remote_db = required_database_url("REMOTE_DATABASE_URL")

    print("Connecting to local database...")
    engine_local = create_engine(local_db)
    print("Connecting to remote Supabase database...")
    engine_remote = create_engine(remote_db)

    with engine_local.connect() as conn_local, engine_remote.connect() as conn_remote:
        print("Fetching reference mappings...")

        # 1. TEAMS mapping by name / db_name
        local_teams = conn_local.execute(text("SELECT id, name, db_name FROM teams")).fetchall()
        remote_teams = conn_remote.execute(text("SELECT id, name, db_name FROM teams")).fetchall()

        remote_team_name_map = {}
        for r_id, r_name, r_dbname in remote_teams:
            if r_name:
                remote_team_name_map[r_name.lower().replace("_", "").replace(" ", "")] = r_id
            if r_dbname:
                remote_team_name_map[r_dbname.lower().replace("_", "").replace(" ", "")] = r_id

        team_id_map = {}
        for l_id, l_name, l_dbname in local_teams:
            matched_r_id = None
            if l_name:
                matched_r_id = remote_team_name_map.get(l_name.lower().replace("_", "").replace(" ", ""))
            if not matched_r_id and l_dbname:
                matched_r_id = remote_team_name_map.get(l_dbname.lower().replace("_", "").replace(" ", ""))
            team_id_map[l_id] = matched_r_id

        # 2. EMPLOYEES mapping by normalized employee_id
        local_emps = conn_local.execute(text("SELECT id, employee_id FROM employees")).fetchall()
        remote_emps = conn_remote.execute(text("SELECT id, employee_id FROM employees")).fetchall()

        remote_emp_map = {}
        for r_id, r_empid in remote_emps:
            if r_empid:
                norm = normalize_emp_id(r_empid)
                if norm:
                    remote_emp_map[norm] = r_id

        emp_id_map = {}
        for l_id, l_empid in local_emps:
            if l_empid:
                norm = normalize_emp_id(l_empid)
                if norm and norm in remote_emp_map:
                    emp_id_map[l_id] = remote_emp_map[norm]

        # 3. USERS mapping by username
        local_users = conn_local.execute(text("SELECT id, username FROM users")).fetchall()
        remote_users = conn_remote.execute(text("SELECT id, username FROM users")).fetchall()

        remote_user_map = {r_username.lower(): r_id for r_id, r_username in remote_users if r_username}
        default_admin_id = remote_user_map.get("super") or (remote_users[0][0] if remote_users else None)

        user_id_map = {}
        for l_id, l_username in local_users:
            if l_username and l_username.lower() in remote_user_map:
                user_id_map[l_id] = remote_user_map[l_username.lower()]
            else:
                user_id_map[l_id] = default_admin_id

        # 4. Fetch local actions
        local_actions = conn_local.execute(text("SELECT * FROM actions")).fetchall()
        if not local_actions:
            print("No actions found in local database.")
            return

        res = conn_local.execute(text("SELECT * FROM actions LIMIT 0"))
        columns = list(res.keys())

        print(f"Found {len(local_actions)} local actions to migrate...")

        success_count = 0
        skipped_count = 0

        for row in local_actions:
            row_dict = dict(zip(columns, row))

            # Remap team_id
            l_team_id = row_dict.get("team_id")
            r_team_id = team_id_map.get(l_team_id)
            if not r_team_id:
                print(f"  - Skipping action {row_dict['id']}: team_id {l_team_id} could not be mapped to remote team.")
                skipped_count += 1
                continue
            row_dict["team_id"] = r_team_id

            # Remap employee_id (optional if NULL in remote, but required if present)
            l_emp_id = row_dict.get("employee_id")
            if l_emp_id:
                row_dict["employee_id"] = emp_id_map.get(l_emp_id)

            # Remap users
            for u_col in ["created_by_user_id", "updated_by_user_id", "owner_user_id"]:
                if row_dict.get(u_col):
                    row_dict[u_col] = user_id_map.get(row_dict[u_col], default_admin_id)

            # Reset plan_id / objective_id to None if foreign key isn't present
            row_dict["plan_id"] = None
            row_dict["objective_id"] = None

            cols_str = ", ".join(columns)
            binds_str = ", ".join([f":{col}" for col in columns])
            query = text(f"INSERT INTO actions ({cols_str}) VALUES ({binds_str}) ON CONFLICT (id) DO NOTHING")

            try:
                conn_remote.execute(query, row_dict)
                success_count += 1
            except Exception as e:
                print(f"Error inserting action {row_dict['id']}: {e}")
                skipped_count += 1

        conn_remote.commit()
        print("\nMigration finished successfully!")
        print(f"   - Migrated actions: {success_count}")
        print(f"   - Skipped actions: {skipped_count}")

if __name__ == "__main__":
    main()
