from stylelens import jobs
from stylelens.eval import samples


async def test_pdf_ingestion_end_to_end(client):
    r = await client.post("/guides", files={"file": ("northwind.pdf", samples.northwind_guide(), "application/pdf")},
                          data={"role": "reference", "name": "Northwind"})
    assert r.status_code == 201
    gid = r.json()["id"]
    await jobs.drain_inline()

    status = (await client.get(f"/guides/{gid}/ingestion-status")).json()
    assert status["status"] == "ready", status
    assert all(s["status"] == "done" for s in status["stages"].values())

    pages = (await client.get(f"/guides/{gid}/pages")).json()
    assert len(pages) >= 5 and pages[0]["image_url"].startswith("/assets/guides/")
    img = await client.get(pages[0]["image_url"])
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")

    elements = (await client.get(f"/guides/{gid}/elements")).json()
    assert any(e["type"] == "swatch" for e in elements)
    assert all(e["id"].startswith(status["version_id"][:24]) for e in elements)

    guide = (await client.get(f"/guides/{gid}")).json()
    assert guide["current_version"]["title"] == "Northwind Coffee Brand Guidelines"
    assert guide["status"] == "ready"


async def test_failed_ingestion_reports_error(client):
    # Valid magic bytes but corrupt body
    r = await client.post("/guides", files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    gid = r.json()["id"]
    await jobs.drain_inline()
    status = (await client.get(f"/guides/{gid}/ingestion-status")).json()
    assert status["status"] == "failed"
    assert status["stages"]["parsing"]["status"] == "failed"
    assert status["error"]
