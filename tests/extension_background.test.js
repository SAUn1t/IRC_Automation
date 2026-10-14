const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const listeners = {};
const storage = { local: { token: "test-token" }, session: {} };
const tabs = [];
const requests = [];
const chrome = {
  runtime: {
    id: "test-extension-id",
    onInstalled: { addListener: fn => { listeners.installed = fn; } },
    onStartup: { addListener: fn => { listeners.startup = fn; } },
    onMessage: { addListener: fn => { listeners.message = fn; } },
  },
  alarms: {
    create: () => {},
    onAlarm: { addListener: fn => { listeners.alarm = fn; } },
  },
  storage: {
    local: { get: async () => storage.local },
    session: {
      get: async () => storage.session,
      set: async value => Object.assign(storage.session, value),
      remove: async key => { delete storage.session[key]; },
    },
  },
  tabs: {
    create: async options => {
      const tab = { id: 7, ...options };
      tabs.push(tab);
      return tab;
    },
    update: async (id, options) => {
      assert.equal(id, 7);
      Object.assign(tabs[0], options);
    },
  },
};

async function fetch(url, options) {
  requests.push({ url, options });
  if (url.endsWith("/job")) {
    return { ok: true, json: async () => ({ job: { id: "job-1" } }) };
  }
  return { ok: true, json: async () => ({ active: true }) };
}

const source = fs.readFileSync("chrome_extension/background.js", "utf8");
vm.runInNewContext(source, { chrome, fetch, URL, encodeURIComponent });

function message(type, tabId) {
  return new Promise(resolve => {
    listeners.message({ type }, { id: chrome.runtime.id, tab: { id: tabId } }, resolve);
  });
}

(async () => {
  // The worker starts polling as soon as Chrome loads the installed extension.
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(tabs.length, 1);
  assert.equal(tabs[0].url, "https://ircenter.gov.ua/irc/index/conclusions-school");
  assert.equal(storage.session.jobState.tabId, 7);
  assert.equal(requests[0].options.headers.Authorization, "Bearer test-token");
  assert.equal(requests[1].options.headers.Authorization, "Bearer test-token");
  assert.equal(JSON.parse(requests[1].options.body).type, "progress");
  assert.equal((await message("getState", 8)).state, null);
  assert.equal((await message("getState", 7)).state.job.id, "job-1");
  assert.equal((await message("clearState", 8)).error, "This tab does not own the extension job");
  assert.equal(storage.session.jobState.job.id, "job-1");
  console.log("extension background handoff passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
