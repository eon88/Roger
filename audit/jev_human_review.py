#!/usr/bin/env python3
"""jev_human_review.py — plough every human-visible string and every stored
judgement of a portal through Jev (TypeSafe System One) and rate it from a
human reader's perspective.

Design rule: Jev JUDGES, it never writes. Every question is typed
(score / choice / noul). Prose suggestions come from the operator who reads
the report this script emits.

Usage:
  python3 jev_human_review.py --dir /path/with/html --stage stage.json \
      --out report.md [--jsonl rows.jsonl] [--limit 40] [--workers 4]

Outputs:
  - markdown report: per-surface clarity averages, the strings rated worst,
    and a "triage calibration" section comparing re-judged urgency against
    what the portal stored (stub-era rows should disagree loudly).
  - JSONL with every rated row for diffing between runs.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://openrouter.ai/api/v1/systemone"
MODEL = "typesafe/jev-1.13"
ENV_FILE = os.environ.get("HERMES_ENV_FILE", "/opt/data/.env")

# ---------- Jev plumbing (stdlib-only, mirrors the portal's jev_client) ----------
def _load_env():
    try:
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass

def _key():
    _load_env()
    for var in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY"):
        v = os.environ.get(var, "").strip()
        if v and not (v.startswith("${") and v.endswith("}")):
            return v
    sys.exit("no OPENROUTER_API_KEY in environment or " + ENV_FILE)

def call_jev(state, questions, retries=3):
    body = json.dumps({"state": state, "model": MODEL, "questions": questions}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1)); continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1)); continue
            raise
    return {}

# ---------- extraction ----------
AUDIENCES = {
    "tenant": "a stressed tenant parent reading on a phone — no jargon tolerance",
    "landlord": "a busy landlord investor who only checks the portal twice a month",
    "trades": "a one-man gas engineer in a van between jobs, sunlit phone screen",
    "agent": "the solo estate agent running thirty properties alone",
    "public": "a stranger who has never heard of this agency",
    "signin": "a first-time visitor trying to find their portal",
}
FILE_AUDIENCE = {
    "tenant.html": "tenant", "landlord.html": "landlord", "trades.html": "trades",
    "agent.html": "agent", "index.html": "public", "signin.html": "signin",
    "register-landlord.html": "public", "register-trades.html": "public",
}

def extract_strings(html):
    """Human-visible text nodes + button/label/placeholder text, each with the
    nearest preceding heading as context — isolated words are not judgeable."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    heads = [(m.start(), re.sub(r"\s+", " ", m.group(2)).strip())
             for m in re.finditer(r"<(h[1-3]|legend|label|caption)[^>]*>([^<]{2,80})", html)]
    def ctx_for(pos):
        c = [h for h in heads if h[0] < pos]
        return c[-1][1] if c else "(page top)"
    found = []
    for m in re.finditer(r"(?:placeholder|title)=\"([^\"]{4,160})\"", html, flags=re.I):
        found.append((m.start(), m.group(1)))
    for m in re.finditer(r">([^<>]{4,160})<", html):
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        if not t or re.fullmatch(r"[/\.\-\s\d]+", t):
            continue
        if re.search(r"^\{|\}|=>|function|window\.|const |var ", t):  # leaked JS
            continue
        found.append((m.start(), t))
    seen, out = set(), []
    for pos, s in found:
        k = s.lower()
        if k not in seen:
            seen.add(k); out.append((s, ctx_for(pos)))
    return out

def load_cases(stage_path):
    d = json.load(open(stage_path))
    return d.get("cases", []), d.get("authority", {})

# ---------- the judgments ----------
def string_questions(audience):
    who = AUDIENCES[audience]
    return {
        "understand": {"type": "score",
            "instructions": f"A reader is {who}, seeing this label/line in the stated context of the page. Do they immediately know what it is and what it does for them?",
            "criteria": ["confusing", "awkward", "clear"]},
        "warmth": {"type": "noul",
            "instructions": "In that context, does it sound like it came from a capable, considerate human rather than a machine or a lawyer?"},
        "misleads": {"type": "noul",
            "instructions": "In that context, is there a SPECIFIC likely misreading that would make the reader take a wrong action, skip a safety step, or misunderstand money owed? Judge only concrete harm, not vagueness."},
    }

def case_questions(audience):
    who = AUDIENCES[audience]
    return {
        "gut_urgency": {"type": "score",
            "instructions": "You are {who}. Read this raw message as it first arrives. How fast does it need action?".replace("{who}", who),
            "criteria": ["routine", "soon", "emergency"]},
        "clarity_for_reader": {"type": "score",
            "instructions": f"Can {who} tell from this message alone what will happen next?",
            "criteria": ["confusing", "awkward", "clear"]},
        "vulnerable": {"type": "noul",
            "instructions": "Is there a hint of a vulnerable person (child, elderly, ill, disabled) or a legal/safety duty in play?"},
    }

def rate_string(s, ctx, audience):
    who = AUDIENCES[audience]
    a = call_jev(f"Portal surface: {audience}. The reader is {who}. Location on page: \"{ctx}\". Text being reviewed: \"{s}\"",
                 string_questions(audience)).get("answers", {})
    return {"kind": "string", "surface": audience, "text": s, "context": ctx,
            "understand": (a.get("understand") or {}).get("score"),
            "warmth": (a.get("warmth") or {}).get("noul"),
            "misleads": (a.get("misleads") or {}).get("noul")}

