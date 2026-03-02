# Learnings: spanHighlighter
- Implemented a UTF-8 byte offset to UTF-16 character range converter for JS strings.
- Used TextEncoder/TextDecoder to compute per-code-point byte boundaries and map to UTF-16 indices.
- Created unit tests covering Arabic multi-byte text to verify edge cases.
- Ensured no direct string.slice on byte ranges; calculations respect multi-byte lengths.
- Files created: apps/ui/src/lib/spanHighlighter.ts and apps/ui/src/lib/spanHighlighter.test.ts
