"""Command-line entry point.

    python main.py generate     create messy sample source data
    python main.py run          run the full integration pipeline
    python main.py report       print catalog, data-quality and business summaries
    python main.py serve        start the REST API (default http://127.0.0.1:8000)
"""

import argparse
import sqlite3
import sys

import pandas as pd

from bdip.api import serve
from bdip.config import Config
from bdip.generate_data import generate
from bdip.pipeline import run_pipeline


def cmd_report(config: Config):
    if not config.warehouse_path.exists():
        sys.exit("Warehouse not found. Run `python main.py run` first.")
    conn = sqlite3.connect(config.warehouse_path)
    pd.set_option("display.width", 140)
    pd.set_option("display.max_columns", 20)

    def show(title, sql):
        print(f"\n=== {title} ===")
        print(pd.read_sql_query(sql, conn).to_string(index=False))

    show("Data catalog", "SELECT dataset, layer, source, row_count, column_count FROM catalog ORDER BY layer, dataset")
    show("Data quality (non-passing checks)",
         "SELECT stage, table_name, check_name, status, failed_rows, total_rows FROM dq_report WHERE status != 'PASS' ORDER BY stage DESC")
    show("Rejected orders by reason",
         "SELECT reject_reason, COUNT(*) AS orders FROM rejected_orders GROUP BY reject_reason")
    show("Revenue by category", "SELECT * FROM mart_sales_by_category")
    show("Revenue by city", "SELECT * FROM mart_sales_by_city")
    show("Top 10 customers", "SELECT * FROM mart_top_customers")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Big Data Integration and Management Platform")
    parser.add_argument("command", choices=["generate", "run", "report", "serve"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--orders", type=int, default=5000, help="number of orders to generate")
    args = parser.parse_args()
    config = Config()

    if args.command == "generate":
        print("Generated:", generate(config.raw_dir, n_orders=args.orders))
    elif args.command == "run":
        for key, value in run_pipeline(config).items():
            print(f"{key:>18}: {value}")
    elif args.command == "report":
        cmd_report(config)
    elif args.command == "serve":
        if not config.warehouse_path.exists():
            sys.exit("Warehouse not found. Run `python main.py run` first.")
        serve(config.warehouse_path, args.host, args.port)


if __name__ == "__main__":
    main()
