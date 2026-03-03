"""KG edge evidence enforcement tests - simplified version."""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

import pytest


class TestEdgeEvidenceRequirements:
    """Test that edges require evidence."""

    def test_rejects_edge_without_evidence(self):
        """Edge creation should fail without evidence_span_ids."""
        from islam_intelligent.kg.edge_manager import create_edge

        with pytest.raises(
            ValueError, match="evidence_span_ids must be a non-empty list"
        ):
            create_edge(
                subject_entity_id="entity_1",
                predicate="test_predicate",
                object_entity_id="entity_2",
                evidence_span_ids=[],  # Empty!
            )

    def test_rejects_edge_with_none_evidence(self):
        """Edge creation should fail with None evidence."""
        from islam_intelligent.kg.edge_manager import create_edge

        with pytest.raises(
            ValueError, match="evidence_span_ids must be a non-empty list"
        ):
            create_edge(
                subject_entity_id="entity_1",
                predicate="test_predicate",
                object_entity_id="entity_2",
                evidence_span_ids=None,  # None!
            )
