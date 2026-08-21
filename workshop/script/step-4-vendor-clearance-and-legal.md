# Step 4 — Vendor Clearance + Legal

**Target runtime:** 24–28 min · **Lab section:** `Vendor Clearance + Legal`

---

## 00:00 — Cold open

[SCREEN: an email thread. A personal checklist. A wiki page that stops mid-sentence.]

Somewhere in your company there's a process.

It works. Everyone follows it. And it has never been written down in one place.

It lives in an email thread from eighteen months ago. In somebody's onboarding checklist, on their own laptop. In a Confluence page that just... stops.

[BEAT]

That's today.

We're building an agent whose job is to reconstruct a process from the wreckage. Then hand it real work — from another agent, across a network, with a human interrupting in the middle.

Three hard things at once. In order.

---

## 01:30 — The tribal-knowledge problem

Legal clearance at Vibeflix is a real process. Certification rules for apparel. Royalty tier definitions. Insurance minimums. The steps for a contract amendment.

None of it is in a database. It's prose. Scattered across documents that were never meant to be read together.

You could sit a lawyer down for a week and turn it into a decision table. Companies do that. It's expensive, it goes stale, and the moment the process changes you're doing it again.

The alternative is **retrieval**. Don't memorise the process — look it up. Every time. From the documents themselves.

Documents change, agent behaviour changes. No retraining. No re-prompting.

That's RAG. And this is the case where it genuinely earns its place.

---

## 03:00 — Build the knowledge base

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_legal_rag.sh
```

[DO: run it. Slow — several minutes.]

Four things happen. It uploads the documents. Creates a corpus with an embedding model. Imports the files. RAG Engine chunks, embeds and indexes everything behind the scenes.

**The import is the slow part.** You'll see it importing files, and it will sit there. For minutes. It's working. Let it finish.

On a brand-new project you might also see it retry on Vector Search permissions still propagating. Also expected. Enabling the API grants the service agent its role, and that grant takes a couple of minutes to land. The script waits it out.

And when it's done, it **writes the corpus id straight into your `.env`**. Nothing to copy and paste. The next `source ./env.sh` exports it, and when you deploy legal in a minute, it travels with the agent.

---

## 05:30 — Ask the corpus directly

Before we build anything on top of this — let's ask it a question. No agent. No model. Just the RAG API.

[DO: run the retrieveContexts curl.]

[SCREEN: three excerpts, with sources and scores.]

Look at what came back. Three excerpts. From **three different documents.**

An email thread. Somebody's onboarding checklist. A wiki page.

[BEAT]

There it is. The tribal-knowledge problem, in one result.

The answer to one simple question — what certifications does apparel need — is spread across three artefacts. None of them authoritative. None of them complete.

One thing that trips people up: **lower score means closer match** here.

And one thing that isn't a failure. If `contexts` comes back empty right after the import, indexing hasn't caught up. Wait a minute. Run it again.

It's the one case where "nothing found" doesn't mean something is wrong.

---

## 07:30 — The trap inside the retrieval tool

[SCREEN: `agents/legal/legal_kb.py`.]

The agent gets one tool for this. It has two backends.

If the corpus is configured, it queries Vertex RAG Engine. If it isn't — or Vertex is unreachable — it falls back to a local keyword search over the same files. So the agent still runs offline.

[DO: run the Python heredoc that calls the tool directly.]

[SCREEN: `retriever: vertex_rag` and three hits.]

Now. **Watch the `retriever` field.** This is the whole reason we're running this by hand.

[BEAT]

That fallback is deliberate. The agent shouldn't die because RAG is down.

But here's what it means. **A broken corpus doesn't look broken.**

The agent keeps answering. It just answers from keyword matches instead of real retrieval.

Run the same command with the corpus unset and watch. `retriever: local_keyword`. And the top hit for a certifications question becomes a document about customs codes.

Plausible. Confident. Wrong. And no error anywhere.

So when legal's answers seem subtly off — check that field first. `vertex_rag` means the corpus is being used. `local_keyword` means it isn't.

General lesson: **a fallback that's silent is a fallback that will fool you.** Build one, and make its state visible.

---

## 10:30 — A2A

Second thing. Vendor clearance needs legal to do something. Legal is a separate agent, in its own engine, with its own identity.

So how does one agent call another?

**A2A.** A small HTTP contract every ADK agent speaks. Each agent publishes an **agent card** at a known URL — what it is, how to reach it. You POST a message to it, get back a **task id**. Then you poll that task until it's done.

The *task* is the unit of work. Remember that. It matters enormously in Step 5.

In ADK, you construct a remote agent with the target's card, and from then on you invoke it like a local sub-agent. The HTTP is handled for you.

[BEAT]

**Treat an agent in another engine as a step you can call.** That's the mental model.

---

## 12:30 — Two things this mesh had to add

Thirty seconds, because these cost a day each if nobody tells you.

**The agent card names the wrong host.** Agent Runtime hardcodes the plain host into the card each engine serves. But the gateway in Step 7 only authorises the mTLS host, and refuses the plain one. Every standard A2A client just follows the card. So you have to build the card yourself.

**The stock client sends blocking, not send-and-poll.** A2A is a send-then-poll protocol — but the stock client holds one long request open. Agent Runtime kills that at around 180 seconds. While the callee is still working perfectly well.

Fast hops never notice. A long one fails, confusingly.

Both are hidden inside a subclass, so every call site stays ordinary ADK. Now you know why it exists.

---

## 14:30 — Deploy both, and the collect in the middle

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py legal
python deploy/collect_agent_identities.py
python deploy/deploy_agents_a2a.py vendor_clearance
python deploy/collect_agent_identities.py
```

Look at that order. There's a `collect` **in between**. That one is load-bearing.

