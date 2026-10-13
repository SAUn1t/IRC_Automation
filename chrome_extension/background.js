const BRIDGE = "http://127.0.0.1:38417";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const allowed = ["claim", "alive", "status", "getState", "setState", "clearState"];
  if (sender.id !== chrome.runtime.id || !allowed.includes(message.type)) {
    return false;
  }
  (async () => {
    if (message.type === "getState") {
      const stored = await chrome.storage.session.get("jobState");
      return { state: stored.jobState || null };
    }
    if (message.type === "setState") {
      const state = message.state;
      if (!state?.job?.id || !["journal", "ipr", "form"].includes(state.stage)) {
        return { error: "Invalid extension job state" };
      }
      await chrome.storage.session.set({ jobState: state });
      return { ok: true };
    }
    if (message.type === "clearState") {
      await chrome.storage.session.remove("jobState");
      return { ok: true };
    }
    const { token } = await chrome.storage.local.get("token");
    if (!token) return { error: "Extension is not paired" };
    const headers = { Authorization: `Bearer ${token}` };
    let path = "/job";
    let options = { headers, cache: "no-store" };
    if (message.type === "alive") {
      path = `/alive?id=${encodeURIComponent(message.id)}`;
    } else if (message.type === "status") {
      path = "/status";
      options = {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ id: message.id, type: message.status, detail: message.detail || "" }),
      };
    }
    const response = await fetch(BRIDGE + path, options);
    if (!response.ok) return { error: `Local app returned ${response.status}` };
    return await response.json();
  })().then(sendResponse).catch(() => sendResponse({ error: "Local app is not connected" }));
  return true;
});
