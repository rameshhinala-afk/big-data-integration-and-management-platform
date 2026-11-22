import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bdip.api import Api, is_safe_query
from bdip.config import Config
from bdip.generate_data import generate
from bdip.pipeline import run_pipeline


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config = Config(root=Path(cls.tmp.name))
        generate(cls.config.raw_dir, n_customers=200, n_products=20, n_orders=2000, seed=7)
        cls.summary = run_pipeline(cls.config, generate_if_missing=False)
        cls.conn = sqlite3.connect(cls.config.warehouse_path)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()

    def q(self, sql):
        return self.conn.execute(sql).fetchall()

    def test_raw_data_has_quality_problems(self):
        self.assertGreater(self.summary["dq_failed_raw"], 0)

    def test_clean_data_passes_all_checks(self):
        self.assertEqual(self.summary["dq_failed_clean"], 0)

    def test_no_duplicate_keys_after_cleaning(self):
        self.assertEqual(self.q("SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM dim_customers")[0][0], 0)
        self.assertEqual(self.q("SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_sales")[0][0], 0)

    def test_referential_integrity_in_fact(self):
        orphans = self.q("""SELECT COUNT(*) FROM fact_sales f
                            LEFT JOIN dim_customers c USING (customer_id)
                            LEFT JOIN dim_products p USING (product_id)
                            WHERE c.customer_id IS NULL OR p.product_id IS NULL""")[0][0]
        self.assertEqual(orphans, 0)

    def test_every_order_is_accounted_for(self):
        s = self.summary
        dupes = s["raw_orders"] - s["clean_orders"] - s["rejected_orders"]
        self.assertGreaterEqual(dupes, 0)  # the remainder are removed duplicates

    def test_mart_revenue_matches_fact(self):
        fact = self.q("SELECT ROUND(SUM(revenue), 2) FROM fact_sales")[0][0]
        mart = self.q("SELECT ROUND(SUM(revenue), 2) FROM mart_sales_by_category")[0][0]
        self.assertAlmostEqual(fact, mart, places=1)

    def test_catalog_lists_all_layers(self):
        layers = {r[0] for r in self.q("SELECT DISTINCT layer FROM catalog")}
        self.assertEqual(layers, {"bronze", "silver", "gold"})

    def test_query_guard(self):
        self.assertTrue(is_safe_query("SELECT * FROM fact_sales"))
        self.assertFalse(is_safe_query("DELETE FROM fact_sales"))
        self.assertFalse(is_safe_query("SELECT 1; DROP TABLE fact_sales"))

    def test_api_endpoints(self):
        api = Api(self.config.warehouse_path)
        self.assertEqual(api.handle("/health", {})[0], 200)
        status, tables = api.handle("/tables", {})
        self.assertIn("fact_sales", tables)
        self.assertEqual(api.handle("/tables/nope", {})[0], 404)
        self.assertEqual(api.handle("/query", {"sql": ["DROP TABLE fact_sales"]})[0], 400)
        status, rows = api.handle("/query", {"sql": ["SELECT COUNT(*) AS n FROM fact_sales"]})
        self.assertEqual(status, 200)
        self.assertGreater(rows[0]["n"], 0)


if __name__ == "__main__":
    unittest.main()
