# Big Data Integration and Management Platform

A compact, runnable reference implementation of a data integration platform. It pulls data from
three differently-shaped sources, cleans and integrates it through a bronze → silver → gold
architecture, checks data quality, tracks metadata and lineage, and serves everything over a REST API.

## Architecture

```
 SOURCES               EXTRACT            BRONZE (raw)      SILVER (clean)         GOLD (integrated)
 customers.csv  ─┐                                          dim_customers  ─┐
 orders.json    ─┼─▶ Connectors ─▶ raw_customers  ─▶ clean ─ dim_products   ─┼─▶ fact_sales ─▶ mart_* tables
 products.db    ─┘   (CSV/JSON/     raw_orders        &      silver_orders  ─┘
                      SQLite)       raw_products      validate rejected_orders (quarantine)

 Cross-cutting:  dq_report (quality, before vs after) · catalog · lineage · pipeline_runs
 Serving:        read-only REST API (stdlib only)
```

## Quick start

```bash
pip install -r requirements.txt
python main.py run        # generates sample data on first run, then executes the pipeline
python main.py report     # catalog, data quality, rejected orders, business marts
python main.py serve      # REST API at http://127.0.0.1:8000
python -m unittest discover -s tests -v
```

Use `python main.py generate --orders 100000` to create a bigger dataset, then `run` again.

## What it does

| Concern | Where | Details |
|---|---|---|
| Multi-source ingestion | `bdip/connectors.py` | CSV, JSON and SQLite connectors behind one `read()` interface. Add a new source by subclassing `Connector`. |
| Cleaning | `bdip/transform.py` | Trim/case-normalise text, validate emails, parse mixed date formats, dedupe keys, default missing categories. |
| Validation + quarantine | `clean_orders` | Bad quantity, unknown customer/product → `rejected_orders` with a `reject_reason` (nothing is silently dropped). |
| Integration | `build_fact_sales`, `build_marts` | Joins orders to products and customers; builds revenue marts by category, city, month, top customers. |
| Data quality | `bdip/quality.py` | Uniqueness, completeness, format, range, referential integrity. Runs on raw **and** clean data. Status is `PASS`, `FAIL`, or `WARN` (gaps that can't be repaired, e.g. a customer with no email). |
| Metadata | `bdip/warehouse.py` | `catalog` (dataset, layer, rows, columns) and `lineage` (which table was derived from which, and how). |
| Serving | `bdip/api.py` | JSON REST API over a read-only SQLite connection. |

## REST API

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /catalog` | All datasets with layer, source, row/column counts |
| `GET /lineage` | Table-to-table lineage |
| `GET /quality?stage=raw\|clean` | Data-quality results |
| `GET /runs` | Pipeline run history |
| `GET /tables` | List tables |
| `GET /tables/<name>?limit=&offset=` | Page through a table |
| `GET /query?sql=SELECT ...` | Ad-hoc read-only query (single `SELECT` only, max 1000 rows) |

Example:

```bash
curl "http://127.0.0.1:8000/query?sql=SELECT%20city,revenue%20FROM%20mart_sales_by_city"
```

## Project layout

```
bigdata_platform/
├── main.py                 CLI (generate | run | report | serve)
├── requirements.txt
├── bdip/
│   ├── config.py           paths
│   ├── generate_data.py    messy sample data generator
│   ├── connectors.py       CSV / JSON / SQLite sources
│   ├── transform.py        cleaning + integration
│   ├── quality.py          data-quality checks
│   ├── warehouse.py        storage, catalog, lineage
│   ├── pipeline.py         orchestration
│   └── api.py              REST API
├── tests/test_platform.py
└── data/                   created on first run (raw/ and warehouse.db)
```

## Scaling up

This project is intentionally small and dependency-light. The same structure maps onto production tools:

- Connectors → Kafka / S3 / JDBC readers
- pandas transforms → Spark or Dask
- SQLite warehouse → Postgres, Snowflake, BigQuery or a Delta/Iceberg lakehouse
- `pipeline.py` → an Airflow / Dagster DAG
- `quality.py` → Great Expectations or dbt tests
