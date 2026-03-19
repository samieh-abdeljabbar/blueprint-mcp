"""Tests for description dictionaries in models.py."""

from src.models import (
    EDGE_RELATIONSHIP_DESCRIPTIONS,
    NODE_STATUS_DESCRIPTIONS,
    NODE_TYPE_DESCRIPTIONS,
    EdgeRelationship,
    NodeStatus,
    NodeType,
)


# --- NodeType descriptions ---

def test_every_node_type_has_description():
    for nt in NodeType:
        assert nt.value in NODE_TYPE_DESCRIPTIONS, f"Missing description for NodeType.{nt.value}"


def test_no_extra_node_type_keys():
    valid = {nt.value for nt in NodeType}
    for key in NODE_TYPE_DESCRIPTIONS:
        assert key in valid, f"Stale key in NODE_TYPE_DESCRIPTIONS: {key}"


def test_node_type_descriptions_concise():
    for key, desc in NODE_TYPE_DESCRIPTIONS.items():
        assert 10 <= len(desc) <= 100, (
            f"NODE_TYPE_DESCRIPTIONS['{key}'] length {len(desc)} not in 10-100"
        )


# --- NodeStatus descriptions ---

def test_every_node_status_has_description():
    for ns in NodeStatus:
        assert ns.value in NODE_STATUS_DESCRIPTIONS, f"Missing description for NodeStatus.{ns.value}"


def test_no_extra_node_status_keys():
    valid = {ns.value for ns in NodeStatus}
    for key in NODE_STATUS_DESCRIPTIONS:
        assert key in valid, f"Stale key in NODE_STATUS_DESCRIPTIONS: {key}"


def test_node_status_descriptions_concise():
    for key, desc in NODE_STATUS_DESCRIPTIONS.items():
        assert 10 <= len(desc) <= 100, (
            f"NODE_STATUS_DESCRIPTIONS['{key}'] length {len(desc)} not in 10-100"
        )


# --- EdgeRelationship descriptions ---

def test_every_edge_relationship_has_description():
    for er in EdgeRelationship:
        assert er.value in EDGE_RELATIONSHIP_DESCRIPTIONS, (
            f"Missing description for EdgeRelationship.{er.value}"
        )


def test_no_extra_edge_relationship_keys():
    valid = {er.value for er in EdgeRelationship}
    for key in EDGE_RELATIONSHIP_DESCRIPTIONS:
        assert key in valid, f"Stale key in EDGE_RELATIONSHIP_DESCRIPTIONS: {key}"


def test_edge_relationship_descriptions_concise():
    for key, desc in EDGE_RELATIONSHIP_DESCRIPTIONS.items():
        assert 10 <= len(desc) <= 100, (
            f"EDGE_RELATIONSHIP_DESCRIPTIONS['{key}'] length {len(desc)} not in 10-100"
        )
