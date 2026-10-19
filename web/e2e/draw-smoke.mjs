// Drive the deployed app in a headless browser: send a draw prompt, capture console errors and the reply events.
// Usage: node e2e/draw-smoke.mjs <base-url> <storage-state.json> "<prompt>"
import { chromium } from "playwright";

const [base, storage, prompt] = process.argv.slice(2);
const browser = await chromium.launch();
const context = await browser.newContext({ storageState: storage, viewport: { width: 1360, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("console", (msg) => { if (msg.type() === "error" || msg.type() === "warning") errors.push(`${msg.type()}: ${msg.text()}`); });
page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}\n${err.stack ?? ""}`));
page.on("response", async (res) => {
  if (res.url().includes("/messages") && res.request().method() === "POST") {
    console.log("POST /messages ->", res.status(), res.headers()["content-type"]);
  }
});
await page.goto(`${base}/`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "New chat" }).click();
await page.waitForURL(/\/c\//, { timeout: 15000 });
await page.getByLabel("Message").fill(prompt);
await page.getByRole("button", { name: "Send" }).click();
const started = Date.now();
while (Date.now() - started < 120000) {
  const text = await page.locator("main").innerText();
  if (/the reply failed|reply failed/i.test(text) || (await page.locator("img[alt]").count()) > 0 && !/Generating image/.test(text) && (await page.getByRole("button", { name: "Stop" }).count()) === 0) break;
  await page.waitForTimeout(1000);
}
await page.waitForTimeout(2000);
console.log("--- main text (tail) ---");
console.log((await page.locator("main").innerText()).slice(-900));
console.log("--- images rendered:", await page.locator("img[alt]").count());
console.log("--- console/page errors:", errors.length);
for (const e of errors) console.log(e.slice(0, 1200));
await page.screenshot({ path: "../.local/shots/e2e-draw.png", fullPage: false });
await browser.close();
