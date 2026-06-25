import pytest


@pytest.mark.asyncio
async def test_list_leads_empty(client):
    resp = await client.get("/api/v1/leads")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_nonexistent_lead(client):
    resp = await client.get("/api/v1/leads/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_csv_empty(client):
    resp = await client.get("/api/v1/leads/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_signals_endpoint_404_for_missing_lead(client):
    resp = await client.get("/api/v1/leads/does-not-exist/signals")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sort_by_priority_score(client):
    resp = await client.get("/api/v1/leads?sort_by=priority_score&sort_dir=desc")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
