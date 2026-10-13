(() => {
  const SITE = "https://ircenter.gov.ua";
  const JOURNAL = "/irc/index/conclusions-school";
  const normalize = value => String(value || "").normalize("NFC").replace(/\s+/g, " ").trim();
  const same = (left, right) => normalize(left).toLocaleLowerCase("uk") === normalize(right).toLocaleLowerCase("uk");

  function fullNameMatches(value, child) {
    const words = normalize(value).split(" ");
    if (words.length !== 3) throw new Error("A portal child name is not a clear three-part name");
    return same(words[0], child.surname) && same(words[1], child.first);
  }

  function checkedUrl(href, pattern, allowQuery = false) {
    const url = new URL(href, location.href);
    if (url.origin !== SITE || !pattern.test(url.pathname) || (!allowQuery && url.search) || url.hash) {
      throw new Error("Portal link does not match the expected route");
    }
    return url;
  }

  async function save(state) {
    const reply = await chrome.runtime.sendMessage({ type: "setState", state });
    if (reply?.error) throw new Error("Could not save extension job state");
  }
  async function clear() { await chrome.runtime.sendMessage({ type: "clearState" }); }

  async function report(state, status, detail) {
    const reply = await chrome.runtime.sendMessage({ type: "status", id: state.job.id, status, detail });
    if (reply?.error) throw new Error("Local app connection was lost");
  }

  async function waitFor(selector) {
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      const element = document.querySelector(selector);
      if (element) return element;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    throw new Error("Expected portal content did not appear");
  }

  function journalPage(doc, job, matches) {
    const table = doc.querySelector("table.zebra-stripe.list");
    if (!table) throw new Error("Conclusions journal table is missing");
    for (const row of table.querySelectorAll("tr")) {
      if (row.cells.length < 8) continue;
      const nameLink = row.cells[1].querySelector("a");
      if (!nameLink) continue;
      if (fullNameMatches(nameLink.textContent, job.child)) {
        const iprLink = row.cells[7].querySelector("a[href]");
        if (!iprLink) throw new Error("Matching journal row has no IPR link");
        matches.push(checkedUrl(iprLink.getAttribute("href"), /^\/irc\/index\/conclusion-iprs\/conclusion_id\/\d+$/));
      }
    }
    const nextLinks = [...doc.querySelectorAll("#pagination-digg a[href]")]
      .filter(link => normalize(link.textContent).startsWith("Далі"));
    if (nextLinks.length > 1) throw new Error("Journal pagination is ambiguous");
    return nextLinks.length
      ? checkedUrl(nextLinks[0].getAttribute("href"), /^\/irc\/index\/conclusions-school$/, true) : null;
  }

  async function processJournal(state) {
    if (location.pathname !== JOURNAL) throw new Error("Open the conclusions journal to start");
    await waitFor("table.zebra-stripe.list");
    const matches = [];
    const visited = new Set();
    let url = new URL(location.href);
    let doc = document;
    for (let count = 0; count < 100; count++) {
      if (visited.has(url.href)) throw new Error("Journal pagination loops");
      visited.add(url.href);
      const next = journalPage(doc, state.job, matches);
      if (!next) break;
      if (count === 99) throw new Error("Journal exceeds 100 pages");
      const response = await fetch(next.href, { credentials: "include", cache: "no-store" });
      if (!response.ok || new URL(response.url).origin !== SITE) {
        throw new Error("Could not read the next journal page");
      }
      doc = new DOMParser().parseFromString(await response.text(), "text/html");
      url = next;
    }
    if (matches.length !== 1) throw new Error("Expected exactly one child match in the journal");
    state.conclusionUrl = matches[0].href;
    state.stage = "ipr";
    await save(state);
    await report(state, "progress", "Exact child found in the journal");
    location.assign(state.conclusionUrl);
  }

  async function processIpr(state) {
    if (location.href !== state.conclusionUrl) throw new Error("Opened IPR page does not match the journal link");
    await waitFor("table.zebra-stripe.list");
    const identity = [...document.querySelectorAll("table.zebra-stripe.list tr")]
      .find(row => row.cells.length >= 2 && normalize(row.cells[0].textContent) === "Прізвище, ім'я, по батькові дитини");
    if (!identity || !fullNameMatches(identity.cells[1].textContent, state.job.child)) {
      throw new Error("IPR page child identity does not match");
    }
    const top = [...document.querySelectorAll("a.add-link.with-icon[href^='/irc/index/filling-ipr/conclusion_id/']")];
    const plus = [...document.querySelectorAll(
      "table.zebra-stripe.list tr td:nth-child(5) a.with-icon[href^='/irc/index/filling-ipr/ipr_id/']"
    )].filter(link => link.querySelector("img[src$='/add.png']"));
    const actions = [...top, ...plus].filter(link => link.getClientRects().length);
    if (actions.length !== 1) throw new Error("Expected exactly one create IPR action");
    const conclusionId = new URL(state.conclusionUrl).pathname.split("/").pop();
    const route = top.includes(actions[0])
      ? new RegExp(`^/irc/index/filling-ipr/conclusion_id/${conclusionId}$`)
      : new RegExp(`^/irc/index/filling-ipr/ipr_id/\\d+/conclusion_id/${conclusionId}$`);
    state.formUrl = checkedUrl(actions[0].getAttribute("href"), route).href;
    state.stage = "form";
    await save(state);
    await report(state, "progress", "Matching IPR page confirmed");
    location.assign(state.formUrl);
  }

  async function processForm(state) {
    if (location.href !== state.formUrl) throw new Error("Opened IPR form has a different address");
    const form = await waitFor("form#iprForm");
    const heading = document.querySelector("#content-wrapper .nosidebar > h1");
    if (!heading || normalize(heading.textContent) !==
      "Створення індивідуальної програми розвитку учня закладу загальної середньої освіти") {
      throw new Error("Opened form heading does not match");
    }
    const names = [...form.querySelectorAll("p")].map(p => normalize(p.textContent))
      .map(text => text.match(/^прізвище,\s*власне ім[’ʼ']я,\s*по батькові\s*\(за наявності\)\s+(.+)$/i))
      .filter(Boolean);
    if (names.length !== 1 || !fullNameMatches(names[0][1], state.job.child)) {
      throw new Error("IPR form child identity does not match");
    }
    const expected = new Set(["execution_period", "year_of_study", "child_grade", "parents_phones"]);
    if (state.job.fields.length !== 4 || state.job.fields.some(field => !expected.delete(field.name)) || expected.size) {
      throw new Error("App supplied an unexpected field mapping");
    }
    for (const field of state.job.fields) {
      const controls = form.querySelectorAll(`[name="${field.name}"]`);
      if (controls.length !== 1 || controls[0].disabled) throw new Error("A mapped form field is missing");
      const control = controls[0];
      if (field.name === "year_of_study") {
        if (control.tagName !== "SELECT" || ![...control.options].some(option => option.value === field.value)) {
          throw new Error("Year of study is unavailable in the form");
        }
      } else if (control.tagName !== "INPUT" || control.type !== "text") {
        throw new Error("A mapped form field changed type");
      }
      control.value = field.value;
      control.dispatchEvent(new Event("input", { bubbles: true }));
      control.dispatchEvent(new Event("change", { bubbles: true }));
      if (control.value !== field.value) throw new Error("A mapped form field did not retain its value");
    }
    await clear();
    await report(state, "ready", "Four fields filled and read back; review remaining sections manually");
  }

  async function run() {
    let state;
    try {
      state = (await chrome.runtime.sendMessage({ type: "getState" }))?.state || null;
      if (state) {
        const alive = await chrome.runtime.sendMessage({ type: "alive", id: state.job.id });
        if (!alive?.active) { await clear(); state = null; }
      }
      if (!state) {
        if (location.pathname !== JOURNAL || !document.querySelector("table.zebra-stripe.list")) return;
        const claimed = await chrome.runtime.sendMessage({ type: "claim" });
        if (!claimed?.job) return;
        state = { job: claimed.job, stage: "journal" };
        await save(state);
      }
      if (state.stage === "journal") await processJournal(state);
      else if (state.stage === "ipr") await processIpr(state);
      else if (state.stage === "form") await processForm(state);
      else throw new Error("Unknown automation stage");
    } catch (error) {
      await clear();
      if (state?.job?.id) {
        await chrome.runtime.sendMessage({
          type: "status", id: state.job.id, status: "error", detail: error.message || "Portal automation stopped",
        }).catch(() => {});
      }
    }
  }

  run();
})();
