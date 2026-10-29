// Optional browser QA: requires Playwright and its Chromium runtime.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { mkdir } = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.REPORT_CHROMIUM ? { executablePath: process.env.REPORT_CHROMIUM } : {}) });
  try {
    await mkdir("artifacts/report-qa", { recursive: true });
    for (const width of [1440, 768, 390, 320]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", message => {
        if (message.type() === "error") errors.push(message.text());
      });
      for (const run of ["concurrent", "fault"]) {
        await page.goto(pathToFileURL(path.resolve("artifacts", run, process.argv[2] || "report.html")).href);
        await page.waitForFunction(() => document.getElementById("visible-count").textContent.includes("of"));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.getByLabel("Search operations").fill("no-matching-operation");
        assert.equal(await page.locator("details.operation:visible").count(), 0);
        assert.equal(await page.locator("#empty").isVisible(), true);
        await page.getByLabel("Search operations").fill("");
        if (run === "fault") {
          await page.getByLabel("Outcome", { exact: true }).selectOption("mismatch");
          assert.equal(await page.locator("details.operation:visible").count(), 1);
          await page.locator("details.operation:visible summary").click();
          assert.equal(await page.locator("details.operation[open]:visible").count(), 1);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
          await page.getByLabel("Outcome", { exact: true }).selectOption("all");
        } else {
          await page.locator(".witness a").first().click();
          await page.locator("details.operation[open]").first().waitFor({ state: "visible" });
          assert.equal(await page.locator("details.operation[open]").count(), 1);
          await page.goto(page.url().split("#")[0]);
        }
        await page.screenshot({ path: `artifacts/report-qa/${run}-${width}.png`, fullPage: true });
      }
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log("PASS: two reports at four widths; filters, links, details, no overflow or browser errors");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
