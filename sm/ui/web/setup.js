"use strict";
(() => {
  const form = document.querySelector("#folder-form");
  const folder = document.querySelector("#folder");
  const message = document.querySelector("#message");
  const differences = document.querySelector("#differences");
  const button = form.querySelector("button[type=submit]");
  const browse = document.querySelector("#browse");
  const back = document.querySelector("#return");
  const headers = {"Content-Type": "application/json", "X-SM-Build": "__SM_BUILD_ID__"};

  async function load() {
    try {
      const response = await fetch("/intake", {cache: "no-store"});
      if (!response.ok) throw new Error("Cannot read folder settings. Reload the page to try again.");
      const state = await response.json();
      back.hidden = !state.ready;
      document.querySelector("#supported").textContent = `Supported now: ${state.expected.join(", ")}. ` +
        (state.missing.length ? `Samples missing, not yet supported: ${state.missing.map(v => v.label).join(", ")}.` : "");
      if (state.source !== "settings") {
        message.textContent = `${state.source} sets the game folder. Change or unset it, then restart the server to use folder settings.`;
        button.disabled = true;
        browse.disabled = true;
        folder.disabled = true;
      } else {
        message.textContent = state.error;
        folder.focus();
      }
    } catch (error) { message.textContent = error.message; }
  }

  browse.addEventListener("click", async () => {
    browse.disabled = button.disabled = true;
    message.textContent = "Choose your game folder in the native folder dialog, or cancel to type a path.";
    try {
      const response = await fetch("/browse", {method: "POST", headers, body: "{}"});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.message || "Reload this page and try Browse again.");
      if (!result.cancelled) folder.value = result.folder;
      message.textContent = result.cancelled ? "Cancelled. You can still type a folder path." : "Folder selected. Verify it to continue.";
    } catch (error) { message.textContent = error.message; }
    finally { browse.disabled = button.disabled = false; folder.focus(); }
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    browse.disabled = button.disabled = true;
    differences.replaceChildren();
    message.textContent = "Checking file names, sizes and SHA-256 hashes…";
    try {
      const response = await fetch("/intake", {method: "POST", headers, body: JSON.stringify({folder: folder.value})});
      const result = await response.json();
      message.textContent = result.message || "The page build changed. Reload the page and try again.";
      for (const difference of result.differences || []) {
        const item = document.createElement("li");
        const describe = value => value ? `${value.size} bytes; SHA-256 ${value.sha256}` : "missing";
        item.textContent = `${difference.name}: expected ${describe(difference.expected)}; found ${describe(difference.found)}.`;
        differences.append(item);
      }
      if (response.ok && result.ok && !result.restart) location.assign("/");
    } catch (error) {
      message.textContent = "Could not confirm the folder. Reload the page to check the saved settings. " + error.message;
    } finally { browse.disabled = button.disabled = false; }
  });
  void load();
})();
