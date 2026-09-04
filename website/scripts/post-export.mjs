import { copyFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * GitHub Pages extras after `next build` (`output: "export"`).
 * Relative `zh-CN/` works with or without `basePath`.
 */
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "out");

writeFileSync(join(out, ".nojekyll"), "");
copyFileSync(join(out, "api/search"), join(out, "search-index.json"));

writeFileSync(
  join(out, "index.html"),
  `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content="0; url=zh-CN/" />
    <link rel="canonical" href="zh-CN/" />
    <title>ageval</title>
    <script>
      location.replace("zh-CN/" + location.search + location.hash);
    </script>
  </head>
  <body>
    <p><a href="zh-CN/">ageval</a></p>
  </body>
</html>
`,
);
