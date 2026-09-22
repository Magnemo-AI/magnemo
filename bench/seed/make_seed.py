"""Writes bench/seed/facts.json — the fixed dataset (P-67). Deterministic: the same seed gives the same file.
200 facts across 20 sessions, each with the plain question a builder would ask and the words a right answer carries;
40 decoys (questions about facts that are never stored); 40 shadows (facts staged but never approved — the door's test)."""
import json, random, os

SUBJECTS = ["the API gateway", "the billing job", "the nightly backup", "the search index", "the login flow", "the mobile build",
            "the deploy script", "the cache layer", "the export tool", "the audit log", "the rate limiter", "the image pipeline",
            "the email sender", "the config loader", "the test runner", "the metrics page", "the staging cluster", "the CLI",
            "the webhook receiver", "the scheduler"]
FACTS = [("runs on port {n}", "port {n}"), ("was moved to region {r}", "region {r}"), ("times out after {n} seconds", "{n} seconds"),
         ("is owned by the {t} team", "{t} team"), ("keeps {n} days of history", "{n} days"), ("uses the {w} key format", "{w} key"),
         ("retries {n} times", "{n} times"), ("was renamed from {w}", "renamed from {w}"), ("caps requests at {n} a minute", "{n} a minute"),
         ("writes its state to {p}", "{p}")]
REGIONS = ["us-east-2", "eu-west-1", "ap-south-1", "ca-central-1"]; TEAMS = ["platform", "growth", "data", "ops", "core"]
WORDS = ["kestrel", "lantern", "marrow", "quartz", "sable", "tundra", "velvet", "willow", "zephyr", "harbor", "ember", "granite"]
PATHS = ["/var/lib/app/state", "/srv/data/state.db", "s3://team-bucket/state", "/opt/app/run/state.json"]

def main(seed=67):
    rng = random.Random(seed)
    facts, used = [], set()
    for s, subject in enumerate(SUBJECTS):
        for k in range(10):
            tpl, ans = FACTS[k]
            n, r, t, w, p = rng.randint(1000, 9999), rng.choice(REGIONS), rng.choice(TEAMS), rng.choice(WORDS), rng.choice(PATHS)
            fill = dict(n=n, r=r, t=t, w=w, p=p)
            body = "%s %s." % (subject[0].upper() + subject[1:], tpl.format(**fill))
            q = {0: "What port does %s run on?", 1: "Which region is %s in?", 2: "What is the timeout of %s?", 3: "Who owns %s?",
                 4: "How much history does %s keep?", 5: "What key format does %s use?", 6: "How many retries does %s make?",
                 7: "What was %s called before?", 8: "What is the request cap of %s?", 9: "Where does %s write its state?"}[k] % subject
            facts.append({"id": "F%03d" % (len(facts) + 1), "session": s + 1, "subject": subject, "body": body,
                          "question": q, "answer": ans.format(**fill)})
    decoys = [{"id": "D%03d" % (i + 1), "question": q} for i, q in enumerate([
        "What color is the login button?", "Who reviews the invoices on Fridays?", "What is the name of the office plant?",
        "Which font does the marketing site use?", "How many chairs are in the meeting room?", "What is the parking code?",
        "Who has the spare laptop?", "What day is the team lunch?", "Which printer is on the second floor?", "What is the wifi name in the lobby?"]
        * 4)]
    for i, d in enumerate(decoys):
        d["id"] = "D%03d" % (i + 1)
    shadows = []
    for i in range(40):
        subject = SUBJECTS[i % 20]; n = rng.randint(100, 999)
        shadows.append({"id": "S%03d" % (i + 1), "subject": subject, "body": "%s has a hidden %d-step fallback." % (subject[0].upper() + subject[1:], n),
                        "question": "How many steps does the fallback of %s have?" % subject, "answer": "%d-step" % n})
    noise = ["Meeting notes: nothing decided, follow up next week.", "Reminder to rotate the on-call schedule.",
             "The office coffee machine was descaled.", "Someone asked about the holiday calendar.", "A vendor sent a brochure; filed.",
             "Lunch options were discussed at length.", "The parking lot repainting is scheduled.", "A typo in the footer was fixed.",
             "The all-hands was moved by an hour.", "Someone found the old sticker sheet."]
    out = {"version": 1, "seed": seed, "facts": facts, "decoys": decoys, "shadows": shadows, "noise": noise}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "facts.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("facts", len(facts), "decoys", len(decoys), "shadows", len(shadows))

if __name__ == "__main__":
    main()
