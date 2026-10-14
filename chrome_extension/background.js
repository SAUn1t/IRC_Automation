const BRIDGE = "http://127.0.0.1:38417";
const JOURNAL = "https://ircenter.gov.ua/irc/index/conclusions-school";
const POLL_ALARM = "ircenter-job-poll";
let polling = false;

function stageForTab(tab) {
  if (!tab?.url) return null;
  let url;
  try { url = new URL(tab.url); } catch (_) { return null; }
  if (url.origin !== "https://ircenter.gov.ua" || url.hash) return null;
  if (/^\/irc\/index\/conclusions-school(?:\/page\/[1-9]\d*)?\/?$/.test(url.pathname)) {
    const pageQuery = url.pathname === "/irc/index/conclusions-school" &&
      [...url.searchParams.keys()].length === 1 &&
      /^[1-9]\d*$/.test(url.searchParams.get("page") || "");
    if (!url.search || pageQuery) return { stage: "journal" };
  }
  if (url.search) return null;
  if (/^\/irc\/index\/conclusion-iprs\/conclusion_id\/\d+$/.test(url.pathname)) {
    return { stage: "ipr", conclusionUrl: url.href, directEntry: true };
  }
  if (/^\/irc\/index\/filling-ipr\/(?:ipr_id\/\d+\/)?conclusion_id\/\d+$/.test(url.pathname)) {
    return { stage: "form", formUrl: url.href, directEntry: true };
  }
  return null;
}

async function request(path, token, options = {}) {
  const response = await fetch(BRIDGE + path, {
    cache: "no-store",
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "X-IRCenter-Extension-Version": chrome.runtime.getManifest().version,
      ...options.headers,
    },
  });
  if (!response.ok) throw new Error(`Local app returned ${response.status}`);
  return response.json();
}

async function pollForJob() {
  if (polling) return;
  polling = true;
  try {
    const { token } = await chrome.storage.local.get("token");
    if (!token) return;
    const { jobState } = await chrome.storage.session.get("jobState");
    if (jobState) {
      const alive = await request(`/alive?id=${encodeURIComponent(jobState.job.id)}`, token);
      if (alive.active) return;
      await chrome.storage.session.remove("jobState");
    }
    const { extensionVersion } = await request("/version", token);
    const currentVersion = chrome.runtime.getManifest().version;
    const parts = value => /^\d+\.\d+\.\d+$/.test(value || "")
      ? value.split(".").map(Number) : null;
    const target = parts(extensionVersion);
    const current = parts(currentVersion);
    if (!target || !current) return;
    const newer = target.some((part, index) => part > current[index] &&
      target.slice(0, index).every((prior, earlier) => prior === current[earlier]));
    if (newer) {
      const { attemptedReloadVersion } = await chrome.storage.local.get("attemptedReloadVersion");
      if (attemptedReloadVersion !== extensionVersion) {
        await chrome.storage.local.set({ attemptedReloadVersion: extensionVersion });
        chrome.runtime.reload();
        return;
      }
      const { job } = await request("/job", token);
      if (job) await request("/status", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: job.id, type: "error",
          detail: "Chrome extension is outdated. Load it from the installed app folder." }),
      });
      return;
    }
    const { job } = await request("/job", token);
    if (!job) return;
    try {
      const [activeTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      const entry = stageForTab(activeTab);
      if (entry) {
        let scriptVersion;
        try {
          scriptVersion = (await chrome.tabs.sendMessage(activeTab.id, { type: "contentVersion" }))?.version;
        } catch (_) {
          scriptVersion = null;
        }
        if (scriptVersion === currentVersion) {
          await chrome.storage.session.set({ jobState: { job, ...entry, tabId: activeTab.id } });
          const started = await chrome.tabs.sendMessage(activeTab.id, { type: "start" });
          if (!started?.ok) throw new Error("Could not start the current portal script");
        } else if (entry.stage === "form") {
          // Leave any unsaved form edits in the existing tab untouched.
          const tab = await chrome.tabs.create({ url: "about:blank", active: true });
          await chrome.storage.session.set({ jobState: { job, ...entry, tabId: tab.id } });
          await chrome.tabs.update(tab.id, { url: activeTab.url });
        } else {
          await chrome.storage.session.set({ jobState: { job, ...entry, tabId: activeTab.id } });
          await chrome.tabs.reload(activeTab.id);
        }
      } else {
        // Create a blank tab first, so only this tab can read the job before the portal loads.
        const tab = await chrome.tabs.create({ url: "about:blank", active: true });
        await chrome.storage.session.set({ jobState: { job, stage: "journal", tabId: tab.id } });
        await chrome.tabs.update(tab.id, { url: JOURNAL });
      }
      await request("/status", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: job.id, type: "progress", detail: entry
          ? `Continuing from the open ${entry.stage} page in Chrome`
          : "Portal tab opened in the Chrome extension profile" }),
      });
    } catch (_) {
      await chrome.storage.session.remove("jobState");
      await request("/status", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: job.id, type: "error", detail: "Could not open Chrome portal tab" }),
      }).catch(() => {});
    }
  } catch (_) {
    // The app only listens while Process is running. A later alarm will retry.
  } finally {
    polling = false;
  }
}

