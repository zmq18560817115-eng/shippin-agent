from orchestrator import queue, user_store


def test_password_is_hashed_and_authenticates(tmp_path):
    db_path = tmp_path / "users.db"
    queue.init_db(db_path)

    user = user_store.create_user("operator-1", "safe-password", db_path=db_path)

    with queue.get_conn(db_path) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    assert row["password_hash"] != "safe-password"
    assert row["password_hash"].startswith("pbkdf2_sha256$")
    assert user_store.authenticate("operator-1", "safe-password", db_path=db_path)["id"] == user["id"]
    assert user_store.authenticate("operator-1", "wrong-password", db_path=db_path) is None
    assert user["onboarding_completed"] == 0

    completed = user_store.complete_onboarding("operator-1", db_path=db_path)
    assert completed["onboarding_completed"] == 1


def test_duplicate_username_is_rejected_case_insensitively(tmp_path):
    db_path = tmp_path / "users.db"
    queue.init_db(db_path)
    user_store.create_user("Editor", "safe-password", db_path=db_path)

    try:
        user_store.create_user("editor", "other-password", db_path=db_path)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("duplicate username was accepted")


def test_existing_users_are_marked_onboarded_during_schema_upgrade(tmp_path):
    db_path = tmp_path / "legacy-users.db"
    with queue.get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO users (
                username, display_name, password_hash, role, status, created_at, updated_at
            ) VALUES ('legacy', '', 'hash', 'operator', 'active', '2026-01-01', '2026-01-01')
            """
        )

    queue.init_db(db_path)

    assert user_store.get_user_by_username("legacy", db_path=db_path)["onboarding_completed"] == 1
