const input = document.getElementById("token");
const message = document.getElementById("message");
chrome.storage.local.get("token").then(({ token }) => {
  if (token) message.textContent = "Paired. Keep this extension enabled while processing.";
});
document.getElementById("save").addEventListener("click", async () => {
  const token = input.value.trim();
  if (token.length < 24) {
    message.textContent = "Paste the full pairing code from the app.";
    return;
  }
  await chrome.storage.local.set({ token });
  await chrome.runtime.sendMessage({ type: "pollNow" });
  input.value = "";
  message.textContent = "Pairing saved. Return to the desktop app and press Process.";
});
