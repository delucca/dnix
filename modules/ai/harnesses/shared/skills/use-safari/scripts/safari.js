// Apple Events runner for safari.py: reads one JSON request on stdin, prints one JSON reply.
// The request comes on stdin, not argv, so a value moved by `copy` never shows in `ps`.
ObjC.import("Foundation");
ObjC.import("AppKit");

class Refusal extends Error {}

function readRequest() {
  const data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  return JSON.parse($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding).js);
}

function browserWindows(safari) {
  const out = [];
  for (const w of safari.windows()) {
    try {
      if (w.tabs.url().length > 0) out.push(w);
    } catch (e) {}
  }
  return out;
}

const idOf = (w, t) => `${w.id()}:${t.index()}`;

function resolveTab(safari, spec) {
  const wins = browserWindows(safari);
  if (!wins.length) throw new Refusal("Safari has no browser windows open");
  if (spec === null || spec === undefined || spec === "") return { w: wins[0], t: wins[0].currentTab() };
  const m = /^(\d+):(\d+)$/.exec(spec);
  if (m) {
    const w = wins.find((w) => w.id() === Number(m[1]));
    if (!w) throw new Refusal(`no Safari window has id ${m[1]}; run tabs`);
    const tabs = w.tabs();
    const i = Number(m[2]);
    if (i < 1 || i > tabs.length) throw new Refusal(`window ${m[1]} has ${tabs.length} tabs, not ${i}; run tabs`);
    return { w, t: tabs[i - 1] };
  }
  const needle = spec.toLowerCase();
  const hits = [];
  for (const w of wins) {
    const urls = w.tabs.url();
    const names = w.tabs.name();
    urls.forEach((url, i) => {
      if ((url || "").toLowerCase().includes(needle) || (names[i] || "").toLowerCase().includes(needle)) {
        hits.push({ w, i, url: url || "" });
      }
    });
  }
  if (!hits.length) throw new Refusal(`no tab matches "${spec}"; run tabs`);
  if (hits.length > 1) {
    const list = hits.map((h) => `${h.w.id()}:${h.i + 1} ${h.url.split(/[?#]/)[0]}`).join(", ");
    throw new Refusal(`${hits.length} tabs match "${spec}" (${list}); pass a window:tab id`);
  }
  return { w: hits[0].w, t: hits[0].w.tabs()[hits[0].i] };
}

const ops = {
  tabs(safari) {
    return {
      windows: browserWindows(safari).map((w) => {
        const current = w.currentTab().index();
        const names = w.tabs.name();
        return {
          id: w.id(),
          tabs: w.tabs.url().map((url, i) => ({ index: i + 1, title: names[i] || "", url: url || "", current: i + 1 === current })),
        };
      }),
    };
  },

  info(safari, req) {
    const { w, t } = resolveTab(safari, req.tab);
    return { tab: idOf(w, t), title: t.name() || "", url: t.url() || "" };
  },

  js(safari, req) {
    const { w, t } = resolveTab(safari, req.tab);
    const result = safari.doJavaScript(req.code, { in: t });
    return { tab: idOf(w, t), result: result === undefined ? null : result };
  },

  navigate(safari, req) {
    if (req.tab) {
      const { w, t } = resolveTab(safari, req.tab);
      t.url = req.url;
      return { tab: idOf(w, t) };
    }
    const wins = browserWindows(safari);
    if (!wins.length) throw new Refusal("Safari has no browser windows open; open one first");
    const w = wins[0];
    const t = safari.Tab({ url: req.url });
    w.tabs.push(t);
    w.currentTab = t;
    return { tab: idOf(w, w.currentTab()) };
  },

  close(safari, req) {
    const { w, t } = resolveTab(safari, req.tab);
    const closed = { tab: idOf(w, t), url: t.url() || "" };
    t.close();
    return closed;
  },

  front(safari, req) {
    const { w, t } = resolveTab(safari, req.tab);
    const prev = $.NSWorkspace.sharedWorkspace.frontmostApplication.bundleIdentifier.js;
    w.currentTab = t;
    w.index = 1;
    safari.activate();
    return { tab: idOf(w, t), windowId: w.id(), prev: prev || null };
  },

  activate(safari, req) {
    Application(req.bundle).activate();
    return {};
  },

  copy(safari, req) {
    const src = resolveTab(safari, req.from);
    const dst = resolveTab(safari, req.to);
    let read;
    try {
      read = JSON.parse(safari.doJavaScript(req.readCode, { in: src.t }));
    } catch (e) {
      throw new Refusal("the source tab returned nothing; the code did not parse, or that tab cannot run scripts");
    }
    if (read.pending) throw new Refusal("the read returned a promise; copy needs a value the page holds now");
    if (!read.ok) throw new Refusal(`reading the source tab failed: ${read.error}`);
    let value = read.v === null || read.v === undefined ? "" : String(read.v);
    if (!value) throw new Refusal("the source read returned an empty value");
    if (req.expectPrefix && !value.startsWith(req.expectPrefix)) {
      throw new Refusal(`the value read does not start with "${req.expectPrefix}"; nothing was filled`);
    }
    const code = req.fillTemplate.split(req.placeholder).join(JSON.stringify(value));
    let fill;
    try {
      fill = JSON.parse(safari.doJavaScript(code, { in: dst.t }));
    } catch (e) {
      throw new Refusal("the destination tab returned nothing; it cannot run scripts");
    }
    const length = value.length;
    value = "";
    if (!fill.ok) throw new Refusal(`filling the destination failed: ${fill.error}`);
    if (fill.v && fill.v.error) throw new Refusal(`filling the destination failed: ${fill.v.error}`);
    return { from: idOf(src.w, src.t), to: idOf(dst.w, dst.t), length, filled: fill.v ? fill.v.filled : null };
  },
};

function run() {
  let req;
  try {
    req = readRequest();
  } catch (e) {
    return JSON.stringify({ ok: false, error: `bad request: ${e.message}` });
  }
  const op = ops[req.op];
  if (!op) return JSON.stringify({ ok: false, error: `unknown op ${req.op}` });
  const safari = Application("Safari");
  if (!safari.running()) return JSON.stringify({ ok: false, error: "Safari is not running; open it with `open -a Safari`" });
  try {
    return JSON.stringify(Object.assign({ ok: true }, op(safari, req)));
  } catch (e) {
    const code = e instanceof Refusal ? null : e.errorNumber === undefined ? null : e.errorNumber;
    return JSON.stringify({ ok: false, error: e.message, code, appleEvent: !(e instanceof Refusal) });
  }
}
