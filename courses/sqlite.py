"""Réglages SQLite pour limiter « database is locked » (admin + tâches PDF, Windows)."""

from django.db.backends.signals import connection_created


def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=60000;")


def register_sqlite_pragmas():
    connection_created.connect(
        configure_sqlite_connection,
        dispatch_uid="cour_ligne_sqlite_pragmas",
    )