def rate_case(c):
    audience = "agent" if c.get("type") == "agent_task" else ("tenant" if c.get("role") == "tenant" else "agent")
    a = call_jev((c.get("message") or "")[:1200], case_questions(audience)).get("answers", {})
    stored = (c.get("triage") or {}).get("urgency")
    rej = a.get("gut_urgency") or {}
    return {"kind": "case", "surface": "cases", "id": c.get("id"),
            "text": (c.get("message") or "")[:120],
            "engine": (c.get("triage") or {}).get("engine", "none"),
            "stored_urgency": stored, "jev_rejudged": rej.get("score"),
            "clarity": rej and (a.get("clarity_for_reader") or {}).get("score"),
            "vulnerable": (a.get("vulnerable") or {}).get("noul")}

# ---------- report ----------
def fmt_pct(v): return f"{round(v*100)}%" if v is not None else "?"
def worst(rows):
    def score(r):
        s = 0
        if r["understand"] is not None:
            s += (2 - r["understand"]) * 2          # confusing weighs double
        if r["misleads"]: s += 2.5
        if r["warmth"] is not None and r["warmth"] < 0.35: s += 0.75
        return s, r
    items = [(score(r)[0], r) for r in rows if r["understand"] is not None]
    items.sort(key=lambda x: -x[0])
    return items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="folder with the *.html surfaces")
    ap.add_argument("--stage", required=True, help="path to stage.json")
    ap.add_argument("--out", default="jev-human-review.md")
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--limit", type=int, default=60, help="max strings per surface")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    jobs, rows = [], []
    for fn, aud in FILE_AUDIENCE.items():
        p = os.path.join(args.dir, fn)
        if not os.path.exists(p):
            continue
        for s, ctx in extract_strings(open(p, encoding="utf-8", errors="replace").read())[:args.limit]:
            jobs.append((rate_string, (s, ctx, aud)))
    cases, _ = load_cases(args.stage)
    for c in cases:
        if c.get("message"):
            jobs.append((rate_case, (c,)))

    print(f"ploughing {len(jobs)} items through Jev…", file=sys.stderr)
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(fn, *a) for fn, a in jobs]
        for i, f in enumerate(cf.as_completed(futs)):
            try:
                rows.append(f.result())
            except Exception as e:
                print(f"  row {i} failed: {e}", file=sys.stderr)
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(jobs)}", file=sys.stderr)

    if args.jsonl:
        with open(args.jsonl, "w") as fh:
            for r in rows: fh.write(json.dumps(r) + "\n")

    strings = [r for r in rows if r["kind"] == "string"]
    case_rows = [r for r in rows if r["kind"] == "case"]
    lines = ["# Jev human-perspective review", "",
             f"_ran {time.strftime('%Y-%m-%d %H:%M')} · {len(strings)} strings · {len(case_rows)} cases · model {MODEL}_", ""]
    # surface averages
    lines += ["## Clarity by surface (0=confusing, 2=clear)", ""]
    for aud in AUDIENCES:
        ss = [r["understand"] for r in strings if r["surface"] == aud and r["understand"] is not None]
        if ss:
            lines.append(f"- **{aud}**: avg {sum(ss)/len(ss):.2f} · {len(ss)} strings · "
                         f"{sum(1 for r in strings if r['surface']==aud and r['misleads'])} possibly misleading")
    lines += ["", "## Worst-rated strings (fix these first)", ""]
    for s, r in worst(strings)[:25]:
        lines.append(f"- **[{r['surface']}]** \"{r['text']}\" (in: *{r.get('context','')}*) — understand {r['understand']}/2 · "
                     f"misleads {'YES' if r['misleads'] else 'no'} · warmth {fmt_pct(r['warmth'])}")
    lines += ["", "## Triage calibration — Jev re-judging what the portal already stored", "",
              "| case | stored | engine | Jev now | agree | vulnerable |", "|--|--|--|--|--|--|"]
    agree = tot = 0
    for r in sorted(case_rows, key=lambda x: str(x.get("id"))):
        st, rv = r.get("stored_urgency"), r.get("jev_rejudged")
        if st is not None and rv is not None:
            ok = abs(rv - st) < 1
            agree += ok; tot += 1
            lines.append(f"| {r['id']} | {st} | {r['engine']} | {rv:g} | {'✓' if ok else '**✗ DRIFT**'} | {fmt_pct(r['vulnerable'])} |")
        else:
            rv_cell = f"{rv:g}" if rv is not None else "?"
            lines.append(f"| {r['id']} | {st} | {r['engine']} | {rv_cell} | – | {fmt_pct(r['vulnerable'])} |")
    if tot:
        lines += ["", f"Agreement: **{agree}/{tot}** ({round(agree/tot*100)}%). Every ✗ DRIFT is a human-facing "
                  "mis-triage to re-check; stub-engine rows are expected to drift."]
    lines += ["", "## Strings that mislead about safety or money", ""]
    for r in strings:
        if r["misleads"]:
            lines.append(f"- **[{r['surface']}]** \"{r['text']}\" (in: *{r.get('context','')}*)")
    open(args.out, "w").write("\n".join(lines) + "\n")
    print(f"report → {args.out}" + (f" · jsonl → {args.jsonl}" if args.jsonl else ""))

if __name__ == "__main__":
    main()
