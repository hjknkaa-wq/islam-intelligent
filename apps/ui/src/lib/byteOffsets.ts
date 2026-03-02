/** UTF-8 byte offset utilities for highlighting evidence spans
 * 
 * Critical: JavaScript strings are UTF-16, NOT UTF-8.
 * We cannot use string.slice(start_byte, end_byte) directly.
 * 
 * Steps:
 * 1. Encode text to UTF-8 bytes (Uint8Array)
 * 2. Extract byte range from the array
 * 3. Decode back to string for display
 */

/**
 * Convert string to UTF-8 bytes
 */
export function stringToUtf8Bytes(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

/**
 * Convert UTF-8 bytes to string
 */
export function utf8BytesToString(bytes: Uint8Array): string {
  return new TextDecoder('utf-8').decode(bytes);
}

/**
 * Extract snippet from text using UTF-8 byte offsets
 * 
 * @param text - Full text
 * @param startByte - Starting byte offset (inclusive)
 * @param endByte - Ending byte offset (exclusive)
 * @returns Extracted snippet
 */
export function extractSnippetByByteOffsets(
  text: string,
  startByte: number,
  endByte: number
): string {
  const bytes = stringToUtf8Bytes(text);
  
  // Validate offsets
  if (startByte < 0 || endByte > bytes.length || startByte >= endByte) {
    throw new Error(
      `Invalid byte offsets: [${startByte}, ${endByte}] for text of ${bytes.length} bytes`
    );
  }
  
  // Extract byte range
  const snippetBytes = bytes.slice(startByte, endByte);
  
  // Decode back to string
  return utf8BytesToString(snippetBytes);
}

/**
 * Find character position from byte offset
 * Useful for mapping byte offsets to string indices
 */
export function byteOffsetToCharIndex(text: string, byteOffset: number): number {
  const bytes = stringToUtf8Bytes(text);
  
  if (byteOffset < 0 || byteOffset > bytes.length) {
    return -1;
  }
  
  // Take bytes up to the offset and decode
  const prefixBytes = bytes.slice(0, byteOffset);
  const prefix = utf8BytesToString(prefixBytes);
  
  return prefix.length;
}

/**
 * Get character range from byte offsets
 */
export function byteOffsetsToCharRange(
  text: string,
  startByte: number,
  endByte: number
): { startChar: number; endChar: number } {
  return {
    startChar: byteOffsetToCharIndex(text, startByte),
    endChar: byteOffsetToCharIndex(text, endByte),
  };
}

/**
 * Split text into before, highlighted, and after segments
 */
export function splitTextForHighlight(
  text: string,
  startByte: number,
  endByte: number
): { before: string; highlighted: string; after: string } {
  const { startChar, endChar } = byteOffsetsToCharRange(text, startByte, endByte);
  
  return {
    before: text.slice(0, startChar),
    highlighted: text.slice(startChar, endChar),
    after: text.slice(endChar),
  };
}

/**
 * Compute SHA-256 hash of UTF-8 bytes
 */
export async function computeHash(text: string): Promise<string> {
  const bytes = stringToUtf8Bytes(text);
  const hashBuffer = await crypto.subtle.digest('SHA-256', bytes as unknown as BufferSource);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Verify that text matches expected hash
 */
export async function verifyHash(text: string, expectedHash: string): Promise<boolean> {
  const actualHash = await computeHash(text);
  return actualHash === expectedHash.toLowerCase();
}
