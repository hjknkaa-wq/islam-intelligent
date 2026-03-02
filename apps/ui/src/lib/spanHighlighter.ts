export function byteOffsetsToStringRange(text: string, startByte: number, endByte: number): { startChar: number; endChar: number; snippet: string } {
  const encoder = new TextEncoder();
  // Build per-code-point UTF-16 span and corresponding UTF-8 end byte
  type CPInfo = { startChar: number; endChar: number; endByte: number };
  const codePoints: CPInfo[] = [];
  let pos = 0;
  let cumBytes = 0;
  // Precompute total utf-8 bytes
  const utf8Total = encoder.encode(text).length;
  while (pos < text.length) {
    const cp = text.codePointAt(pos)!;
    const utf16Len = cp > 0xffff ? 2 : 1;
    const chunk = text.slice(pos, pos + utf16Len);
    const bLen = encoder.encode(chunk).length;
    codePoints.push({ startChar: pos, endChar: pos + utf16Len, endByte: cumBytes + bLen });
    cumBytes += bLen;
    pos += utf16Len;
  }
  const S = Math.max(0, Math.min(startByte, utf8Total));
  const E = Math.max(0, Math.min(endByte, utf8Total));
  const s = Math.min(S, E);
  const e = Math.max(S, E);
  // Find start: first code point whose endByte > s
  let startIndex = -1;
  for (let i = 0; i < codePoints.length; i++) {
    if (codePoints[i].endByte > s) {
      startIndex = i;
      break;
    }
  }
  if (startIndex === -1) {
    // span starts after the last code point
    return { startChar: text.length, endChar: text.length, snippet: "" };
  }
  const startChar = codePoints[startIndex].startChar;
  // Find end: last code point whose endByte <= e
  let endIndex = -1;
  for (let i = 0; i < codePoints.length; i++) {
    if (codePoints[i].endByte <= e) endIndex = i;
    else break;
  }
  const endChar = endIndex >= 0 ? codePoints[endIndex].endChar : startChar;
  const snippet = text.substring(startChar, endChar);
  return { startChar, endChar, snippet };
}
