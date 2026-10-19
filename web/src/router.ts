// Hash routing: #/doc/<id> opens (or focuses) that document tab.
export function docHref(id: string): string {
  return `#/doc/${id}`;
}

export function currentDoc(fallback: string): string {
  const m = /^#\/doc\/([\w-]+)/.exec(location.hash);
  return m?.[1] ?? fallback;
}

export function onRoute(fallback: string, open: (id: string) => void): void {
  const go = () => open(currentDoc(fallback));
  window.addEventListener("hashchange", go);
  go();
}

export function navigate(id: string): void {
  if (location.hash !== docHref(id)) location.hash = docHref(id);
}
