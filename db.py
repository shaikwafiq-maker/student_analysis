import os
from decimal import Decimal

import mysql.connector


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def run_query(sql, params=(), fetch=False, one=False):
    """Run one parameterized SQL statement.
    SELECT  -> returns rows (fetch=True) or a single row (one=True)
    others  -> commits and returns (rows_affected, last_inserted_id)
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        if fetch:
            return cursor.fetchone() if one else cursor.fetchall()
        conn.commit()
        return cursor.rowcount, cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def to_json(data):
    """Turn MySQL Decimal values into normal numbers so JSON looks clean."""
    if isinstance(data, list):
        return [to_json(item) for item in data]
    if isinstance(data, dict):
        return {key: to_json(value) for key, value in data.items()}
    if isinstance(data, Decimal):
        return float(data)
    return data
