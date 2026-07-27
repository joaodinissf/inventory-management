"""
Tests for reports API endpoints (/api/reports/quarterly, /api/reports/monthly-trends).

Aggregates are cross-checked against /api/orders with the same query string
rather than hardcoded counts, so the suite survives changes to the mock data.
"""
import pytest

QUARTER_MONTHS = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12'],
}


def _orders(client, query=""):
    """Fetch /api/orders with the same query string used against a report."""
    suffix = f"?{query}" if query else ""
    response = client.get(f"/api/orders{suffix}")
    assert response.status_code == 200
    return response.json()


class TestQuarterlyReportFiltering:
    """Test suite for filtering on GET /api/reports/quarterly."""

    def test_quarterly_baseline_unfiltered(self, client):
        """Unfiltered quarterly report returns all four 2025 quarters, sorted."""
        response = client.get("/api/reports/quarterly")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert [q["quarter"] for q in data] == [
            "Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025"
        ]

        required_fields = [
            "quarter", "total_orders", "total_revenue",
            "avg_order_value", "delivered_orders", "fulfillment_rate"
        ]
        for quarter in data:
            for field in required_fields:
                assert field in quarter, f"Missing field: {field}"

    def test_quarterly_all_sentinel_matches_no_filters(self, client):
        """The 'all' sentinel on every filter is equivalent to no filters."""
        response = client.get(
            "/api/reports/quarterly?warehouse=all&category=all&status=all&month=all"
        )
        assert response.status_code == 200

        response_no_filter = client.get("/api/reports/quarterly")
        assert response.json() == response_no_filter.json()

    def test_quarterly_warehouse_filter_matches_orders(self, client):
        """Warehouse-filtered totals match the same-query /api/orders result."""
        response = client.get("/api/reports/quarterly?warehouse=Tokyo")
        assert response.status_code == 200
        data = response.json()

        expected_orders = _orders(client, "warehouse=Tokyo")
        assert sum(q["total_orders"] for q in data) == len(expected_orders)
        assert sum(q["total_revenue"] for q in data) == pytest.approx(
            sum(o["total_value"] for o in expected_orders)
        )

    def test_quarterly_category_filter_is_case_insensitive(self, client):
        """Lowercase category (as sent by the filter bar) matches the canonical case."""
        lower = client.get("/api/reports/quarterly?category=sensors")
        upper = client.get("/api/reports/quarterly?category=Sensors")
        assert lower.status_code == 200
        assert lower.json() == upper.json()

        expected_orders = _orders(client, "category=sensors")
        assert sum(q["total_orders"] for q in lower.json()) == len(expected_orders)
        assert sum(q["total_revenue"] for q in lower.json()) == pytest.approx(
            sum(o["total_value"] for o in expected_orders)
        )

    def test_quarterly_status_delivered_gives_full_fulfillment(self, client):
        """status=delivered leaves only delivered orders, so fulfillment is 100%."""
        response = client.get("/api/reports/quarterly?status=delivered")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for quarter in data:
            assert quarter["delivered_orders"] == quarter["total_orders"]
            assert quarter["fulfillment_rate"] == 100.0

    def test_quarterly_status_processing_gives_zero_fulfillment(self, client):
        """Documented degenerate semantics: a non-delivered status filter zeroes fulfillment."""
        response = client.get("/api/reports/quarterly?status=processing")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for quarter in data:
            assert quarter["delivered_orders"] == 0
            assert quarter["fulfillment_rate"] == 0.0

    def test_quarterly_month_filter_collapses_to_one_quarter(self, client):
        """A single-month filter collapses the report to that month's quarter."""
        response = client.get("/api/reports/quarterly?month=2025-01")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["quarter"] == "Q1-2025"
        assert data[0]["total_orders"] == len(_orders(client, "month=2025-01"))

    def test_quarterly_quarter_filter(self, client):
        """A quarter filter returns exactly that quarter."""
        response = client.get("/api/reports/quarterly?month=Q2-2025")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["quarter"] == "Q2-2025"
        assert data[0]["total_orders"] == len(_orders(client, "month=Q2-2025"))

    def test_quarterly_combined_filters_match_orders_endpoint(self, client):
        """All four filters combined still agree with /api/orders."""
        query = "warehouse=London&category=sensors&status=delivered&month=Q1-2025"
        response = client.get(f"/api/reports/quarterly?{query}")
        assert response.status_code == 200

        data = response.json()
        expected_orders = _orders(client, query)
        assert sum(q["total_orders"] for q in data) == len(expected_orders)
        assert sum(q["total_revenue"] for q in data) == pytest.approx(
            sum(o["total_value"] for o in expected_orders)
        )

    def test_quarterly_over_filtered_returns_empty_list(self, client):
        """A filter matching nothing returns 200 with an empty list, not an error."""
        response = client.get("/api/reports/quarterly?warehouse=Mars")
        assert response.status_code == 200
        assert response.json() == []

    def test_quarterly_derived_metrics_recomputed_under_filter(self, client):
        """Derived metrics are recomputed from the filtered totals, not the full set."""
        response = client.get("/api/reports/quarterly?warehouse=Tokyo")
        data = response.json()
        assert len(data) > 0

        for quarter in data:
            assert quarter["total_orders"] > 0
            assert quarter["avg_order_value"] == pytest.approx(
                round(quarter["total_revenue"] / quarter["total_orders"], 2)
            )
            assert quarter["fulfillment_rate"] == pytest.approx(
                round((quarter["delivered_orders"] / quarter["total_orders"]) * 100, 1)
            )


