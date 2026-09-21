# A place to put reports

The analyzer does not need this. It ships with no host set, and **Share → Show
me the file to send** is the answer for almost everybody: a report of a few
dozen saves is a couple of megabytes and goes straight into a chat window.

This is for the other case — a link, for anyone, with no account. That needs a
server, and a server needs somebody to run it. This is the smallest one that
does the job.

## What it costs

Cloudflare's free tier covers a surprising amount of it, because R2 does not
charge for bandwidth — which is normally what makes file hosting expensive,
since one 20 MB report read a hundred times is 2 GB of traffic.

| | Free tier | After that |
|---|---|---|
| Storage (R2) | 10 GB — roughly 500 full-length reports, or 1,400 smaller ones | $0.015 per GB-month |
| Bandwidth | unlimited, free | still free |
| Requests (Workers) | 100,000 a day | $5 a month |

So: nothing, until it is popular. A domain is about $10 a year, and you can
start on the `workers.dev` address without one.

## Deploying it

```
npm install -g wrangler
wrangler login
wrangler r2 bucket create vic2-reports
wrangler deploy
```

That prints an address like `https://vic2-reports.<you>.workers.dev`. Put it
in the analyzer under **Share → Upload to a report host**, and the button
becomes one click for whoever you give that build to.

To stop reports piling up forever, add a lifecycle rule on the bucket — in the
Cloudflare dashboard, R2 → your bucket → Settings → Object lifecycle rules —
deleting objects after however long you want to keep them. The Worker tells
each uploader how long that is; change `KEEP_DAYS` to match.

## What you are signing up for

You would be holding other people's files, so it is worth being plain about
what stops this becoming a problem.

**It only takes reports.** An upload is checked against the analyzer's own
template — the title, the packed-payload marker, the closing tag — so it is
not a general file host. The check reads a slice off each end rather than the
whole file, because the free plan gives a Worker 10 ms of CPU.

**Nothing it serves can reach anywhere.** Reports are served under a
Content-Security-Policy that forbids fetching, external scripts, forms and
framing. A report needs none of those: it carries its data inside itself and
draws its own charts. A page that cannot talk to anywhere cannot be used to
collect anything from anybody, which is the usual reason not to host
strangers' HTML.

**Every upload comes back with its own take-down link**, and you can delete
anything from the bucket yourself.

What none of that gives you is moderation of *content* — somebody could still
upload a genuine report of something you would rather not host. At that point
it is a bucket you control and a `wrangler r2 object delete` away.
