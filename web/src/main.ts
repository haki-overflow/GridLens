// Entry point.
// Sections follow the order of the files this one replaced; search for '// ----'.
import "./tokens.css";
import "./workspace.css";
import "./canvas";
import { currentDoc, getState, mountBusy, onRoute, setState } from "./app";
import { lookupDoc } from "./documents";
import { mountTree } from "./panels";
import { DocTabs, buildShell, mountChrome, mountToolbar } from "./shell";

// ---- main --------------------------------------------------------------

const shell = buildShell(document.getElementById("app")!);
mountBusy(shell.busy);
mountChrome(shell.readouts, shell.status, shell.outTabs, shell.out, shell.props);
mountToolbar(shell.tools);
mountTree(shell.tree);

const tabs = new DocTabs(shell.tabs, shell.docs, lookupDoc,
  (open, active) => setState({ openDocs: open, activeDoc: active }));

// reopen the documents of the last session, then follow the URL
const s = getState();
const start = currentDoc(s.activeDoc || "canvas");
onRoute(start, (id) => tabs.show(id));
