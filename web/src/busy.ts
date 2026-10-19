// Thin progress bar under the toolbar. Requests nest: the bar shows while
// any is running. The screen is never blanked; views keep old results.
let count = 0;
let bar: HTMLElement | null = null;

export function mountBusy(el: HTMLElement): void {
  bar = el;
}

function paint(): void {
  bar?.classList.toggle("on", count > 0);
}

export async function busy<T>(work: Promise<T>): Promise<T> {
  count += 1;
  paint();
  try {
    return await work;
  } finally {
    count -= 1;
    paint();
  }
}
