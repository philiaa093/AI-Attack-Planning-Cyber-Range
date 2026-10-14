/** Keep absent measurements distinct from a measured zero. */
export const recordedValue = (value: unknown): string =>
  value === null || value === undefined ? '—' : String(value);
