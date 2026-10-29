"""Sample SQLite database and example queries for learning the SQL Workbench. All data is synthetic."""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta

from ..config import get_settings

SAMPLE_FILE = "sample_store.sqlite"

EXAMPLE_QUERIES = [
    {"title": "Preview a table", "target": "sample",
     "sql": "SELECT *\nFROM customers\nLIMIT 20;"},
    {"title": "Filter and sort", "target": "sample",
     "sql": "SELECT name, region, signup_date\nFROM customers\nWHERE region = 'North'\nORDER BY signup_date DESC;"},
    {"title": "Join and aggregate", "target": "sample",
     "sql": "SELECT c.region,\n       COUNT(DISTINCT o.order_id) AS orders,\n       ROUND(SUM(i.quantity * p.price), 2) "
            "AS revenue\nFROM orders o\nJOIN customers c ON c.customer_id = o.customer_id\nJOIN order_items i ON "
            "i.order_id = o.order_id\nJOIN products p ON p.product_id = i.product_id\nGROUP BY c.region\n"
            "ORDER BY revenue DESC;"},
    {"title": "Common table expression (CTE)", "target": "sample",
     "sql": "WITH order_totals AS (\n  SELECT o.order_id, o.customer_id, SUM(i.quantity * p.price) AS total\n  FROM orders "
            "o\n  JOIN order_items i ON i.order_id = o.order_id\n  JOIN products p ON p.product_id = i.product_id\n  "
            "GROUP BY o.order_id, o.customer_id\n)\nSELECT customer_id, COUNT(*) AS orders, ROUND(AVG(total), 2) AS "
            "avg_order\nFROM order_totals\nGROUP BY customer_id\nHAVING COUNT(*) >= 3\nORDER BY avg_order DESC;"},
    {"title": "Window function: rank within category", "target": "sample",
     "sql": "SELECT category, name, price,\n       RANK() OVER (PARTITION BY category ORDER BY price DESC) AS "
            "price_rank\nFROM products\nORDER BY category, price_rank;"},
    {"title": "Subquery: customers above average spend", "target": "sample",
     "sql": "SELECT customer_id, spend FROM (\n  SELECT o.customer_id, SUM(i.quantity * p.price) AS spend\n  FROM orders o "
            "JOIN order_items i USING (order_id) JOIN products p USING (product_id)\n  GROUP BY o.customer_id\n) s\n"
            "WHERE spend > (SELECT AVG(i.quantity * p.price) * 5 FROM order_items i JOIN products p USING (product_id))"
            "\nORDER BY spend DESC;"},
    {"title": "Summarise a project dataset by group", "target": "workspace",
     "sql": "-- Replace survey with a table name from the explorer\nSELECT gender, COUNT(*) AS n, AVG(satisfaction) "
            "AS mean_satisfaction\nFROM survey\nGROUP BY gender\nORDER BY n DESC;"},
    {"title": "Filter a dataset before analysis", "target": "workspace",
     "sql": "-- Save the result as a new dataset, then analyse it\nSELECT *\nFROM survey\nWHERE age >= 18\n  AND "
            "satisfaction IS NOT NULL;"},
]


def ensure_sample_db() -> str:
    path = get_settings().sqlite_connections_dir / SAMPLE_FILE
    if path.exists():
        return SAMPLE_FILE
    rng = random.Random(42)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL,
                                signup_date TEXT NOT NULL);
        CREATE TABLE products (product_id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                               price REAL NOT NULL);
        CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                             order_date TEXT NOT NULL, channel TEXT NOT NULL);
        CREATE TABLE order_items (order_id INTEGER NOT NULL REFERENCES orders(order_id),
                                  product_id INTEGER NOT NULL REFERENCES products(product_id),
                                  quantity INTEGER NOT NULL, PRIMARY KEY (order_id, product_id));
        CREATE VIEW monthly_orders AS SELECT substr(order_date, 1, 7) AS month, COUNT(*) AS orders
                                      FROM orders GROUP BY month;
    """)
    first = ["Ana", "Ben", "Carla", "Dan", "Ela", "Felix", "Gia", "Hugo", "Iris", "Jon", "Kai", "Lea", "Mika", "Noel"]
    last = ["Reyes", "Santos", "Cruz", "Lim", "Garcia", "Tan", "Lopez", "Bautista", "Mendoza", "Ramos"]
    regions = ["North", "South", "East", "West"]
    start = date(2024, 1, 1)
    con.executemany("INSERT INTO customers VALUES (?,?,?,?)",
                    [(i, f"{rng.choice(first)} {rng.choice(last)}", rng.choice(regions),
                      (start + timedelta(days=rng.randrange(365))).isoformat()) for i in range(1, 201)])
    cats = {"Books": (8, 40), "Electronics": (25, 400), "Home": (10, 120), "Sports": (12, 150)}
    products, pid = [], 1
    for cat, (lo, hi) in cats.items():
        for k in range(1, 9):
            products.append((pid, f"{cat} item {k}", cat, round(rng.uniform(lo, hi), 2)))
            pid += 1
    con.executemany("INSERT INTO products VALUES (?,?,?,?)", products)
    orders, items = [], []
    for oid in range(1, 1501):
        orders.append((oid, rng.randint(1, 200), (start + timedelta(days=rng.randrange(600))).isoformat(),
                       rng.choice(["web", "store", "phone"])))
        for p in rng.sample(range(1, pid), rng.randint(1, 4)):
            items.append((oid, p, rng.randint(1, 5)))
    con.executemany("INSERT INTO orders VALUES (?,?,?,?)", orders)
    con.executemany("INSERT INTO order_items VALUES (?,?,?)", items)
    con.commit()
    con.close()
    return SAMPLE_FILE
