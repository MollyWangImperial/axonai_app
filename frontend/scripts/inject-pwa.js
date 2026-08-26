#!/usr/bin/env node
// Post-processes dist/index.html after `expo export --platform web` to add the
// PWA tags (manifest, theme-color, iOS Add-to-Home-Screen meta, apple-touch-icon).
// Needed because app.json uses web.output "single", which does not render app/+html.tsx.
const fs = require("fs");
const path = require("path");

const file = path.join(__dirname, "..", "dist", "index.html");
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
        window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
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

fs.writeFileSync(file, html);
console.log("PWA tags injected into dist/index.html");
