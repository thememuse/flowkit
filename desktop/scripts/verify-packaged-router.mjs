#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopRoot = join(__dirname, "..");

const appPath = join(desktopRoot, "src", "App.tsx");
const mainPath = join(desktopRoot, "electron", "main.ts");

function fail(message) {
  console.error(`[verify:packaged-router] ${message}`);
  process.exit(1);
}

const appSource = readFileSync(appPath, "utf-8");
const mainSource = readFileSync(mainPath, "utf-8");

if (!/\bHashRouter\b/.test(appSource)) {
  fail("App router guard failed: HashRouter not found in desktop/src/App.tsx");
}

if (/<\s*BrowserRouter\b|<\/\s*BrowserRouter\s*>/.test(appSource)) {
  fail("App router guard failed: BrowserRouter tag still present in desktop/src/App.tsx");
}

const loadFileHashRoutePattern =
  /loadFile\(\s*join\(__dirname,\s*['"]\.\.\/renderer\/index\.html['"]\)\s*,\s*\{\s*hash:\s*['"]\/['"]\s*\}\s*\)/m;

if (!loadFileHashRoutePattern.test(mainSource)) {
  fail("Main window guard failed: expected loadFile(..., { hash: '/' }) in desktop/electron/main.ts");
}

console.log("[verify:packaged-router] OK");
