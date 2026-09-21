#!/usr/bin/env python3
"""jev_workflow_review.py — plough workflow DESIGN docs through Jev.

Where jev_human_review.py rates UI strings, this rates the process itself:
every designed move and every message template, judged from the RECIPIENT's
persona perspective (the role that will actually receive/perform it).

Questions per item (one batched call each, ~$0.00002):
  - clear:      would the recipient understand exactly what is expected/asked?
  - promise_ok: is any time/behaviour promise believable from a small agency
                (not overpromising what the system can enforce)?
  - burden:     score 0-2 how much extra work this move creates for the
                recipient (2 = heavy/new admin, 0 = free)
  - safe:       noul — could following this instruction endanger a person,
                money, or a legal duty? (gas, entry, money, tenancy law)

Extracts from the markdown:
  1. Message templates: quoted/inline-code strings inside "## Message templates"
     sections or lines starting "MSG:" (design docs follow role-workflow-design
     skeleton; anything shaped like a sentence in backticks under that heading
     counts).
  2. Moves: table rows or bullet lines under "## Action matrix" that contain a
     verb-ish move name + states.

Usage: python3 jev_workflow_review.py workflows/agent-dashboard.md [more.md...]
       [--out report.md] [--jsonl rows.jsonl] [--workers 4]
Exit: prints summary; report lists worst-scoring moves/messages per doc.
"""
import argparse, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev_human_review as H  # reuse call_jev / rate plumbing

RECIPIENTS = {
    "agent": "the solo estate agent conducting everything on their desk",
    "tenant": "a stressed working-parent tenant reading on a phone",
    "landlord": "a busy landlord who checks the portal twice a month",
    "trades": "a one-man-band tradesperson in a van, allergic to admin",
}

def recipient_for(doc, line):
    l = line.lower()
    for who in RECIPIENTS:
        if f"to {who}" in l or f"{who} receives" in l or f"(notify {who})" in l:
            return who
    m = re.search(r"(agent|tenant|landlord|trades)", os.path.basename(doc), re.I)
    return m.group(1).lower() if m else "agent"

def questions(recipient):
    who = RECIPIENTS.get(recipient, RECIPIENTS["agent"])
    return {
        "clear": {"type": "score",
            "instructions": f"The recipient is {who}. After reading this, do they know exactly what it means and what (if anything) they must do next?",
            "criteria": ["confusing", "awkward", "clear"]},
        "promise_ok": {"type": "noul",
            "instructions": "If this text makes any promise about time, money, refunds or behaviour: could a two-person agency plus software keep it EVERY time as stated, fairly to the reader? Answer NO for overpromises, hidden obligations, or anything a human must remember to do. If it makes no promise, answer YES."},
        "burden": {"type": "score",
            "instructions": f"How much NEW recurring work does this create for {who} (learning, clicking, deciding, chasing)?",
            "criteria": ["free", "manageable", "heavy"]},
        "risky": {"type": "choice",
            "instructions": "This text comes from a property-repair workflow where safety subjects are ordinary. Classify how this step handles a potential live emergency (gas leak, no heat with a vulnerable person, break-in):",
            "criteria": {
                "covered": "an emergency path exists in or alongside this step (human notified, call-first instruction, or agent decides)",
                "not-safety": "money/admin/normal repairs — no emergency dimension at all",
                "HOLE": "if an emergency arrived and followed ONLY this step, no human would know — genuine gap",
            }},
    }

def review_item(text, recipient, kind, doc, ctx=""):
    state = f"{who_line(recipient)} Context: {ctx[:160]}. {kind.capitalize()}: \"{text[:500]}\""
    a = H.call_jev(state, questions(recipient)).get("answers", {})
    return {"doc": doc, "kind": kind, "recipient": recipient, "text": text[:220],
            "clear": (a.get("clear") or {}).get("score"),
            "promise_ok": (a.get("promise_ok") or {}).get("noul"),
            "burden": (a.get("burden") or {}).get("score"),
            "risky": (a.get("risky") or {}).get("choice")}

def who_line(r): return f"Reader persona: {RECIPIENTS.get(r, r)}."

