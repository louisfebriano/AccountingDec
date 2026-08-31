import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const app = await readFile(new URL("../../pwa/app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../../pwa/index.html", import.meta.url), "utf8");
const styles = await readFile(new URL("../../pwa/styles.css", import.meta.url), "utf8");

test("website dikunci sampai login atau register berhasil", () => {
  assert.match(html, /<body data-auth-state="loading">/);
  assert.match(html, /id="login-form"/);
  assert.match(html, /id="register-form"/);
  assert.match(html, /id="logout-button"/);
  assert.match(styles, /body:not\(\[data-auth-state="authenticated"\]\) \.app-shell/);
  assert.match(app, /initializeAuthentication\(\)/);
  assert.match(app, /document\.body\.dataset\.authState = "authenticated"/);
});

test("cache transaksi dipisahkan menurut user ID dan token tidak masuk localStorage", () => {
  assert.match(app, /setHistoryUser\(user\.id\)/);
  assert.doesNotMatch(app, /localStorage\.setItem\([^\n]*(access|refresh)[_-]?token/i);
  assert.match(app, /logoutAccount\(\)/);
});
