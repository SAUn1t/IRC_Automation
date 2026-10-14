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

  function checkedUrl(href, pattern, base = location.href, allowPageQuery = false) {
    const url = new URL(href, base);
    const pageQuery = allowPageQuery && url.pathname === JOURNAL &&
      [...url.searchParams.keys()].length === 1 &&
      /^[1-9]\d*$/.test(url.searchParams.get("page") || "");
    if (url.origin !== SITE || !pattern.test(url.pathname) ||
        (url.search && !pageQuery) || url.hash) {
      throw new Error("Portal link does not match the expected route: " +
        url.pathname.replace(/\d+/g, ":n"));
    }
    return url;
  }

  function journalPageNumber(url) {
    const pathPage = url.pathname.match(/\/page\/([1-9]\d*)\/?$/);
    const number = Number(pathPage ? pathPage[1] : (url.searchParams.get("page") || "1"));
    if (!Number.isSafeInteger(number) || number < 1) throw new Error("Journal page number is invalid");
    return number;
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

  async function restartFromJournal(state) {
    const reply = await chrome.runtime.sendMessage({ type: "restartJournal", id: state.job.id });
    if (reply?.error) throw new Error("Could not continue from the conclusions journal");
    await report(state, "progress", "Open page belongs to another child; searching the journal");
  }

  async function waitFor(selector, timeout = 15000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const element = document.querySelector(selector);
      if (element) return element;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    if (document.title.includes("Just a moment") ||
        document.body?.textContent?.includes("Performing security verification")) {
      throw new Error("Cloudflare verification did not finish in this Chrome profile");
    }
    throw new Error("Expected portal content did not appear");
  }

  function journalPage(doc, pageUrl, job, matches) {
    const table = doc.querySelector("table.zebra-stripe.list");
    if (!table) throw new Error("Conclusions journal table is missing");
    for (const row of table.querySelectorAll("tr")) {
      if (row.cells.length < 8) continue;
      const nameLink = row.cells[1].querySelector("a");
      if (!nameLink) continue;
      if (fullNameMatches(nameLink.textContent, job.child)) {
        const iprLink = row.cells[7].querySelector("a[href]");
        if (!iprLink) throw new Error("Matching journal row has no IPR link");
        matches.push(checkedUrl(iprLink.getAttribute("href"),
          /^\/irc\/index\/conclusion-iprs\/conclusion_id\/\d+$/, pageUrl).href);
      }
    }
    const nextLinks = [...doc.querySelectorAll("#pagination-digg a[href]")]
      .filter(link => normalize(link.textContent).startsWith("Далі"));
    if (nextLinks.length > 1) throw new Error("Journal pagination is ambiguous");
    return nextLinks.length
      ? checkedUrl(nextLinks[0].getAttribute("href"),
        /^\/irc\/index\/conclusions-school(?:\/page\/[1-9]\d*)?\/?$/, pageUrl, true) : null;
  }

  async function processJournal(state) {
    const url = checkedUrl(location.href,
      /^\/irc\/index\/conclusions-school(?:\/page\/[1-9]\d*)?\/?$/, location.href, true);
    const pageNumber = journalPageNumber(url);
    // Starting on a later journal page must still scan earlier pages for duplicates.
    if (!state.journalVisited && pageNumber !== 1) {
      location.assign(SITE + JOURNAL);
      return;
    }
    state.journalVisited ||= [];
    state.journalMatches ||= [];
    if (pageNumber !== (state.journalNextPage || 1) || state.journalVisited.includes(pageNumber)) {
      throw new Error("Journal pagination changed or looped");
    }
    await waitFor("table.zebra-stripe.list", 60000);
    const next = journalPage(document, url.href, state.job, state.journalMatches);
    state.journalVisited.push(pageNumber);
    if (state.journalMatches.length > 1) throw new Error("Expected exactly one child match in the journal");
    if (next) {
      if (state.journalVisited.length >= 100) throw new Error("Journal exceeds 100 pages");
      const nextPage = journalPageNumber(next);
      if (nextPage !== pageNumber + 1) throw new Error("Journal pagination skipped or looped");
      state.journalNextPage = nextPage;
      await save(state);
      await report(state, "progress", `Scanning journal page ${nextPage}`);
      // A top-level Chrome navigation uses the same path as clicking “Далі”.
      location.assign(next.href);
      return;
    }
    if (state.journalMatches.length !== 1) throw new Error("Expected exactly one child match in the journal");
    state.conclusionUrl = state.journalMatches[0];
    delete state.journalMatches;
    delete state.journalVisited;
    delete state.journalNextPage;
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
    if (!identity) {
      throw new Error("IPR page child identity is missing");
    }
    if (!fullNameMatches(identity.cells[1].textContent, state.job.child)) {
      if (state.directEntry) return restartFromJournal(state);
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
    const names = [...form.querySelectorAll("p")]
      .map(element => normalize(element.textContent))
      .map(text => text.match(/^прізвище,\s*власне ім[’ʼ']я,\s*по батькові\s*\(за наявності\)\s+(.+)$/i))
      .filter(match => match && normalize(match[1]).split(" ").length === 3);
    if (names.length === 0) throw new Error("IPR form child name label was not found; no fields changed");
    if (names.length > 1) throw new Error("IPR form child name is ambiguous; no fields changed");
    if (!fullNameMatches(names[0][1], state.job.child)) {
      if (state.directEntry) return restartFromJournal(state);
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

  let running = false;
  let pendingStart = false;
  async function run() {
    if (running) { pendingStart = true; return; }
    running = true;
    let state;
    try {
      state = (await chrome.runtime.sendMessage({ type: "getState" }))?.state || null;
      if (state) {
        const alive = await chrome.runtime.sendMessage({ type: "alive", id: state.job.id });
        if (!alive?.active) { await clear(); state = null; }
      }
      if (!state) return;
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
    } finally {
      running = false;
      if (pendingStart) {
        pendingStart = false;
        run();
      }
    }
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "start") {
      run();
      sendResponse({ ok: true });
    }
  });
  run();
})();
