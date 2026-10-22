from stylelens import jobs


async def test_health(client):
    r = await client.get("/health")
    assert r.json() == {"status": "ok"}


async def test_upload_rejects_unsupported_type(client):
    r = await client.post("/guides", files={"file": ("x.exe", b"MZ...", "application/octet-stream")})
    assert r.status_code == 415


async def test_upload_rejects_mismatched_content(client):
    r = await client.post("/guides", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 415


async def test_upload_rejects_empty(client):
    r = await client.post("/guides", files={"file": ("a.txt", b"", "text/plain")})
    assert r.status_code == 422


async def test_upload_creates_versioned_guide(client):
    r = await client.post(
        "/guides",
        files={"file": ("brand.md", b"# Brand\n\nUse #0055FF as primary.", "text/markdown")},
        data={"role": "reference"},
    )
    assert r.status_code == 201, r.text
    guide = r.json()
    assert guide["name"] == "brand"
    assert guide["format"] == "markdown"
    assert guide["current_version"]["version"] == 1
    await jobs.drain_inline()

    r = await client.get(f"/guides/{guide['id']}/ingestion-status")
    status = r.json()
    assert set(status["stages"]) == {"parsing", "extracting", "chunking", "embedding", "indexing"}

    r = await client.post(f"/guides/{guide['id']}/reingest")
    assert r.json()["current_version"]["version"] == 2
    await jobs.drain_inline()

    r = await client.get("/guides", params={"role": "reference"})
    assert [g["id"] for g in r.json()] == [guide["id"]]

    r = await client.get(f"/guides/{guide['id']}/file")
    assert r.content.startswith(b"# Brand")

    assert (await client.delete(f"/guides/{guide['id']}")).status_code == 204
    assert (await client.get(f"/guides/{guide['id']}")).status_code == 404


async def test_assets_never_serve_originals(client):
    r = await client.get("/assets/guides/abc/original/brand.pdf")
    assert r.status_code == 404
