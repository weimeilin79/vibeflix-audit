# Vibeflix docs

The story and design of the Vibeflix licensing-audit mesh, in a few short pages. The
top-level [`README.md`](../README.md) stays lean and points here; deployment lives under
[`deploy/docs/`](../deploy/docs/).

## Pages

1. **[The Story](./01-the-story.md)** — why this system exists: what Vibeflix licenses,
   why the process is hard, where humans still have to *reason* (deal pricing), the
   "tribal knowledge" legal problem, and the enterprise-grade security bar.
2. **[Architecture](./02-architecture.md)** — the ten-service mesh: the layers, the two
   protocols (A2A + MCP), the shared task store, and what enforces the boundaries.
3. **[The `vibeflix-common` library](./03-common-lib.md)** — the shared plumbing every
   service uses: what each module does, who imports it, and the four that carry hard-won
   fixes.

## Where the rest lives

| Looking for | Go to |
|---|---|
| Security target state — who may call whom + the IAM | [`topology.md`](../topology.md) |
| Rules that fail silently in production | [`deploy/docs/GOTCHAS.md`](../deploy/docs/GOTCHAS.md) |
| Stand it up (automated) | [`deploy/docs/instruction-sre.md`](../deploy/docs/instruction-sre.md) |
| Stand it up (command by command) | [`deploy/docs/instruction-dev.md`](../deploy/docs/instruction-dev.md) |
| Preflight check before deploying | [`deploy/preflight.sh`](../deploy/preflight.sh) |