function schedulePolling() {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
  pollForJob();
}

chrome.runtime.onInstalled.addListener(schedulePolling);
chrome.runtime.onStartup.addListener(schedulePolling);
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === POLL_ALARM) pollForJob();
});
schedulePolling();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const allowed = ["alive", "status", "getState", "setState", "clearState", "pollNow", "restartJournal", "addIprRow"];
  if (sender.id !== chrome.runtime.id || !allowed.includes(message.type)) return false;
  (async () => {
    if (message.type === "pollNow") {
      await pollForJob();
      return { ok: true };
    }
    if (message.type === "getState") {
      const { jobState } = await chrome.storage.session.get("jobState");
      return { state: jobState?.tabId === sender.tab?.id ? jobState : null };
    }
    if (message.type === "addIprRow") {
      const { jobState } = await chrome.storage.session.get("jobState");
      const functions = new Set(["addSection5Row29", "addSection6Row1", "addSection7Row1", "addSection10Row1"]);
      if (!jobState || jobState.stage !== "form" || jobState.tabId !== sender.tab?.id ||
          jobState.job.id !== message.id || !functions.has(message.name) ||
          (sender.url || sender.tab.url) !== jobState.formUrl) {
        return { error: "This form cannot add the requested row" };
      }
      try {
        const [injection] = await chrome.scripting.executeScript({
          target: { tabId: sender.tab.id }, world: "MAIN", args: [message.name],
          func: name => {
            try {
              if (typeof window[name] !== "function") return { error: "Portal row function is unavailable" };
              window[name]();
              return { ok: true };
            } catch (_) {
              return { error: "Portal row function failed" };
            }
          },
        });
        return injection?.result || { error: "Portal row function returned no result" };
      } catch (_) {
        return { error: "Chrome could not run the portal row function" };
      }
    }
    if (["setState", "clearState", "restartJournal"].includes(message.type)) {
      const { jobState } = await chrome.storage.session.get("jobState");
      if (!jobState || jobState.tabId !== sender.tab?.id) {
        return { error: "This tab does not own the extension job" };
      }
      if (message.type === "clearState") {
        await chrome.storage.session.remove("jobState");
        return { ok: true };
      }
      if (message.type === "restartJournal") {
        if (!jobState.directEntry || message.id !== jobState.job.id) {
          return { error: "Cannot restart this extension job" };
        }
        const { token } = await chrome.storage.local.get("token");
        const alive = await request(`/alive?id=${encodeURIComponent(jobState.job.id)}`, token);
        if (!alive.active) return { error: "Local app job is no longer active" };
        const tab = await chrome.tabs.create({ url: "about:blank", active: true });
        await chrome.storage.session.set({
          jobState: { job: jobState.job, stage: "journal", tabId: tab.id },
        });
        await chrome.tabs.update(tab.id, { url: JOURNAL });
        return { ok: true };
      }
      const state = message.state;
      if (state?.job?.id !== jobState.job.id || state.tabId !== jobState.tabId ||
          !["journal", "ipr", "form"].includes(state.stage)) {
        return { error: "Invalid extension job state" };
      }
      await chrome.storage.session.set({ jobState: state });
      return { ok: true };
    }
    const { token } = await chrome.storage.local.get("token");
    if (!token) return { error: "Extension is not paired" };
    if (message.type === "alive") {
      return request(`/alive?id=${encodeURIComponent(message.id)}`, token);
    }
    return request("/status", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: message.id, type: message.status, detail: message.detail || "" }),
    });
  })().then(sendResponse).catch(() => sendResponse({ error: "Local app is not connected" }));
  return true;
});
