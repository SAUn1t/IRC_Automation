const BRIDGE = "http://127.0.0.1:38417";
const JOURNAL = "https://ircenter.gov.ua/irc/index/conclusions-school";
const POLL_ALARM = "ircenter-job-poll";
let polling = false;

async function request(path, token, options = {}) {
  const response = await fetch(BRIDGE + path, {
    cache: "no-store",
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...options.headers },
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
    const { job } = await request("/job", token);
    if (!job) return;
    try {
      // Create a blank tab first, so only this tab can read the job before the portal loads.
      const tab = await chrome.tabs.create({ url: "about:blank", active: true });
      await chrome.storage.session.set({ jobState: { job, stage: "journal", tabId: tab.id } });
      await chrome.tabs.update(tab.id, { url: JOURNAL });
      await request("/status", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: job.id, type: "progress", detail: "Portal tab opened in the Chrome extension profile" }),
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
  const allowed = ["alive", "status", "getState", "setState", "clearState", "pollNow"];
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
    if (message.type === "setState" || message.type === "clearState") {
      const { jobState } = await chrome.storage.session.get("jobState");
      if (!jobState || jobState.tabId !== sender.tab?.id) {
        return { error: "This tab does not own the extension job" };
      }
      if (message.type === "clearState") {
        await chrome.storage.session.remove("jobState");
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
