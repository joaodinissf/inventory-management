"""
Tests for the restocking endpoints and the procurement fields added to demand forecasts.
"""
import pytest


@pytest.fixture
def restock_items():
    """Two valid restock line items totalling 5120.00."""
    return [
        {
            "sku": "WDG-001",
            "name": "Industrial Widget Type A",
            "quantity": 100,
            "unit_price": 45.00,
            "lead_time_days": 14,
            "supplier": "Acme Industrial"
        },
        {
            "sku": "FLT-405",
            "name": "Oil Filter Cartridge",
            "quantity": 50,
            "unit_price": 12.40,
            "lead_time_days": 7,
            "supplier": "Nippon Components"
        }
    ]


class TestDemandProcurementFields:
    """The Restocking tab needs cost and lead time on every forecast row."""

    def test_forecasts_expose_procurement_fields(self, client):
        """Every forecast carries unit_cost, lead_time_days and supplier."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        forecasts = response.json()
        assert len(forecasts) > 0

        for forecast in forecasts:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] > 0
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["lead_time_days"] > 0
            assert isinstance(forecast["supplier"], str)
            assert forecast["supplier"]

    def test_psu_501_cost_matches_inventory(self, client):
        """PSU-501 is the one SKU in both fixtures; its cost must agree."""
        forecasts = client.get("/api/demand").json()
        inventory = client.get("/api/inventory").json()

        forecast = next(f for f in forecasts if f["item_sku"] == "PSU-501")
        item = next(i for i in inventory if i["sku"] == "PSU-501")

        assert forecast["unit_cost"] == item["unit_cost"]


class TestCreateRestockOrder:
    """Test suite for POST /api/restock-orders."""

    def test_create_order_succeeds(self, client, restock_items):
        """A within-budget order is accepted and echoed back."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": restock_items}
        )
        assert response.status_code == 200

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert len(order["items"]) == 2
        assert order["budget"] == 10000

    def test_total_value_computed_server_side(self, client, restock_items):
        """The total comes from the line items, not from the client."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": restock_items}
        )
        order = response.json()

        expected = sum(i["quantity"] * i["unit_price"] for i in restock_items)
        assert order["total_value"] == pytest.approx(expected)

    def test_expected_delivery_uses_max_lead_time(self, client, restock_items):
        """An order lands when its slowest line lands, not its fastest."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": restock_items}
        )
        order = response.json()

        assert order["max_lead_time_days"] == 14
        assert order["expected_delivery"] > order["order_date"]

    def test_order_over_budget_rejected(self, client, restock_items):
        """A total above the stated budget returns 400."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 100, "items": restock_items}
        )
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

    def test_empty_order_rejected(self, client):
        """An order with no line items returns 400."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": []}
        )
        assert response.status_code == 400

    def test_zero_quantity_rejected(self, client, restock_items):
        """A line item with no quantity returns 400."""
        items = [dict(restock_items[0], quantity=0)]
        response = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": items}
        )
        assert response.status_code == 400


class TestGetRestockOrders:
    """Test suite for GET /api/restock-orders."""

    def test_submitted_order_is_retrievable(self, client, restock_items):
        """An order that was just posted appears in the list."""
        created = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": restock_items}
        ).json()

        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        orders = response.json()
        # The in-memory list persists across tests in a run, so assert against the
        # order this test created rather than against a length or index.
        assert any(o["order_number"] == created["order_number"] for o in orders)

    def test_orders_returned_newest_first(self, client, restock_items):
        """The most recently submitted order sorts to the top."""
        first = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": restock_items}
        ).json()
        second = client.post(
            "/api/restock-orders",
            json={"budget": 10000, "items": restock_items}
        ).json()

        orders = client.get("/api/restock-orders").json()
        numbers = [o["order_number"] for o in orders]

        assert numbers.index(second["order_number"]) < numbers.index(first["order_number"])
