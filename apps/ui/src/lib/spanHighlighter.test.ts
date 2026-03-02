import { describe, expect, it } from 'vitest';
import { byteOffsetsToStringRange } from './spanHighlighter';

describe('byteOffsetsToStringRange', () => {
  it('returns full text for full UTF-8 byte range', () => {
    const text = 'مرحبا بالعالم';
    const totalBytes = new TextEncoder().encode(text).length;

    const full = byteOffsetsToStringRange(text, 0, totalBytes);
    expect(full.startChar).toBe(0);
    expect(full.endChar).toBe(text.length);
    expect(full.snippet).toBe(text);
  });

  it('maps the end of the first Unicode code point', () => {
    const text = 'مرحبا بالعالم';
    const encoder = new TextEncoder();

    const firstCodePointLen = text.codePointAt(0)! > 0xffff ? 2 : 1;
    const endOfFirstCodePointBytes = encoder.encode(text.slice(0, firstCodePointLen)).length;
    const firstCp = byteOffsetsToStringRange(text, 0, endOfFirstCodePointBytes);

    expect(firstCp.snippet).toBe(text.slice(0, firstCodePointLen));
    expect(firstCp.startChar).toBe(0);
    expect(firstCp.endChar).toBe(firstCodePointLen);
  });
});
