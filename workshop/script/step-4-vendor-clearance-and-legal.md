# Step 4 — Vendor Clearance + Legal

**Target runtime:** 24–28 min · **Lab section:** `Vendor Clearance + Legal`

---

## 00:00 — Cold open

[SCREEN: an email thread, a personal checklist file, a half-finished wiki page — three documents, side by side.]

Somewhere in your company there's a process that works, that everyone follows, and that nobody has ever written down in one place.

It lives in an email thread from eighteen months ago. In somebody's onboarding checklist on their own laptop. In a Confluence page that stops mid-sentence.

[BEAT]

That's this step. We're going to build an agent whose job is to reconstruct a process from the wreckage — and then hand real work to it from another agent, across a network boundary, with a human interrupting in the middle.

Three hard things at once. Let's take them in order.

---

## 01:30 — The tribal-knowledge problem

Legal clearance at Vibeflix is a genuine process. Certification requirements for apparel. Royalty tier definitions. Insurance minimums. The steps for a contract amendment.

None of it is in a database. It's in prose, scattered across a folder of documents that were never meant to be read together.

Now — you could sit a lawyer down for a week to formalise it into a decision table. Companies do that. It's expensive, it goes stale, and the moment the process changes you're doing it again.

The alternative is **retrieval**. Instead of memorising the process, the agent looks it up — every time, from the documents themselves. When the documents change, the agent's behaviour changes. No retraining, no re-prompting.

That's RAG, and this is the case where it genuinely earns its place.

---

## 03:00 — Build the knowledge base

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_legal_rag.sh
```

[DO: run it. This is slow — several minutes.]

Four things happen. It uploads the documents to a bucket. It creates a corpus — `vibeflix-legal-kb` — configured with an embedding model. It imports the files, and RAG Engine chunks, embeds and indexes every document behind the scenes.

**The import is the slow part.** When you see it importing files, it can sit there for minutes. It's working. Let it finish.

On a brand-new project you may also see it retrying on Vector Search permissions still propagating. That's expected too — enabling the API grants the RAG service agent its role, and the grant takes a couple of minutes to take effect. The script waits it out.

And when it finishes, it **writes the corpus id into `deploy/.env` for you**. Nothing to copy and paste. The next `source ./env.sh` exports it, and when you deploy legal in a moment, it travels with the agent.

---

## 05:30 — Verify the corpus actually answers

Before we build anything on top of this, let's ask the corpus a question **directly** — no agent, no model, just the RAG Engine API.

[DO: run the retrieveContexts curl.]

[SCREEN: three excerpts returned, with sources and scores.]

Look at what came back. Three excerpts, from **three different documents**. An email thread. Somebody's onboarding checklist. A wiki page.

[BEAT]

That is the tribal-knowledge problem in a single result. The answer to one straightforward question — what certifications does apparel need — is spread across three artefacts, none of which is authoritative, none of which is complete.

Also worth noting: **lower score means closer match** here. That trips people up.

And one thing that isn't a failure: if `contexts` comes back empty right after the import, indexing hasn't caught up. Wait a minute and run it again. It's the one case where "nothing found" doesn't mean something is wrong.

---

## 07:30 — The retrieval tool, and the trap inside it

[SCREEN: `agents/legal/legal_kb.py` — `search_legal_docs`.]

The agent gets one tool for this: `search_legal_docs`. It has two backends. If `RAG_CORPUS` is set, it queries Vertex RAG Engine. If it isn't — or Vertex is unreachable — it falls back to a local keyword search over the same files, so the agent still runs offline.

[DO: run the Python heredoc that calls the tool directly.]

Let's call it on its own — no agent, no model, just the function.

[SCREEN: `retriever: vertex_rag` and the three hits.]

Now. **Watch the `retriever` field. It's the whole point of running this.**

[BEAT]

That fallback is deliberate — the agent shouldn't die because RAG is down. But it means **a broken corpus doesn't look broken**. The agent keeps answering. It just answers from keyword matches instead of semantic retrieval.

Run the same command with `RAG_CORPUS` unset and you'll see it: `retriever: local_keyword`, and the top hit for a certifications question becomes a document about customs codes. Plausible-looking. Wrong. And no error anywhere.

So whenever legal's answers seem subtly off, check that field first. `vertex_rag` means the corpus is being used. `local_keyword` means it isn't.

This is a general lesson about graceful degradation: **a fallback that's silent is a fallback that will fool you.** If you build one, make its state observable.

---

## 10:30 — A2A: handing off to a remote agent

Second concept. Vendor clearance needs legal to do something. Legal is a completely separate agent, in its own engine, with its own identity.

How does one agent call another?

**A2A** — a small HTTP contract every ADK agent speaks. Each agent publishes an **agent card** at a well-known URL describing what it is and how to reach it. To call one, you POST a message to its endpoint, which returns a **task id**. Then you poll the task until it's done.

The *task* is the unit of work. Remember that — it matters enormously in Step 5.

In ADK you don't hand-write those calls. You construct a remote agent with the target's card, and from then on you invoke it like a local sub-agent. It makes the call and hands you back the result.

[BEAT]

**Treat an agent running in another engine as a step you can call.** That's the mental model.

---

## 12:30 — Two things this mesh had to add

Worth thirty seconds, because these are the kind of details that cost a day if nobody tells you.

**The agent card names the wrong host.** Agent Runtime's template hardcodes the plain aiplatform host into the card each engine serves. But the Agent Gateway in Step 7 only authorises the mTLS host, and refuses the plain one. Since every standard A2A client just follows the card's URL, you have to build the card yourself and point it at the right host.

**The stock client sends blocking, not send-and-poll.** Despite A2A being a send-then-poll protocol, the stock client holds one long request open — and Agent Runtime kills that at around 180 seconds, while the callee is still happily working. Fast hops never notice. A long one fails confusingly.

Both are hidden inside a subclass, so every call site stays ordinary ADK. But now you know why it exists.

---

## 14:30 — Deploy both, and why `collect` runs twice

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py legal
python deploy/collect_agent_identities.py
python deploy/deploy_agents_a2a.py vendor_clearance
python deploy/collect_agent_identities.py
```

