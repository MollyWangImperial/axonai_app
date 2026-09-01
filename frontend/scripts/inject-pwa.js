#!/usr/bin/env node
// Post-processes dist/index.html after `expo export --platform web` to add the
// PWA tags (manifest, theme-color, iOS Add-to-Home-Screen meta, apple-touch-icon).
// Needed because app.json uses web.output "single", which does not render app/+html.tsx.
const fs = require("fs");
const path = require("path");

const file = path.join(__dirname, "..", "dist", "index.html");
const serviceWorkerFile = path.join(__dirname, "..", "dist", "sw.js");
let html = fs.readFileSync(file, "utf8");

const PWA_TAGS = `
    <link rel="manifest" href="/manifest.json" />
    <meta name="theme-color" content="#4A7856" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="Rehyn" />
    <link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png" />
    <script>
      if ("serviceWorker" in navigator) {
        let reloadingForUpdate = false;
        navigator.serviceWorker.addEventListener("controllerchange", () => {
          if (reloadingForUpdate) return;
          reloadingForUpdate = true;
          window.location.reload();
        });
        window.addEventListener("load", async () => {
          const registration = await navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
          await registration.update();
        });
      }
    </script>
`;

if (!html.includes('rel="manifest"')) {
  html = html.replace("</head>", `${PWA_TAGS}</head>`);
}
html = html.replace(
  'content="width=device-width, initial-scale=1, shrink-to-fit=no"',
  'content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover"',
);

const bundleHash = html.match(/entry-([a-f0-9]+)\.js/)?.[1];
if (!bundleHash) throw new Error("Could not identify the exported web bundle hash.");

let serviceWorker = fs.readFileSync(serviceWorkerFile, "utf8");
serviceWorker = serviceWorker.replace("rehyn-shell-__BUILD_ID__", `rehyn-shell-${bundleHash}`);
if (serviceWorker.includes("rehyn-shell-__BUILD_ID__")) {
  throw new Error("Could not stamp the service worker cache version.");
}

fs.writeFileSync(file, html);
fs.writeFileSync(serviceWorkerFile, serviceWorker);
console.log(`PWA tags injected and service worker stamped with ${bundleHash}`);
