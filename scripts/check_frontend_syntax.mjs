import fs from "node:fs";

const files = ["static/participant.html", "static/admin-detail.html"];

for (const file of files) {
  const html = fs.readFileSync(file, "utf8");
  const start = html.indexOf("<script>");
  const end = html.lastIndexOf("</script>");
  if (start < 0 || end < start) {
    throw new Error(`Inline script not found in ${file}`);
  }
  const source = html.slice(start + "<script>".length, end);
  new Function(source);
  console.log(`${file}: inline script parsed`);
}