Look at that ordering — there's a `collect` **in between**, and it's not decoration.

`vendor_clearance` calls `legal`, so it has to be deployed knowing legal's A2A URL. That URL contains legal's engine id, which doesn't exist until legal is deployed. The deploy script reads it out of `agent_identities.json`, and only `collect_agent_identities.py` writes that file.

Deploy both back to back and vendor clearance looks up a URL that isn't recorded yet — you'll see it skip, and say so.

[BEAT]

**Why can't this one be computed away?** In Step 6 you'll meet the mirror image — the app's URL, which the engines need — and that one turns out to be *derivable* from the project number, so no second pass is needed there.

Engine ids aren't. Agent Runtime mints a random one. The only way to learn legal's address is to deploy it and read it back. Deploy, collect, then deploy the agent that calls it.

[DO: start the deploys. Two agents here, so this is the longest wait in the workshop — plan the jump cut.]

Then grant each its own access.

---

## 17:00 — Try legal on its own first

Before we watch the handoff, let's talk to legal **directly**. Worth doing separately: in the handoff, legal answers from inside another agent's workflow — so if retrieval came back empty you'd see a vague vendor-clearance result rather than the real cause.

[DO: mesh tab, then Dev UI on agents/legal. Web Preview → 8000.]

Two questions, in this order. They're a **matched pair**, and the second one is *supposed* to come up empty.

**One — something only the scattered documents know:**

> What does "annual-volume band" mean, and what are the options?

[SCREEN: `status: answer`, with the royalty tiers.]

Watch the trace: it calls `search_legal_docs`, and the answer is assembled from documents that never state it in one place. That's the corpus doing its job.

**Two — something the documents don't contain:**

> Are there style guidelines for grogu, and any exclusivity in North America?

[SCREEN: "I could not find any information regarding..."]

---

## 20:00 — Why the second question has no answer, and shouldn't

Nothing is broken. Those two facts exist in your project — just **not in legal's corpus**.

[SCREEN: the two-row table.]

There's a split here that mirrors everything else in this workshop.