def extract(path):
    s = open(path).read()
    doc = os.path.basename(path)
    items = []
    # message templates: backticked or quoted sentences under a Message-templates heading
    m = re.search(r"^#{2,}[^\n]*[Mm]essage templates[^\n]*\n(.*?)(?=^#{2,} |\Z)", s, re.M | re.S)
    if m:
        for t in re.findall(r"[\"`]([^\"`\n]{25,})[\"`]", m.group(1)):
            items.append(("message", t, "message template"))
        for t in re.findall(r"MSG:\s*(.+)$", m.group(1), re.M):
            items.append(("message", t.strip(), "message template"))
    # action matrix rows: markdown table lines with >=3 cells
    m2 = re.search(r"^#{2,}[^\n]*[Aa]ction matrix[^\n]*\n(.*?)(?=^#{2,} |\Z)", s, re.M | re.S)
    if m2:
        for row in re.findall(r"^\|(.+)\|$", m2.group(1), re.M):
            cells = [c.strip() for c in row.split("|") if c.strip()]
            if len(cells) >= 3 and not all(re.fullmatch(r"[-: ]+", c) for c in cells):
                move = " / ".join(cells[:3])
                if not re.search(r"^(object|state|move|---)", move, re.I):
                    items.append(("move", move, "designed workflow move"))
    # keep only human-voice sentence-looking strings
    def humanish(t):
        t = t.strip()
        if not (40 <= len(t) <= 600): return False
        if not re.match(r"^[A-Z“\'{]|^(Welcome|Thanks|Good news|Logged|All settled|Quote|The office|On second|Before|Deposits|Your report)", t): return False
        if re.search(r"^(=|\+|,|;|\)|\[)|payload|regex|jargon:|voice rules", t): return False
        letters = sum(c.isalpha() for c in t)
        return letters / max(len(t), 1) > 0.55
    items = [(k, t, c) for (k, t, c) in items if k == "move" or humanish(t)]
    # dedupe
    seen, out = set(), []
    for k, t, ctx in items:
        if t[:80].lower() not in seen:
            seen.add(t[:80].lower()); out.append((k, t, ctx))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="+")
    ap.add_argument("--out", default="jev-workflow-review.md")
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    import concurrent.futures as cf
    jobs = []
    for d in args.docs:
        for kind, text, ctx in extract(d):
            jobs.append((kind, text, ctx, d))
    print(f"reviewing {len(jobs)} designed moves/messages through Jev...", file=sys.stderr)
    rows = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(review_item, t, recipient_for(d, t), k, os.path.basename(d), c): (k, d) for k, t, c, d in jobs}
        for f in cf.as_completed(futs):
            try: rows.append(f.result())
            except Exception as e: print("row failed:", e, file=sys.stderr)

    if args.jsonl:
        with open(args.jsonl, "w") as fh:
            for r in rows: fh.write(json.dumps(r) + "\n")

    def bad(r):
        s = 0.0
        if r["clear"] is not None: s += (2 - r["clear"])
        if r["promise_ok"] is False: s += 1.5
        if r["burden"] is not None and r["burden"] >= 2: s += 1.0
        if r["risky"] == "HOLE": s += 2.0
        return s
    rows.sort(key=bad, reverse=True)
    lines = ["# Jev workflow-design review", "",
             f"_ran {time.strftime('%Y-%m-%d %H:%M')} · {len(rows)} items · recipients judged in-persona_", ""]
    for doc in sorted({r["doc"] for r in rows}):
        dr = [r for r in rows if r["doc"] == doc]
        cl = [r["clear"] for r in dr if r["clear"] is not None]
        lines += [f"## {doc}", f"- clarity avg {sum(cl)/max(len(cl),1):.2f}/2 · "
                  f"{sum(1 for r in dr if r['promise_ok'] is False)} unkeepable-promise items · "
                  f"{sum(1 for r in dr if r['risky'] == 'HOLE')} safety holes · "
                  f"{sum(1 for r in dr if r['risky'] == 'covered')} emergency-covered", ""]
        for r in dr[:12]:
            if bad(r) < 0.8: continue
            flags = []
            if r["clear"] is not None and r["clear"] < 1.4: flags.append(f"clear {r['clear']:.2f}")
            if r["promise_ok"] is False: flags.append("PROMISE RISK")
            if r["risky"] == "HOLE": flags.append("SAFETY HOLE")
            if r["burden"] is not None and r["burden"] >= 2: flags.append("HEAVY for recipient")
            lines.append(f"- [{r['kind']}→{r['recipient']}] \"{r['text'][:90]}\" — {', '.join(flags)}")
        lines.append("")
    open(args.out, "w").write("\n".join(lines) + "\n")
    print(f"report -> {args.out}")

if __name__ == "__main__":
    main()
