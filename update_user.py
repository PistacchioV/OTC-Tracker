import duckdb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "apps", "db", "Users_OTCTracker.db")

VALID_ROLES   = {'', 'ADMIN', 'BO', 'FO', 'MO', 'INSTITUTIONAL'}
VALID_STATUSES = {'Active', 'Inactive', 'Pending'}


def list_users(conn):
    rows = conn.execute("SELECT SID, Name, Role, Status FROM users ORDER BY created_at DESC").fetchall()
    if not rows:
        print("No users found.")
        return
    print(f"\n{'SID':<10} {'Name':<30} {'Role':<15} {'Status'}")
    print("-" * 65)
    for sid, name, role, status in rows:
        print(f"{sid:<10} {name:<30} {role or '—':<15} {status}")
    print()


def update_user(conn, sid, role, status):
    user = conn.execute("SELECT SID, Name, Role, Status FROM users WHERE SID = ?", [sid]).fetchone()
    if not user:
        print(f"ERROR: SID '{sid}' not found.")
        return

    _, name, old_role, old_status = user
    print(f"\nUser: {name} ({sid})")
    print(f"  Role:   {old_role or '—'}  →  {role or '—'}")
    print(f"  Status: {old_status}  →  {status}")

    confirm = input("Confirm? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    conn.execute("UPDATE users SET Role = ?, Status = ? WHERE SID = ?", [role, status, sid])
    print("Updated successfully.")


def main():
    conn = duckdb.connect(DB_PATH)

    print("=== OTC Tracker — Update User ===")
    list_users(conn)

    sid = input("Enter SID: ").strip().upper()
    if not sid:
        print("No SID entered. Exiting.")
        conn.close()
        return

    print(f"\nValid roles:    {', '.join(sorted(VALID_ROLES)) or '(empty)'}")
    role = input("New Role (leave blank to clear): ").strip().upper()
    if role not in VALID_ROLES:
        print(f"ERROR: Invalid role '{role}'. Choose from: {', '.join(sorted(VALID_ROLES))}")
        conn.close()
        return

    print(f"\nValid statuses: {', '.join(sorted(VALID_STATUSES))}")
    status = input("New Status: ").strip().capitalize()
    if status not in VALID_STATUSES:
        print(f"ERROR: Invalid status '{status}'. Choose from: {', '.join(sorted(VALID_STATUSES))}")
        conn.close()
        return

    update_user(conn, sid, role, status)
    conn.close()


if __name__ == "__main__":
    main()
