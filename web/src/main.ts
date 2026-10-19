import "./tokens.css";
import "./workspace.css";
import "./views";
import "./canvas";
import { mountBusy } from "./busy";
import { mountChrome } from "./chrome";
import { DOC_TITLES, lookupDoc } from "./docs";
import { currentDoc, onRoute } from "./router";
import { buildShell } from "./shell";
import { getState, setState } from "./state";
import { DocTabs } from "./tabs";
import { mountToolbar } from "./toolbar";

const shell = buildShell(document.getElementById("app")!);
mountBusy(shell.busy);
mountChrome(shell.readouts, shell.status, shell.outTabs, shell.out, shell.props);
mountToolbar(shell.tools);

const tabs = new DocTabs(shell.tabs, shell.docs, lookupDoc,
  (open, active) => setState({ openDocs: open, activeDoc: active }));

// reopen the documents of the last session, then follow the URL
const s = getState();
const start = currentDoc(s.activeDoc || "canvas");
for (const id of s.openDocs) if (id in DOC_TITLES && id !== start) tabs.show(id);
onRoute(start, (id) => tabs.show(id));
