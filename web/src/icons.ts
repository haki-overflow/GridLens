// Small inline SVG icons (16x16 viewBox, currentColor).
const svg = (body: string) =>
  `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" ` +
  `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const ICON = {
  run: svg('<path d="M4 3l9 5-9 5z" fill="currentColor" stroke="none"/>'),
  reset: svg('<path d="M3 8a5 5 0 1 0 1.5-3.5"/><path d="M3 2.5v3h3"/>'),
  open: svg('<path d="M2 4h4l1.5 1.5H14v7.5H2z"/>'),
  save: svg('<path d="M8 2v8M5 7l3 3 3-3"/><path d="M3 12v2h10v-2"/>'),
  fit: svg('<path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/>'),
  grid: svg('<path d="M2 5.5h12M2 10.5h12M5.5 2v12M10.5 2v12"/>'),
  flows: svg('<path d="M2 8h10M9 5l3 3-3 3"/>'),
  angles: svg('<path d="M2 13h11M2 13l8-8"/><path d="M7 13a5 5 0 0 0-1.5-3.5"/>'),
  report: svg('<path d="M4 2h6l3 3v9H4z"/><path d="M6 8h5M6 10.5h5M6 5.5h2"/>'),
  project: svg('<path d="M2 4h4l1.5 1.5H14v7.5H2z"/>'),
  case: svg('<rect x="2.5" y="2.5" width="11" height="11"/><path d="M5 6h6M5 10h6"/>'),
  folder: svg('<path d="M2 4h4l1.5 1.5H14v7.5H2z"/>'),
  bus: svg('<path d="M2 8h12" stroke-width="2.4"/>'),
  branch: svg('<path d="M3 13L13 3"/><circle cx="3" cy="13" r="1.4"/><circle cx="13" cy="3" r="1.4"/>'),
  study: svg('<path d="M2 13l3.5-5 3 3L14 3"/>'),
  doc: svg('<path d="M4 2h6l3 3v9H4z"/>'),
  calc: svg('<rect x="3" y="2" width="10" height="12"/><path d="M5.5 5h5M5.5 8h1M9.5 8h1M5.5 11h1M9.5 11h1"/>'),
  chev: svg('<path d="M6 4l4 4-4 4"/>'),
};