How the process **works** — cert rules, royalty tiers, insurance minimums, amendment steps — lives in the documents, in the RAG corpus, read by legal.

The **records** — exclusivity contracts, trademarks, style guidelines, the rate card — live in Firestore registries, read by the MCP servers through deterministic tools.

[BEAT]

`exclusivity_grogu_north_america` and `style_guidelines_grogu` are registry rows. Prose that has to be *interpreted* goes in RAG. Facts that must be *looked up exactly* go in a registry behind a tool.

An exclusivity conflict is not something you want a language model inferring from a wiki page.

That's why the exclusivity check belongs to vendor clearance, and you'll watch it fire in a moment.

And note what legal did **not** do: invent an answer. "I could not find any information" is the correct behaviour for a retrieval agent, and it's worth more than a confident guess.

---

## 22:00 — Now the handoff

[DO: stop both tabs. Start `./run_local.sh mesh`, then Dev UI on vendor_clearance.]

Stop what's running first — both tabs. Vendor clearance's Dev UI wants port 8000, which legal's Dev UI is holding, and `mesh` starts its own MCP servers on 9002 to 9004.

`mesh` brings up the three MCP servers **and every agent as an A2A service** — including legal on 8005.

[BEAT]

That's the shift worth noticing. A moment ago you were *typing at* legal in a playground. Now the same agent is running as a **service**, waiting to be called by another agent. Nothing about legal changed. Only who talks to it.

---

## 23:30 — Three turns, and the gate that decides

You're going to onboard a vendor to a category it doesn't already have. That, and only that, triggers the handoff.

**The category has to be genuinely new for that vendor**, or legal never runs. VND-1008 already makes action figures, vinyl figures and resin statues — ask for any of those and the agent correctly clears the vendor and stops, because there's nothing to onboard. **Apparel** is one it doesn't have.

The gate is in `vendor_clearance/agent.py` — legal runs only when the report comes back cleared **and** the reasoner actually called `update_vendor` or `create_vendor`. A quiet, correct no-op is easy to mistake for a broken handoff. If legal doesn't fire, check the vendor's existing categories first.

**This takes three messages, not one.**

**Turn one** — the request. It comes back `needs_input`: it wants approval before touching the vendor record.

**Turn two** — approve, **and restate the request**. And here's the surprise:

[BEAT]

**Answering just "yes" will not work.** It comes back blocked, asking for the vendor, character, territory and category all over again.

The reason is worth understanding. The reasoner's brief is a template of state fields, and its instruction says *take anything missing from the user's message*. In the **console** you build in Step 6, those fields come from a **form** — so the user really can just click yes. The **Dev UI has no form**. Your message is the only channel, so each turn has to carry the whole picture.

Same agent, different transport.

**Turn three** — the human-in-the-loop question. Legal reconstructs its process and discovers it needs a **safety-certification ID** — a value that exists in no record. It asks, and the question travels back up to you.

The id is arbitrary. **Any string works**, because no document in the corpus defines a format for it. That's not sloppiness in the lab — it's the point the documents themselves make. One of them has an unresolved action item to *document the safety cert ID step*. Another has someone complaining they've asked three times for it to be written down.

**The one field that blocks every contract is the one nobody specified.**

---

## 26:30 — Do and don't

**Do use RAG for process, and a registry for records.** Interpretation versus exact lookup — the same split, one level up.

**Don't build a silent fallback.** Expose which retriever ran, or you'll debug bad answers for hours.

**Do talk to a sub-agent directly before testing it inside a handoff.** Isolate the failure before you nest it.

**Don't assume "yes" is enough input** when there's no form supplying state. Transport shapes conversation.

**Do let the agent say it doesn't know.** A retrieval agent that admits a gap is working correctly.

---

## 27:30 — Recap and bridge

Two more agents, and the first time work crossed an agent boundary. Legal reconstructs an undocumented process from scattered prose. Vendor clearance calls it over A2A, and a question from deep inside legal travelled all the way back up to you.

Next step: the **orchestrator**. Instead of one agent calling one other agent, it fans out to three simultaneously — and that's where a genuinely brutal distributed-systems bug lives, one that turns most of your polls into 404s. We'll fix it properly.

See you there.
