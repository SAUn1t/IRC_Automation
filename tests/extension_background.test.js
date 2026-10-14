const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const listeners = {};
const storage = { local: { token: "test-token" }, session: {} };
const tabs = [];
const starts = [];
const requests = [];
const chrome = {
  runtime: {
    id: "test-extension-id",
    getManifest: () => ({ version: "1.1.0" }),
    reload: () => { throw new Error("Unexpected extension reload"); },
    onInstalled: { addListener: fn => { listeners.installed = fn; } },
    onStartup: { addListener: fn => { listeners.startup = fn; } },
    onMessage: { addListener: fn => { listeners.message = fn; } },
  },
  alarms: {
    create: () => {},
    onAlarm: { addListener: fn => { listeners.alarm = fn; } },
  },
  storage: {
    local: {
      get: async () => storage.local,
      set: async value => Object.assign(storage.local, value),
    },
    session: {
      get: async () => storage.session,
      set: async value => Object.assign(storage.session, value),
      remove: async key => { delete storage.session[key]; },
    },
  },
  tabs: {
    query: async () => [],
    sendMessage: async (id, message) => { starts.push({ id, message }); },
    reload: async () => { throw new Error("Unexpected reload"); },
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
  if (url.endsWith("/version")) {
    return { ok: true, json: async () => ({ extensionVersion: "1.1.0" }) };
  }
  if (url.endsWith("/job")) {
    return { ok: true, json: async () => ({ job: { id: "job-1" } }) };
  }
  return { ok: true, json: async () => ({ active: true }) };
}

const source = fs.readFileSync("chrome_extension/background.js", "utf8");
vm.runInNewContext(source, { chrome, fetch, URL, encodeURIComponent });

function message(type, tabId, extra = {}) {
  return new Promise(resolve => {
    listeners.message({ type, ...extra }, { id: chrome.runtime.id, tab: { id: tabId } }, resolve);
  });
}

(async () => {
  // The worker starts polling as soon as Chrome loads the installed extension.
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(tabs.length, 1);
  assert.equal(tabs[0].url, "https://ircenter.gov.ua/irc/index/conclusions-school");
  assert.equal(storage.session.jobState.tabId, 7);
  assert.equal(requests[0].options.headers.Authorization, "Bearer test-token");
  assert.equal(requests[2].options.headers.Authorization, "Bearer test-token");
  assert.equal(JSON.parse(requests[2].options.body).type, "progress");
  assert.equal((await message("getState", 8)).state, null);
  assert.equal((await message("getState", 7)).state.job.id, "job-1");
  assert.equal((await message("clearState", 8)).error, "This tab does not own the extension job");
  assert.equal(storage.session.jobState.job.id, "job-1");

  await message("clearState", 7);
  chrome.tabs.query = async () => [{
    id: 8, url: "https://ircenter.gov.ua/irc/index/conclusion-iprs/conclusion_id/42",
  }];
  listeners.alarm({ name: "ircenter-job-poll" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(storage.session.jobState.stage, "ipr");
  assert.equal(storage.session.jobState.directEntry, true);
  assert.equal(storage.session.jobState.conclusionUrl,
    "https://ircenter.gov.ua/irc/index/conclusion-iprs/conclusion_id/42");
  assert.equal(starts[0].id, 8);
  assert.equal(starts[0].message.type, "start");
  assert.equal(tabs.length, 1);

  await message("clearState", 8);
  chrome.tabs.query = async () => [{
    id: 9, url: "https://ircenter.gov.ua/irc/index/filling-ipr/ipr_id/99/conclusion_id/42",
  }];
  listeners.alarm({ name: "ircenter-job-poll" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(storage.session.jobState.stage, "form");
  assert.equal(storage.session.jobState.tabId, 9);
  assert.equal(starts[1].id, 9);
  assert.equal(starts[1].message.type, "start");
  assert.equal(tabs.length, 1);

  assert.equal((await message("restartJournal", 8, { id: "job-1" })).error,
    "This tab does not own the extension job");
  assert.equal((await message("restartJournal", 9, { id: "job-1" })).ok, true);
  assert.equal(storage.session.jobState.stage, "journal");
  assert.equal(tabs.length, 2);

  await message("clearState", 7);
  chrome.tabs.query = async () => [{
    id: 10, url: "https://ircenter.gov.ua/irc/index/conclusions-school",
  }];
  listeners.alarm({ name: "ircenter-job-poll" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(storage.session.jobState.stage, "journal");
  assert.equal(storage.session.jobState.tabId, 10);
  assert.equal(starts[2].id, 10);
  assert.equal(tabs.length, 2);

  await message("clearState", 10);
  chrome.tabs.query = async () => [{
    id: 11, url: "https://ircenter.gov.ua/irc/index/conclusions-search",
  }];
  listeners.alarm({ name: "ircenter-job-poll" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(storage.session.jobState.stage, "journal");
  assert.equal(tabs.length, 3);

  await message("clearState", 7);
  let reloads = 0;
  chrome.runtime.getManifest = () => ({ version: "1.0.0" });
  chrome.runtime.reload = () => { reloads += 1; };
  listeners.alarm({ name: "ircenter-job-poll" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(reloads, 1);
  assert.equal(storage.local.attemptedReloadVersion, "1.1.0");
  listeners.alarm({ name: "ircenter-job-poll" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(reloads, 1);
  assert.equal(JSON.parse(requests.at(-1).options.body).type, "error");
  console.log("extension background handoff passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