Vendor clearance calls legal. So it has to deploy knowing legal's A2A URL. That URL contains legal's engine id. Which doesn't exist until legal is deployed. The deploy script reads it from the identities file — and only `collect` writes that file.

Deploy both back to back and vendor clearance looks up a URL that isn't recorded yet. It'll skip, and say so.

[BEAT]

**Why can't this one be computed away?**

In Step 6 you'll meet the mirror image — the app's URL, which the engines need. And that one turns out to be *derivable* from your project number. No second pass needed.

Engine ids aren't. Agent Runtime mints a random one. The only way to learn legal's address is to deploy it and read it back.

Deploy. Collect. Then deploy the agent that calls it.

[DO: start the deploys. Two agents — longest wait in the workshop. Jump cut.]

Then grant each its own access.

---

## 17:00 — Talk to legal alone first

Before we watch the handoff — let's talk to legal **directly**.

Worth doing separately. In the handoff, legal answers from inside another agent's workflow. So if retrieval came back empty, you'd see a vague vendor-clearance result instead of the real cause.

[DO: mesh tab, then Dev UI on agents/legal.]

Two questions. In this order. They're a **matched pair** — and the second one is *supposed* to come up empty.

**One. Something only the scattered documents know.**

> What does "annual-volume band" mean, and what are the options?

[SCREEN: an answer, with the royalty tiers.]

Watch the trace. It calls the search tool. And the answer is assembled from documents that never state it in one place.

**Two. Something the documents don't contain.**

> Are there style guidelines for grogu, and any exclusivity in North America?

[SCREEN: "I could not find any information regarding..."]

---

## 20:00 — Why the second one has no answer

Nothing is broken.

Those two facts exist in your project. They're just **not in legal's corpus**.

[SCREEN: the two-row table.]

Here's the split, and it mirrors everything else in this workshop.

How the process **works** — cert rules, royalty tiers, insurance minimums — lives in documents. In the RAG corpus. Read by legal.

The **records** — exclusivity contracts, trademarks, style guidelines, the rate card — live in Firestore registries. Read by MCP servers, through deterministic tools.

[BEAT]

Prose that has to be *interpreted* goes in RAG.

Facts that must be *looked up exactly* go in a registry behind a tool.

An exclusivity conflict is not something you want a language model inferring from a wiki page.

That's why the exclusivity check belongs to vendor clearance. You'll watch it fire in a minute.

And notice what legal did **not** do. It didn't invent an answer. "I could not find any information" is correct behaviour for a retrieval agent. That's worth more than a confident guess.

---

## 22:00 — The handoff

[DO: stop both tabs. Start the mesh, then Dev UI on vendor_clearance.]

Stop what's running first. Both tabs. Vendor clearance's Dev UI wants port 8000, and legal's Dev UI is holding it. And the mesh starts its own MCP servers on the ports the old ones have.

The mesh brings up all three MCP servers **and every agent as an A2A service** — including legal.

[BEAT]

That's the shift worth catching.

A minute ago you were *typing at* legal in a playground. Now the same agent is running as a **service**. Waiting to be called by another agent.

Nothing about legal changed. Only who talks to it.

---

## 23:30 — Three turns

You're going to onboard a vendor to a category it doesn't already have. That, and only that, triggers the handoff.

**The category has to be genuinely new.** This vendor already makes action figures, vinyl figures and resin statues. Ask for any of those and the agent clears the vendor and stops — correctly. There's nothing to onboard.

Apparel is one it doesn't have.

The gate is in the code: legal runs only when the report comes back cleared **and** the reasoner actually called update or create. A quiet, correct no-op looks exactly like a broken handoff. If legal doesn't fire, check the vendor's existing categories first.

**This takes three messages.**

**Turn one.** The request. It comes back asking for approval before it touches the vendor record.

**Turn two.** Approve — **and restate the whole request.**

[BEAT]

Because here's what surprises everyone. **Answering just "yes" will not work.**

It comes back blocked, asking for the vendor, character, territory and category all over again.

And the reason is worth understanding. The reasoner's brief is a template of state fields. Its instruction says: take anything missing from the user's message.

In the **console** you build in Step 6, those fields come from a **form**. So the user really can just click yes.

The **Dev UI has no form.** Your message is the only channel. So every turn has to carry the whole picture.

Same agent. Different transport.

**Turn three.** The human-in-the-loop question. Legal reconstructs its process and finds it needs a **safety-certification ID**. A value that exists in no record anywhere. It asks. And the question travels back up to you.

The id is arbitrary. **Any string works.** Because no document in the corpus defines a format for it.

That's the point the documents themselves make. One of them has an open action item to *document the safety cert ID step*. Another has somebody complaining they've asked three times for it to be written down.

**The one field that blocks every contract is the one nobody specified.**

---

## 26:30 — Do and don't

**Do use RAG for process, and a registry for records.** Interpretation versus exact lookup.

**Don't build a silent fallback.** Expose which path ran, or you'll debug bad answers for hours.

**Do talk to a sub-agent directly before testing it inside a handoff.** Isolate the failure before you nest it.

**Don't assume "yes" is enough input** when nothing is supplying state. Transport shapes conversation.

**Do let the agent say it doesn't know.** A retrieval agent that admits a gap is working.

---

## 27:30 — Recap and hook

Two more agents. And the first time work crossed an agent boundary. Legal reconstructs an undocumented process from scattered prose. Vendor clearance calls it over A2A. And a question from deep inside legal travelled all the way up to you.

Next: the **orchestrator**. One agent calling three others, at the same time.

And that's where a genuinely brutal bug lives. It doesn't show up on your laptop. It doesn't show up in testing.

It shows up in production. And it turns most of your polls into 404s.

See you there.
