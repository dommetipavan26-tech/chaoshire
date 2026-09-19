"""HTTP semantics for business failures (v0.23.0 status contract)."""

from fastapi.testclient import TestClient

from chaoshire.app import app


def test_business_failures_use_proper_status_codes():
    with TestClient(app) as client:
        # Uploaded-dataset artifact missing in a fresh process -> 404.
        response = client.get("/api/audit", params={"dataset": "uploaded", "model": "legacy"})
        assert response.status_code == 404
        assert response.json()["error"].startswith("No published dataset is available")

        # Unknown candidate reads -> 404.
        assert client.get("/api/explain/CANDIDATE-9999").status_code == 404
        assert client.get("/api/candidate/CANDIDATE-9999").status_code == 404

        # Appeal for an unknown candidate -> 404.
        response = client.post(
            "/api/appeals", json={"candidate_id": "CANDIDATE-9999", "message": "hello"}
        )
        assert response.status_code == 404
        assert response.json()["error"] == "Unknown candidate ID."

        # Unknown mitigation strategy -> schema-level 422 (Literal catalogue).
        response = client.post("/api/mitigate", json={"strategies": ["review"]})
        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "literal_error"

        # Empty strategy list -> schema-level 422 (min_length=1).
        assert client.post("/api/mitigate", json={"strategies": []}).status_code == 422

        # A valid mitigation still succeeds with the flat result shape.
        response = client.post("/api/mitigate", json={"strategies": ["blind"]})
        assert response.status_code == 200
        body = response.json()
        assert body["applied"]
        assert body["after"]["certificate"]["total"] > body["before"]["certificate"]["total"]

        # Rejected CSV upload -> 422 with the columns that were found.
        response = client.post("/api/upload", json={"csv": "candidate_id\nC-1\n"})
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "Decision column 'decision' was not found."
        assert body["available_columns"] == ["candidate_id"]

        # Export of an artifact that was never produced -> 404.
        response = client.get("/api/audit/export", params={"dataset": "uploaded"})
        assert response.status_code == 404

        # The happy paths still succeed with 200.
        assert (
            client.get("/api/audit", params={"dataset": "demo", "model": "legacy"}).status_code
            == 200
        )


def test_health_routes_expose_get_and_head():
    with TestClient(app) as client:
        for path in ("/api/health", "/api/live", "/api/ready"):
            assert client.get(path).status_code == 200
            assert client.head(path).status_code == 200


def test_openapi_operation_ids_are_unique():
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
    ids = [op["operationId"] for path in spec["paths"].values() for op in path.values()]
    assert ids, "expected OpenAPI operations"
    assert len(ids) == len(set(ids)), f"duplicate operation ids: {ids}"
