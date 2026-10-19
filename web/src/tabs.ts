// Multi-document tab strip. Every open document stays mounted (hidden when
// inactive) so switching tabs never blanks or re-fetches a view; the switch
// is an opacity fade only.
import { h } from "./shell";
import { navigate } from "./router";

export interface DocDef {
  id: string;
  title: string;
  flush?: boolean; // no padding / no scroll (canvas)
  mount: (el: HTMLElement) => void;
}

export class DocTabs {
  private open: string[] = [];
  private panes = new Map<string, HTMLElement>();
  active = "";

  constructor(
    private strip: HTMLElement,
    private host: HTMLElement,
    private lookup: (id: string) => DocDef,
    private onChange: (open: string[], active: string) => void = () => {},
  ) {}

  show(id: string): void {
    if (!this.panes.has(id)) {
      const def = this.lookup(id);
      const pane = h("div", `doc${def.flush ? " flush" : ""}`);
      pane.setAttribute("role", "tabpanel");
      pane.dataset.doc = id;
      this.host.append(pane);
      this.panes.set(id, pane);
      this.open.push(id);
      def.mount(pane);
    }
    this.active = id;
    for (const [k, p] of this.panes) p.classList.toggle("active", k === id);
    this.paint();
  }

  close(id: string): void {
    const i = this.open.indexOf(id);
    if (i < 0) return;
    this.open.splice(i, 1);
    this.panes.get(id)?.remove();
    this.panes.delete(id);
    if (this.active === id) {
      const next = this.open[Math.min(i, this.open.length - 1)];
      if (next) navigate(next);
      else navigate("canvas");
    } else {
      this.paint();
    }
  }

  ids(): string[] {
    return [...this.open];
  }

  private paint(): void {
    const items = this.open.map((id) => {
      const t = h("div", `tab${id === this.active ? " active" : ""}`);
      t.setAttribute("role", "tab");
      t.setAttribute("aria-selected", String(id === this.active));
      t.dataset.doc = id;
      t.append(h("span", "", this.lookup(id).title));
      const x = h("span", "x", "×");
      x.title = "Close";
      x.addEventListener("click", (e) => {
        e.stopPropagation();
        this.close(id);
      });
      t.append(x);
      t.addEventListener("click", () => navigate(id));
      t.addEventListener("auxclick", (e) => {
        if (e.button === 1) this.close(id);
      });
      return t;
    });
    this.strip.replaceChildren(...items);
    this.strip.querySelector(".tab.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    this.onChange(this.ids(), this.active);
  }
}
