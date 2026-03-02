# @islam-intelligent/schemas

Shared JSON schemas and SQL migrations for the Islam Intelligent knowledge platform.

## Purpose

This package defines the canonical data schemas used across the platform:
- **JSON Schemas**: For runtime validation and type generation
- **SQL Migrations**: For database schema evolution

## Directory Structure

```
packages/schemas/
├── json/               # JSON Schema definitions
│   ├── source_document.json   # Source registry schema
│   └── text_unit.json         # Text unit schema
├── sql/                # SQL migrations
│   └── 0001_init.sql          # Initial migration (placeholder)
└── package.json
```

## Status

⚠️ **PLACEHOLDER STRUCTURE** - Full schemas will be implemented in Task 5

Current state:
- ✅ Directory structure created
- ⏳ Schemas awaiting implementation (Task 5)
- ⏳ Migrations awaiting implementation (Task 5)

## Usage

```javascript
// Import schemas
import sourceDocumentSchema from '@islam-intelligent/schemas/json/source_document.json' assert { type: 'json' };
```

## Schema Design Principles

1. **Provenance-First**: Every schema includes source tracking fields
2. **Extensible**: Base schemas allow domain-specific extensions
3. **Versioned**: Schemas include version identifiers for migration support
4. **Validated**: All data passes schema validation before storage

## Related

- Task 5: Schema locking and full implementation
- Master Plan: Data architecture specification
