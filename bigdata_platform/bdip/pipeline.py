"""End-to-end pipeline: extract -> load raw (bronze) -> quality(raw) -> clean (silver) -> integrate (gold)
-> quality(clean) -> catalog."""

import time
from datetime import datetime

import pandas as pd

from .config import Config
from .connectors import CSVConnector, JSONConnector, SQLiteConnector
from .generate_data import generate
from .quality import run_checks
from .transform import (build_fact_sales, build_marts, clean_customers,
                        clean_orders, clean_products)
from .warehouse import Warehouse


def run_pipeline(config: Config = Config(), generate_if_missing: bool = True) -> dict:
    started = datetime.now()
    t0 = time.time()

    if generate_if_missing and not (config.customers_csv.exists()
                                    and config.orders_json.exists()
                                    and config.products_db.exists()):
        generate(config.raw_dir)

    # ---------------- 1. Extract from heterogeneous sources
    sources = {
        "customers": CSVConnector(config.customers_csv),
        "orders": JSONConnector(config.orders_json),
        "products": SQLiteConnector(config.products_db, "products"),
    }
    raw = {name: conn.read() for name, conn in sources.items()}

    if config.warehouse_path.exists():
        config.warehouse_path.unlink()
    config.root.mkdir(parents=True, exist_ok=True)
    wh = Warehouse(config.warehouse_path)

    # ---------------- 2. Bronze: land raw data untouched
    for name, df in raw.items():
        wh.write(f"raw_{name}", df, layer="bronze", source=sources[name].describe())

    # ---------------- 3. Quality on raw data
    dq_raw = run_checks("raw", raw["customers"], raw["products"], raw["orders"])

    # ---------------- 4. Silver: clean + conform
    customers = clean_customers(raw["customers"])
    products = clean_products(raw["products"])
    orders, rejected = clean_orders(raw["orders"], customers, products)

    wh.write("dim_customers", customers, "silver", "raw_customers",
             "trim, case-normalise, validate email, parse dates, dedupe on customer_id", ["raw_customers"])
    wh.write("dim_products", products, "silver", "raw_products",
             "normalise text, default category, drop invalid prices, dedupe", ["raw_products"])
    wh.write("silver_orders", orders, "silver", "raw_orders",
             "dedupe, type-cast, referential + range validation",
             ["raw_orders", "dim_customers", "dim_products"])
    wh.write("rejected_orders", rejected, "silver", "raw_orders",
             "orders failing validation, with reject_reason", ["raw_orders"])

    # ---------------- 5. Gold: integrated fact table and marts
    fact = build_fact_sales(orders, products)
    wh.write("fact_sales", fact, "gold", "silver_orders",
             "join orders to product price, compute revenue", ["silver_orders", "dim_products"])
    for name, mart in build_marts(fact, customers, products).items():
        wh.write(name, mart, "gold", "fact_sales", "aggregate", ["fact_sales", "dim_customers", "dim_products"])

    # ---------------- 6. Quality on cleaned data
    dq_clean = run_checks("clean", customers, products, orders)
    pd.concat([dq_raw, dq_clean], ignore_index=True).to_sql(
        "dq_report", wh.conn, if_exists="replace", index=False)

    # ---------------- 7. Run log + catalog
    summary = {
        "started_at": started.isoformat(timespec="seconds"),
        "duration_sec": round(time.time() - t0, 2),
        "raw_customers": len(raw["customers"]), "raw_products": len(raw["products"]),
        "raw_orders": len(raw["orders"]),
        "clean_customers": len(customers), "clean_products": len(products),
        "clean_orders": len(orders), "rejected_orders": len(rejected),
        "dq_failed_raw": int((dq_raw["status"] == "FAIL").sum()),
        "dq_failed_clean": int((dq_clean["status"] == "FAIL").sum()),
        "status": "SUCCESS",
    }
    pd.DataFrame([summary]).to_sql("pipeline_runs", wh.conn, if_exists="append", index=False)
    wh.flush_metadata()
    wh.close()
    return summary
