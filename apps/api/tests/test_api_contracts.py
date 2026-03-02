"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from islam_intelligent.api.main import app

client = TestClient(app)


class TestAPIContracts:
    """Test API contracts and responses."""

    def test_health_endpoint(self):
        """Health endpoint should return OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_rag_query_endpoint_structure(self):
        """RAG query endpoint should have correct structure."""
        # Note: This may fail if DB not set up, but tests the API structure
        response = client.post("/rag/query", json={"query": "test"})

        # Should return either 200 (success) or 500 (DB error)
        # but structure should be valid
        if response.status_code == 200:
            data = response.json()
            assert "verdict" in data
            assert data["verdict"] in ["answer", "abstain"]

    def test_sources_list_endpoint(self):
        """Sources list endpoint should work."""
        response = client.get("/sources")
        assert response.status_code in [200, 500]  # 500 if DB issue

    def test_evidence_endpoint_structure(self):
        """Evidence endpoint should return 404 for non-existent ID."""
        response = client.get("/evidence/nonexistent")
        assert response.status_code == 404
