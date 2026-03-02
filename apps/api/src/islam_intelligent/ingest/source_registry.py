"""Source registry with append-only versioning.

This module implements the core registry for managing source documents
with append-only versioning. Updates create NEW rows; old rows remain
accessible via the supersedes_source_id chain.
"""

import hashlib
import json
import uuid
from typing import Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from islam_intelligent.domain.models import SourceDocument


def _generate_source_id() -> str:
    """Generate a unique source identifier."""
    return f"src_{uuid.uuid4().hex[:16]}"


def _compute_sha256(data: str) -> str:
    """Compute SHA256 hash of string data."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _compute_manifest_hash(source_doc: SourceDocument) -> str:
    """Compute manifest hash including all metadata and content."""
    manifest = {
        "source_id": source_doc.source_id,
        "version": source_doc.version,
        "source_type": source_doc.source_type,
        "title": source_doc.title,
        "author": source_doc.author,
        "language": source_doc.language,
        "content_sha256": source_doc.content_sha256,
    }
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return _compute_sha256(manifest_json)


def create_source_document(
    db: Session,
    source_type: str,
    content: dict[str, Any],
    title: Optional[str] = None,
    author: Optional[str] = None,
    language: str = "ar",
    source_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> SourceDocument:
    """Create a new source document.

    Args:
        db: Database session
        source_type: Type of source (e.g., 'quran', 'hadith_bukhari', 'tafsir')
        content: Document content as dictionary (will be serialized to JSON)
        title: Optional title
        author: Optional author
        language: Language code (default: 'ar' for Arabic)
        source_id: Optional explicit source ID (generated if not provided)
        created_by: Optional identifier of creator

    Returns:
        The created SourceDocument with generated hashes
    """
    # Generate source_id if not provided
    if source_id is None:
        source_id = _generate_source_id()

    # Serialize content to JSON
    content_json = json.dumps(content, sort_keys=True, ensure_ascii=False)

    # Compute content hash
    content_sha256 = _compute_sha256(content_json)

    # Create document
    doc = SourceDocument(
        source_id=source_id,
        version=1,
        source_type=source_type,
        title=title,
        author=author,
        language=language,
        content_json=content_json,
        content_sha256=content_sha256,
        manifest_sha256="",  # Will be computed after creation
        created_by=created_by,
    )

    # Compute manifest hash
    doc.manifest_sha256 = _compute_manifest_hash(doc)

    db.add(doc)
    db.commit()
    db.refresh(doc)

    return doc


def get_source_document(
    db: Session,
    source_id: str,
    version: Optional[int] = None,
) -> Optional[SourceDocument]:
    """Get a source document by ID and optional version.

    Args:
        db: Database session
        source_id: Source identifier
        version: Specific version to retrieve (default: latest)

    Returns:
        SourceDocument if found, None otherwise
    """
    if version is not None:
        # Get specific version
        stmt = select(SourceDocument).where(
            SourceDocument.source_id == source_id,
            SourceDocument.version == version,
        )
        return db.execute(stmt).scalar_one_or_none()
    else:
        # Get latest version
        stmt = (
            select(SourceDocument)
            .where(SourceDocument.source_id == source_id)
            .order_by(desc(SourceDocument.version))
            .limit(1)
        )
        return db.execute(stmt).scalar_one_or_none()


def list_sources(
    db: Session,
    source_type: Optional[str] = None,
    author: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    latest_only: bool = True,
) -> list[SourceDocument]:
    """List source documents with optional filters.

    Args:
        db: Database session
        source_type: Filter by source type
        author: Filter by author
        language: Filter by language
        limit: Maximum results to return
        offset: Offset for pagination
        latest_only: If True, return only latest version of each source

    Returns:
        List of SourceDocument objects
    """
    stmt = select(SourceDocument)

    if source_type:
        stmt = stmt.where(SourceDocument.source_type == source_type)
    if author:
        stmt = stmt.where(SourceDocument.author == author)
    if language:
        stmt = stmt.where(SourceDocument.language == language)

    if latest_only:
        # Subquery to get latest version per source_id
        latest_versions = (
            select(
                SourceDocument.source_id,
                func.max(SourceDocument.version).label("max_version"),
            )
            .group_by(SourceDocument.source_id)
            .subquery()
        )
        stmt = stmt.join(
            latest_versions,
            (SourceDocument.source_id == latest_versions.c.source_id)
            & (SourceDocument.version == latest_versions.c.max_version),
        )

    stmt = stmt.order_by(desc(SourceDocument.created_at)).limit(limit).offset(offset)
    result = db.execute(stmt)
    return list(result.scalars().all())


def update_source(
    db: Session,
    source_id: str,
    new_data: dict[str, Any],
    updated_by: Optional[str] = None,
) -> Optional[SourceDocument]:
    """Update a source document - creates NEW version, old remains accessible.

    This is the core append-only operation. The old document remains in the
    database and can be accessed via its version number. The new document
    links to the old via supersedes_source_id.

    Args:
        db: Database session
        source_id: Source identifier to update
        new_data: Dictionary with updated fields. Can include:
            - content: New content dict (required)
            - title: New title
            - author: New author
            - language: New language
            - source_type: New source type
        updated_by: Optional identifier of updater

    Returns:
        New SourceDocument version, or None if source not found
    """
    # Get current latest version
    current = get_source_document(db, source_id)
    if current is None:
        return None

    # Extract new values with fallbacks to current
    content = new_data.get("content")
    if content is None:
        raise ValueError("'content' is required in new_data for update")

    title = new_data.get("title", current.title)
    author = new_data.get("author", current.author)
    language = new_data.get("language", current.language)
    source_type = new_data.get("source_type", current.source_type)

    # Serialize content to JSON
    content_json = json.dumps(content, sort_keys=True, ensure_ascii=False)

    # Compute new content hash
    content_sha256 = _compute_sha256(content_json)

    # Create new version
    new_doc = SourceDocument(
        source_id=source_id,
        version=current.version + 1,
        supersedes_source_id=source_id,
        supersedes_version=current.version,
        source_type=source_type,
        title=title,
        author=author,
        language=language,
        content_json=content_json,
        content_sha256=content_sha256,
        manifest_sha256="",  # Will be computed after creation
        created_by=updated_by,
    )

    # Compute manifest hash
    new_doc.manifest_sha256 = _compute_manifest_hash(new_doc)

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return new_doc


def generate_manifest(source_id: str, db: Session) -> Optional[dict[str, Any]]:
    """Generate manifest for a source document.

    The manifest includes all metadata, content hash, and computed manifest hash.
    This can be used for verification and provenance tracking.

    Args:
        source_id: Source identifier
        db: Database session

    Returns:
        Manifest dictionary with sha256, or None if source not found
    """
    doc = get_source_document(db, source_id)
    if doc is None:
        return None

    manifest = {
        "source_id": doc.source_id,
        "version": doc.version,
        "source_type": doc.source_type,
        "title": doc.title,
        "author": doc.author,
        "language": doc.language,
        "content_sha256": doc.content_sha256,
        "manifest_sha256": doc.manifest_sha256,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "created_by": doc.created_by,
        "supersedes": {
            "source_id": doc.supersedes_source_id,
            "version": doc.supersedes_version,
        }
        if doc.supersedes_source_id
        else None,
    }

    # Recompute and verify
    computed_manifest_hash = _compute_manifest_hash(doc)
    manifest["hash_verified"] = computed_manifest_hash == doc.manifest_sha256

    return manifest


def verify_manifest(source_id: str, db: Session) -> dict[str, Any]:
    """Verify manifest integrity for a source document.

    Args:
        source_id: Source identifier
        db: Database session

    Returns:
        Verification result dictionary
    """
    doc = get_source_document(db, source_id)
    if doc is None:
        return {
            "source_id": source_id,
            "exists": False,
            "valid": False,
            "errors": ["Source not found"],
        }

    errors = []

    # Verify content hash
    computed_content_hash = _compute_sha256(doc.content_json)
    content_valid = computed_content_hash == doc.content_sha256
    if not content_valid:
        errors.append(
            f"Content hash mismatch: expected {doc.content_sha256}, got {computed_content_hash}"
        )

    # Verify manifest hash
    computed_manifest_hash = _compute_manifest_hash(doc)
    manifest_valid = computed_manifest_hash == doc.manifest_sha256
    if not manifest_valid:
        errors.append(
            f"Manifest hash mismatch: expected {doc.manifest_sha256}, got {computed_manifest_hash}"
        )

    return {
        "source_id": source_id,
        "version": doc.version,
        "exists": True,
        "valid": content_valid and manifest_valid,
        "content_hash_valid": content_valid,
        "manifest_hash_valid": manifest_valid,
        "errors": errors,
    }


def get_version_history(db: Session, source_id: str) -> list[SourceDocument]:
    """Get complete version history for a source.

    Args:
        db: Database session
        source_id: Source identifier

    Returns:
        List of all versions, ordered from oldest to newest
    """
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_id == source_id)
        .order_by(SourceDocument.version)
    )
    result = db.execute(stmt)
    return list(result.scalars().all())
