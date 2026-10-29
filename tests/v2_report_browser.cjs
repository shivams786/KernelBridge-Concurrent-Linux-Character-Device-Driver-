// Optional offline report acceptance check; requires Playwright and Chromium.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { mkdir } = require("node:fs/promises");
const { pathToFileURL } = require("node:url");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.REPORT_CHROMIUM ? { executablePath: process.env.REPORT_CHROMIUM } : {}) });
  try {
    await mkdir("artifacts/v2-browser", { recursive: true });
    for (const width of [1440, 768, 390, 320]) {
      for (const kind of ["fault", "control"]) {
        const page = await browser.newPage({ viewport: { width, height: 900 } });
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
        await page.goto(pathToFileURL(path.resolve(`artifacts/v2-demo-${kind}/run-00/report.html`)).href);
        await page.waitForFunction(() => document.getElementById("visible-count").textContent.includes("of"));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.getByLabel("Search operations").fill("no-matching-operation");
        assert.equal(await page.locator("details.operation:visible").count(), 0);
        await page.getByLabel("Search operations").fill("");
        if (kind === "fault") {
          await page.getByRole("heading", { name: "Repeated executable replay" }).waitFor();
          await page.getByRole("heading", { name: "Recorded history reduction" }).waitFor();
          await page.getByText("Reduction evidence", { exact: true }).click();
        } else {
          await page.locator(".witness a").first().click();
          await page.locator("details.operation[open]").first().waitFor({ state: "visible" });
        }
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        assert.deepEqual(errors, []);
        await page.screenshot({ path: `artifacts/v2-browser/${kind}-${width}.png`, fullPage: false });
        await page.close();
      }
    }
    console.log("PASS: v2 fault/control reports, four widths, filters, evidence expansion and witness navigation");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