class TestMonthlyTrendsFiltering:
    """Test suite for filtering on GET /api/reports/monthly-trends."""

    def test_monthly_baseline_unfiltered(self, client):
        """Unfiltered trends return all twelve 2025 months in ascending order."""
        response = client.get("/api/reports/monthly-trends")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert [m["month"] for m in data] == [f"2025-{i:02d}" for i in range(1, 13)]

        for bucket in data:
            for field in ["month", "order_count", "revenue", "delivered_count"]:
                assert field in bucket, f"Missing field: {field}"

    def test_monthly_all_sentinel_matches_no_filters(self, client):
        """The 'all' sentinel on every filter is equivalent to no filters."""
        response = client.get(
            "/api/reports/monthly-trends?warehouse=all&category=all&status=all&month=all"
        )
        assert response.status_code == 200

        response_no_filter = client.get("/api/reports/monthly-trends")
        assert response.json() == response_no_filter.json()

    def test_monthly_warehouse_filter_matches_orders(self, client):
        """Per-month counts and revenue match buckets rebuilt from /api/orders."""
        query = "warehouse=San Francisco"
        response = client.get(f"/api/reports/monthly-trends?{query}")
        assert response.status_code == 200
        data = response.json()

        expected = {}
        for order in _orders(client, query):
            key = order["order_date"][:7]
            bucket = expected.setdefault(key, {"order_count": 0, "revenue": 0.0})
            bucket["order_count"] += 1
            bucket["revenue"] += order["total_value"]

        assert {m["month"] for m in data} == set(expected)
        for bucket in data:
            assert bucket["order_count"] == expected[bucket["month"]]["order_count"]
            assert bucket["revenue"] == pytest.approx(
                expected[bucket["month"]]["revenue"]
            )

    def test_monthly_category_filter_lowercase(self, client):
        """A lowercase, space-containing category value filters correctly."""
        query = "category=power supplies"
        response = client.get(f"/api/reports/monthly-trends?{query}")
        assert response.status_code == 200
        data = response.json()

        expected_orders = _orders(client, query)
        assert sum(m["order_count"] for m in data) == len(expected_orders)
        assert sum(m["revenue"] for m in data) == pytest.approx(
            sum(o["total_value"] for o in expected_orders)
        )

    def test_monthly_status_filter_affects_delivered_count(self, client):
        """status=processing zeroes delivered_count in every bucket."""
        response = client.get("/api/reports/monthly-trends?status=processing")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for bucket in data:
            assert bucket["delivered_count"] == 0

        assert sum(m["order_count"] for m in data) == len(
            _orders(client, "status=processing")
        )

    def test_monthly_month_filter_returns_single_bucket(self, client):
        """A single-month filter yields exactly that bucket.

        Regression test for the `month` query parameter being shadowed by the
        loop-local bucket key.
        """
        response = client.get("/api/reports/monthly-trends?month=2025-05")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["month"] == "2025-05"
        assert data[0]["order_count"] == len(_orders(client, "month=2025-05"))

    def test_monthly_quarter_filter_returns_three_buckets(self, client):
        """A quarter filter yields that quarter's three months, ascending."""
        response = client.get("/api/reports/monthly-trends?month=Q3-2025")
        assert response.status_code == 200

        data = response.json()
        assert [m["month"] for m in data] == ["2025-07", "2025-08", "2025-09"]

    def test_monthly_results_sorted_after_filtering(self, client):
        """Sorting is preserved once a filter has reduced the bucket set."""
        response = client.get("/api/reports/monthly-trends?warehouse=Tokyo")
        assert response.status_code == 200

        months = [m["month"] for m in response.json()]
        assert months == sorted(months)

    def test_monthly_over_filtered_returns_empty_list(self, client):
        """A filter combination matching nothing returns 200 with an empty list."""
        response = client.get(
            "/api/reports/monthly-trends?warehouse=Mars&month=2025-01"
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_monthly_no_bucket_has_zero_orders(self, client):
        """Buckets are built from matching orders only, never pre-seeded then filtered."""
        response = client.get(
            "/api/reports/monthly-trends?warehouse=London&category=sensors"
        )
        assert response.status_code == 200

        for bucket in response.json():
            assert bucket["order_count"] > 0


class TestReportsFilterConsistency:
    """Cross-endpoint checks that both reports aggregate the same filtered set."""

    QUERIES = [
        "warehouse=Tokyo",
        "category=sensors",
        "status=delivered",
        "warehouse=London&category=sensors",
        "month=Q4-2025",
    ]

    @pytest.mark.parametrize("query", QUERIES)
    def test_totals_agree_across_reports_and_orders(self, client, query):
        """Quarterly, monthly-trends and /api/orders agree on counts and revenue."""
        quarterly = client.get(f"/api/reports/quarterly?{query}").json()
        monthly = client.get(f"/api/reports/monthly-trends?{query}").json()
        expected_orders = _orders(client, query)

        assert sum(q["total_orders"] for q in quarterly) == len(expected_orders)
        assert sum(m["order_count"] for m in monthly) == len(expected_orders)

        expected_revenue = sum(o["total_value"] for o in expected_orders)
        assert sum(q["total_revenue"] for q in quarterly) == pytest.approx(
            expected_revenue
        )
        assert sum(m["revenue"] for m in monthly) == pytest.approx(expected_revenue)

    @pytest.mark.parametrize("query", QUERIES)
    def test_quarterly_buckets_match_monthly_buckets(self, client, query):
        """Each quarter's total equals the sum of its three months in monthly-trends."""
        quarterly = client.get(f"/api/reports/quarterly?{query}").json()
        monthly = client.get(f"/api/reports/monthly-trends?{query}").json()

        monthly_by_key = {m["month"]: m for m in monthly}

        for quarter in quarterly:
            member_months = QUARTER_MONTHS[quarter["quarter"]]
            assert quarter["total_orders"] == sum(
                monthly_by_key[m]["order_count"]
                for m in member_months
                if m in monthly_by_key
            )
            assert quarter["total_revenue"] == pytest.approx(
                sum(
                    monthly_by_key[m]["revenue"]
                    for m in member_months
                    if m in monthly_by_key
                )
            )
