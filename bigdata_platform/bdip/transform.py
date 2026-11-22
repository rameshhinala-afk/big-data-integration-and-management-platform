"""Cleaning (silver layer) and integration (gold layer) logic."""

import pandas as pd

EMAIL_RE = r"^[\w.+-]+@[\w-]+\.[\w.-]+$"


def _text(series: pd.Series) -> pd.Series:
    """Trim whitespace and turn empty strings into proper nulls."""
    s = series.astype("string").str.strip()
    return s.mask(s == "", pd.NA)


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["customer_id"] = pd.to_numeric(out["customer_id"], errors="coerce")
    out = out.dropna(subset=["customer_id"])
    out["customer_id"] = out["customer_id"].astype("int64")

    out["name"] = _text(out["name"]).str.title()
    out["city"] = _text(out["city"]).str.title().fillna("Unknown")
    out["email"] = _text(out["email"]).str.lower()
    out.loc[~out["email"].str.match(EMAIL_RE, na=False), "email"] = pd.NA
    out["signup_date"] = pd.to_datetime(out["signup_date"], format="mixed", errors="coerce")

    return out.drop_duplicates("customer_id", keep="last").reset_index(drop=True)


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["name"] = _text(out["name"]).str.title()
    out["category"] = _text(out["category"]).str.title().fillna("Uncategorized")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out = out.dropna(subset=["product_id", "price"])
    out = out[out["price"] > 0]
    return out.drop_duplicates("product_id", keep="last").reset_index(drop=True)


def clean_orders(orders: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame):
    """Return (clean_orders, rejected_orders). Rejected rows carry a `reject_reason`."""
    df = orders.copy()
    for col in ("order_id", "customer_id", "product_id", "quantity"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["order_date"] = pd.to_datetime(df["order_date"], format="mixed", errors="coerce")
    df = df.dropna(subset=["order_id"]).drop_duplicates("order_id", keep="first")

    reasons = pd.Series(pd.NA, index=df.index, dtype="string")

    def flag(mask, why):
        reasons.loc[mask & reasons.isna()] = why

    flag(df["quantity"].isna() | (df["quantity"] <= 0), "invalid_quantity")
    flag(df["order_date"].isna(), "invalid_date")
    flag(~df["customer_id"].isin(customers["customer_id"]), "unknown_customer")
    flag(~df["product_id"].isin(products["product_id"]), "unknown_product")

    rejected = df[reasons.notna()].copy()
    rejected["reject_reason"] = reasons[reasons.notna()]
    clean = df[reasons.isna()].copy()
    for col in ("order_id", "customer_id", "product_id", "quantity"):
        clean[col] = clean[col].astype("int64")
    return clean.reset_index(drop=True), rejected.reset_index(drop=True)


def build_fact_sales(orders: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    fact = orders.merge(
        products[["product_id", "price"]].rename(columns={"price": "unit_price"}),
        on="product_id", how="left",
    )
    fact["revenue"] = (fact["quantity"] * fact["unit_price"]).round(2)
    fact["order_month"] = fact["order_date"].dt.to_period("M").astype(str)
    return fact[["order_id", "customer_id", "product_id", "quantity",
                 "unit_price", "revenue", "order_date", "order_month"]]


def build_marts(fact: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame) -> dict:
    enriched = (fact.merge(products[["product_id", "category"]], on="product_id")
                    .merge(customers[["customer_id", "name", "city"]], on="customer_id"))

    def agg(group_cols):
        return (enriched.groupby(group_cols, as_index=False)
                .agg(orders=("order_id", "count"), units=("quantity", "sum"),
                     revenue=("revenue", "sum"))
                .assign(revenue=lambda d: d["revenue"].round(2)))

    top_customers = (agg(["customer_id", "name", "city"])
                     .sort_values("revenue", ascending=False).head(10).reset_index(drop=True))
    return {
        "mart_sales_by_category": agg(["category"]).sort_values("revenue", ascending=False),
        "mart_sales_by_city": agg(["city"]).sort_values("revenue", ascending=False),
        "mart_monthly_sales": agg(["order_month"]).sort_values("order_month"),
        "mart_top_customers": top_customers,
    }
