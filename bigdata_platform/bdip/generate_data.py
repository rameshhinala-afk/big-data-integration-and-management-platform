"""Generate deliberately messy sample data in three different source formats.

* customers.csv  - CSV file   (duplicates, mixed casing, bad/missing emails, mixed date formats)
* orders.json    - JSON file  (orphan keys, invalid quantities, duplicate orders, mixed date formats)
* products.db    - SQLite DB  (missing categories)
"""

import csv
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

FIRST = ["Aarav", "Priya", "Rahul", "Sneha", "Vikram", "Ananya", "Karthik", "Meera",
         "Rohan", "Divya", "Arjun", "Kavya", "Nikhil", "Isha", "Sanjay", "Pooja"]
LAST = ["Sharma", "Reddy", "Patel", "Iyer", "Singh", "Gupta", "Nair", "Rao",
        "Mehta", "Das", "Kumar", "Joshi"]
CITIES = ["Hyderabad", "Mumbai", "Delhi", "Bengaluru", "Chennai", "Pune", "Kolkata", "Ahmedabad"]
CATEGORIES = {
    "Electronics": ["Headphones", "Keyboard", "Monitor", "Webcam", "Router"],
    "Home": ["Lamp", "Cushion", "Kettle", "Blender", "Rug"],
    "Books": ["Novel", "Cookbook", "Biography", "Atlas", "Journal"],
    "Sports": ["Yoga Mat", "Dumbbell", "Football", "Racket", "Skipping Rope"],
}


def generate(raw_dir, n_customers=500, n_products=40, n_orders=5000, seed=42):
    rng = random.Random(seed)
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- customers.csv
    customers = []
    for cid in range(1, n_customers + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        email = f"{first}.{last}{cid}@example.com".lower()
        r = rng.random()
        if r < 0.05:
            email = f"  {email.upper()} "
        elif r < 0.07:
            email = "not-an-email"
        elif r < 0.10:
            email = ""
        city = rng.choice(CITIES)
        r = rng.random()
        if r < 0.03:
            city = ""
        elif r < 0.13:
            city = city.upper()
        name = f"{first} {last}"
        if rng.random() < 0.10:
            name = name.upper()
        signup = date(2024, 1, 1) + timedelta(days=rng.randint(0, 600))
        fmt = rng.choice(["%Y-%m-%d", "%d-%b-%Y", "%Y/%m/%d"])
        customers.append({
            "customer_id": cid, "name": name, "email": email,
            "city": city, "signup_date": signup.strftime(fmt),
        })
    dupes = rng.sample(customers, k=max(1, int(n_customers * 0.03)))
    customers.extend(dict(row) for row in dupes)

    with open(raw_dir / "customers.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(customers[0].keys()))
        writer.writeheader()
        writer.writerows(customers)

    # ---------------------------------------------------------------- products.db
    db_path = raw_dir / "products.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE products (product_id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL)")
    cats = list(CATEGORIES)
    for pid in range(1, n_products + 1):
        cat = rng.choice(cats)
        name = f"{rng.choice(CATEGORIES[cat])} {pid}"
        price = round(rng.uniform(5, 500), 2)
        if pid % 20 == 0:
            cat = None  # missing category
        conn.execute("INSERT INTO products VALUES (?, ?, ?, ?)", (pid, name, cat, price))
    conn.commit()
    conn.close()

    # ---------------------------------------------------------------- orders.json
    orders = []
    for oid in range(1, n_orders + 1):
        cid = rng.randint(1, n_customers)
        if rng.random() < 0.01:
            cid = n_customers + rng.randint(1, 100)       # orphan customer
        pid = rng.randint(1, n_products)
        if rng.random() < 0.005:
            pid = n_products + rng.randint(1, 5)          # orphan product
        qty = rng.randint(1, 5)
        if rng.random() < 0.01:
            qty = rng.choice([0, -1])                     # invalid quantity
        d = date(2025, 1, 1) + timedelta(days=rng.randint(0, 668))
        fmt = "%Y/%m/%d" if rng.random() < 0.10 else "%Y-%m-%d"
        orders.append({
            "order_id": oid, "customer_id": cid, "product_id": pid,
            "quantity": qty, "order_date": d.strftime(fmt),
        })
    orders.extend(dict(o) for o in rng.sample(orders, k=max(1, int(n_orders * 0.01))))  # duplicates

    with open(raw_dir / "orders.json", "w", encoding="utf-8") as f:
        json.dump(orders, f)

    return {"customers": len(customers), "products": n_products, "orders": len(orders)}
