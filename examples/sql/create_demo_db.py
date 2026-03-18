from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    db_path = base_dir / "demo.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.executescript(
        """
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            city TEXT NOT NULL,
            segment TEXT NOT NULL
        );

        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        );

        CREATE TABLE order_items (
            order_item_id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (order_id)
        );
        """
    )

    customers = [
        (1, "Ana Ruiz", "Bogota", "enterprise"),
        (2, "Carlos Mejia", "Medellin", "midmarket"),
        (3, "Luisa Torres", "Cali", "smb"),
        (4, "Jorge Perez", "Bogota", "enterprise"),
    ]
    orders = [
        (1001, 1, "2026-03-01", "paid"),
        (1002, 1, "2026-03-03", "shipped"),
        (1003, 2, "2026-03-04", "cancelled"),
        (1004, 3, "2026-03-05", "paid"),
        (1005, 4, "2026-03-07", "paid"),
        (1006, 4, "2026-03-09", "cancelled"),
    ]
    order_items = [
        (1, 1001, "Curso LangGraph", 2, 120.0),
        (2, 1001, "Workshop Kit", 1, 40.0),
        (3, 1002, "Curso LangGraph", 1, 120.0),
        (4, 1003, "Consultoria", 1, 300.0),
        (5, 1004, "Workshop Kit", 3, 40.0),
        (6, 1005, "Licencia Pro", 2, 250.0),
        (7, 1006, "Licencia Pro", 1, 250.0),
    ]

    cursor.executemany(
        "INSERT INTO customers (customer_id, full_name, city, segment) VALUES (?, ?, ?, ?)",
        customers,
    )
    cursor.executemany(
        "INSERT INTO orders (order_id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
        orders,
    )
    cursor.executemany(
        """
        INSERT INTO order_items (order_item_id, order_id, product_name, quantity, unit_price)
        VALUES (?, ?, ?, ?, ?)
        """,
        order_items,
    )

    connection.commit()
    connection.close()

    print(f"Demo DB creada en: {db_path}")


if __name__ == "__main__":
    main()
