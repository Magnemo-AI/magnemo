# Contributing to Magnemo

Magnemo is governed software — the repo runs under the same law the product
enforces: every change has provenance, every ruling has a story.

## The short version
1. Open an issue before a large change; small fixes can go straight to a PR.
2. Zero dependencies is a feature, not an accident. PRs that add a runtime
   dependency will be declined; pure Python 3.10+ stdlib only.
3. Every PR must pass the suite: `python3 -m unittest discover -s tests`.
4. Sign your work (DCO — see below).

## Developer Certificate of Origin (DCO)
We use the [Developer Certificate of Origin v1.1](https://developercertificate.org/).
Every commit must be signed off:

    git commit -s -m "your message"

The `Signed-off-by:` line certifies you have the right to submit the work
under this repository's license.

> Maintainer note: a CLA (instead of, or in addition to, DCO) is FLAGGED FOR
> COUNSEL and may be adopted before the first external release candidate.

## What we will not merge
- Changes to the gate map's keyholder-only doors (promotion, publish). The
  asymmetry IS the protocol (Register #81).
- Telemetry, phone-home, or network calls of any kind.
- Anything that writes outside the vault.

## Conduct
Be the kind of contributor you'd trust with your own memory. Disagreement is
welcome; disrespect is not.
