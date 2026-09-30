import os

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "1")


def test_database_initializes_and_merges_settings(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.init_db()

    database.set_guild_data(123, {"welcome_enabled": True, "prefix": "!"})
    database.update_guild_data(123, welcome_enabled=False)

    assert database.get_guild_data(123) == {"welcome_enabled": False, "prefix": "!"}


def test_database_connection_rolls_back(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.init_db()

    try:
        with database.connection() as conn:
            conn.execute("INSERT INTO global_settings(key, value) VALUES(?, ?)", ("x", "y"))
            raise RuntimeError("rollback")
    except RuntimeError:
        pass

    assert database.get_global_setting("x") is None


def test_ticket_number_and_open_user_constraints(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.init_db()
    with database.connection() as conn:
        conn.execute("INSERT INTO tickets(guild_id, channel_id, user_id, status, ticket_number) VALUES(?,?,?,?,?)", (1, 10, 20, "open", 1))
        try:
            conn.execute("INSERT INTO tickets(guild_id, channel_id, user_id, status, ticket_number) VALUES(?,?,?,?,?)", (1, 11, 20, "open", 2))
        except Exception as exc:
            assert "UNIQUE" in str(exc).upper()
        else:
            raise AssertionError("duplicate open ticket was accepted")


def test_giveaway_duration_parser():
    from cogs.giveaways import parse_duration

    assert parse_duration("10m") == 600
    assert parse_duration("2H") == 7200
    for value in ("9s", "31d", "10minutes"):
        try:
            parse_duration(value)
        except ValueError:
            continue
        raise AssertionError(f"invalid duration accepted: {value}")
