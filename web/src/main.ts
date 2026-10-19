import "./tokens.css";
import "./workspace.css";
import { mountBusy } from "./busy";
import { lookupDoc } from "./docs";
import { onRoute } from "./router";
import { buildShell, h } from "./shell";
import { DocTabs } from "./tabs";

const shell = buildShell(document.getElementById("app")!);
mountBusy(shell.busy);

shell.readouts.innerHTML =
  "<div><span>Case</span>-</div><div><span>Buses / Branches</span>- / -</div>" +
  "<div><span>Base</span>-</div><div><span>Limits</span>-</div><div><span>Solution</span>-</div>";
shell.status.innerHTML =
  "<div><b>Solver</b>-</div><div><b>Iterations</b>-</div><div><b>Tolerance</b>-</div>" +
  "<div class='fill'><b>Status</b>Ready</div><div class='file'>untitled.gridlens.json</div>";
const msgTab = h("div", "tab active", "Messages");
shell.outTabs.append(msgTab);
shell.props.append(h("div", "empty", "Nothing selected."));

const tabs = new DocTabs(shell.tabs, shell.docs, lookupDoc);
onRoute("canvas", (id) => tabs.show(id));
