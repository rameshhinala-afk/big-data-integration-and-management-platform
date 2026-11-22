"""Data-quality checks. The same rules run on raw data and on cleaned data so the improvement is visible."""

from datetime import datetime

import pandas as pd

from .transform import EMAIL_RE


def run_checks(stage: str, customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    results = []
    now = datetime.now().isoformat(timespec="seconds")

    def check(table, name, bad_mask, total, severity="error"):
        """severity="warn" is for gaps cleaning cannot repair (the true value is unknown)."""
        failed = int(bad_mask.sum())
        status = "PASS" if failed == 0 else ("WARN" if severity == "warn" else "FAIL")
        results.append({
            "stage": stage, "table_name": table, "check_name": name,
            "status": status,
            "failed_rows": failed, "total_rows": int(total), "checked_at": now,
        })

    # ---- customers
    n = len(customers)
    cid = pd.to_numeric(customers["customer_id"], errors="coerce")
    check("customers", "customer_id unique", cid.duplicated(keep="first"), n)
    email = customers["email"].astype("string").str.strip()
    check("customers", "email not null", email.isna() | (email == ""), n, severity="warn")
    check("customers", "email valid format",
          (email.notna() & (email != "")) & ~email.str.match(EMAIL_RE, na=False), n)
    city = customers["city"].astype("string").str.strip()
    check("customers", "city not null", city.isna() | (city == ""), n)
    check("customers", "signup_date parseable",
          pd.to_datetime(customers["signup_date"], format="mixed", errors="coerce").isna(), n)

    # ---- products
    n = len(products)
    check("products", "product_id unique", products["product_id"].duplicated(keep="first"), n)
    check("products", "category not null", products["category"].isna(), n)
    check("products", "price > 0", ~(pd.to_numeric(products["price"], errors="coerce") > 0), n)

    # ---- orders
    n = len(orders)
    qty = pd.to_numeric(orders["quantity"], errors="coerce")
    check("orders", "order_id unique", orders["order_id"].duplicated(keep="first"), n)
    check("orders", "quantity > 0", ~(qty > 0), n)
    check("orders", "order_date parseable",
          pd.to_datetime(orders["order_date"], format="mixed", errors="coerce").isna(), n)
    check("orders", "customer_id exists in customers",
          ~pd.to_numeric(orders["customer_id"], errors="coerce").isin(cid), n)
    check("orders", "product_id exists in products",
          ~pd.to_numeric(orders["product_id"], errors="coerce").isin(products["product_id"]), n)

    return pd.DataFrame(results)
