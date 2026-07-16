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
