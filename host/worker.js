/*
 * Victoria 2 campaign analyzer -- a place to put a report
 * Copyright (C) 2026 vic2tools
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU Affero General Public License as published by the
 * Free Software Foundation, either version 3 of the License, or (at your
 * option) any later version. It is distributed WITHOUT ANY WARRANTY; without
 * even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 * PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
 *
 * A Cloudflare Worker that takes a report and answers with a link.
 *
 * Nothing in the analyzer needs this to exist. It is here because the honest
 * answer to "where does the link go" is that somebody has to run a host, and
 * this is the smallest one that does the job: an upload, a page, and a way to
 * take it down again. See host/README.md before deploying it -- running this
 * means holding other people's files.
 *
 * Two things keep it from being an open HTML host, which is what it would
 * otherwise be:
 *
 *   It only accepts what the analyzer makes. A report is one known template
 *   with a compressed payload inside it, so an upload is checked against that
 *   shape -- and only in bounded slices off each end, because a Worker on the
 *   free plan gets 10 ms of CPU and a 20 MB file will not be read twice.
 *
 *   Everything it serves is sandboxed by the headers it serves them with. A
 *   report needs no network of its own: it carries its data inside it and
 *   draws its own charts. So the policy below forbids the lot -- no fetching,
 *   no external scripts, no forms, no framing -- and a page that cannot talk
 *   to anywhere cannot be used to collect anything from anybody.
 */

const MAX_BYTES = 32 * 1024 * 1024;   // a monthly century is about 20
const HEAD_BYTES = 96 * 1024;         // enough to cover the template's head
const KEEP_DAYS = 400;                // lifecycle on the bucket does the rest

// Marks every report carries, near the front and at the very end. These are
// the analyzer's own template, not a guess about HTML in general.
const WANTED_HEAD = [
  "<!DOCTYPE html>",
  "<title>Campaign returns</title>",
  "const PACKED",
];
const WANTED_TAIL = "</html>";

const POLICY = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src data: blob:",
  "connect-src 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
].join("; ");

function id(bytes = 9) {
  const raw = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...raw))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

/** Whether this is one of ours, judged on the ends alone. */
function looksLikeAReport(head, tail) {
  const text = new TextDecoder("utf-8", { fatal: false }).decode(head);
  for (const mark of WANTED_HEAD) if (!text.includes(mark)) return false;
  const end = new TextDecoder("utf-8", { fatal: false }).decode(tail);
  return end.includes(WANTED_TAIL);
}

async function upload(request, env, url) {
  const declared = Number(request.headers.get("Content-Length") || 0);
  if (declared > MAX_BYTES)
    return json({ error: `reports over ${MAX_BYTES >> 20} MB are not taken` }, 413);

  const body = new Uint8Array(await request.arrayBuffer());
  if (body.length === 0) return json({ error: "empty upload" }, 400);
  if (body.length > MAX_BYTES)
    return json({ error: `reports over ${MAX_BYTES >> 20} MB are not taken` }, 413);
  if (!looksLikeAReport(body.subarray(0, HEAD_BYTES),
                        body.subarray(Math.max(0, body.length - 4096))))
    return json({ error: "this is not a Victoria 2 campaign report" }, 400);

  const key = id();
  const secret = id(12);
  const name = (request.headers.get("X-Report-Name") || "").slice(0, 120);
  await env.REPORTS.put(`r/${key}`, body, {
    httpMetadata: { contentType: "text/html; charset=utf-8" },
    customMetadata: { name, secret, at: new Date().toISOString() },
  });

  return json({
    url: `${url.origin}/r/${key}`,
    delete: `${url.origin}/d/${key}?k=${secret}`,
    keeps_until_days: KEEP_DAYS,
  });
}

async function serve(env, key) {
  const held = await env.REPORTS.get(`r/${key}`);
  if (!held) return new Response("No report here. It may have been taken down.",
                                 { status: 404 });
  return new Response(held.body, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": POLICY,
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      // A report never changes once uploaded: a new one gets a new address.
      "Cache-Control": "public, max-age=604800, immutable",
    },
  });
}

async function remove(env, key, given) {
  const held = await env.REPORTS.head(`r/${key}`);
  if (!held) return new Response("Already gone.", { status: 404 });
  const secret = (held.customMetadata || {}).secret || "";
  // Constant-time enough for a random 96-bit string that is never guessed.
  if (!given || given !== secret)
    return new Response("That is not the right link.", { status: 403 });
  await env.REPORTS.delete(`r/${key}`);
  return new Response("Taken down.", { status: 200 });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");

    if (request.method === "POST" && path === "/upload")
      return upload(request, env, url);
    if (request.method === "GET" && path.startsWith("/r/"))
      return serve(env, path.slice(3));
    if (request.method === "GET" && path.startsWith("/d/"))
      return remove(env, path.slice(3), url.searchParams.get("k"));
    if (request.method === "GET" && (path === "" || path === "/"))
      return new Response(
        "A place to put Victoria 2 campaign reports.\n" +
        "The analyzer uploads them here; there is nothing to see at this address.\n",
        { headers: { "Content-Type": "text/plain; charset=utf-8" } });

    return new Response("Not found", { status: 404 });
  },
};
