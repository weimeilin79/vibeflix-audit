# Step 4 — Vendor Clearance + Legal

**Target runtime:** 24–28 min · **Lab section:** `Vendor Clearance + Legal`

---

## 00:00 — Cold open

[SCREEN: an email thread, a personal checklist, a wiki page that stops mid-sentence.]

Almost every company has a process that works, that everyone follows, and that has never been written down in one place. It lives in an email thread from eighteen months ago, in somebody's onboarding checklist on their own laptop, and in a Confluence page that stops in the middle of a sentence.

This step builds an agent whose job is to reconstruct a process from exactly that kind of wreckage, and then hands it real work from another agent, across a network boundary, with a human interrupting partway through. That's three hard problems at once, so we'll take them in order.

---

## 01:30 — The tribal-knowledge problem

Legal clearance at Vibeflix is a real process. There are certification rules for apparel, definitions for the royalty tiers, insurance minimums, and a set of steps for amending a contract. None of it sits in a database, because it's prose scattered across documents that were never meant to be read together.

You could put a lawyer in a room for a week and turn all of that into a decision table. Companies do it, it's expensive, it goes stale, and the moment the process changes you're doing it again.

The alternative is retrieval, where instead of memorising the process the agent looks it up every time, from the documents themselves. When the documents change the agent's behaviour changes with them, without retraining and without rewriting a prompt. That's what RAG is for, and this is a case where it genuinely earns its place.

---

## 03:00 — Building the knowledge base

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_legal_rag.sh
```

[DO: run it. Slow — several minutes.]

Four things happen while that runs. It uploads the documents to a bucket, creates a corpus configured with an embedding model, imports the files, and then RAG Engine chunks, embeds and indexes every document behind the scenes.

The import is the slow part. You'll see it report that it's importing files and then apparently do nothing for several minutes, and it is in fact working, so let it finish.

On a brand-new project you may also see it retry because Vector Search permissions are still propagating. That's expected as well, since enabling the API grants the RAG service agent its role and that grant takes a couple of minutes to take effect. The script waits it out.

When it finishes it writes the corpus id straight into your `.env` file, so there's nothing to copy and paste. The next time you source that file it gets exported, and when you deploy legal in a few minutes the value travels with the agent.

---

## 05:30 — Asking the corpus directly

Before we build anything on top of this, let's ask the corpus a question with no agent and no model involved, going straight at the RAG API.

[DO: run the retrieveContexts curl.]

[SCREEN: three excerpts, with sources and scores.]

Three excerpts come back, and they come from three different documents: an email thread, somebody's onboarding checklist, and a wiki page.

That result is the tribal-knowledge problem in miniature. The answer to one straightforward question about apparel certifications is spread across three artefacts, none of which is authoritative and none of which is complete.

Two practical notes. A lower score means a closer match here, which catches people out. And if the contexts come back empty immediately after the import, indexing hasn't caught up yet, so wait a minute and run it again — this is the one situation where finding nothing doesn't indicate a problem.

---

## 07:30 — The trap inside the retrieval tool

[SCREEN: `agents/legal/legal_kb.py`.]

The agent gets a single tool for this, and it has two backends. If the corpus is configured it queries Vertex RAG Engine, and if it isn't configured, or Vertex is unreachable, it falls back to a local keyword search across the same files so the agent keeps working offline.

[DO: run the Python heredoc that calls the tool directly.]

[SCREEN: `retriever: vertex_rag` and three hits.]

The field to watch in that output is `retriever`, and it's the reason we're running this by hand rather than through the agent.

The fallback is deliberate, because an agent shouldn't die just because RAG is unavailable. The consequence is that a broken corpus keeps answering questions, using keyword matches instead of semantic retrieval, and it does so confidently.

Run the same command with the corpus unset and you'll see `retriever: local_keyword`, and the top hit for a certifications question becomes a document about customs codes. The answer looks plausible, it's wrong, and there's no error anywhere in the output. So whenever legal's answers start feeling subtly off, that field is the first thing to check.

The general lesson is that a silent fallback will eventually fool you, so if you build one, make its state visible.

---

## 10:30 — A2A, and calling another agent

The second problem in this step is that vendor clearance needs legal to do something, and legal is a separate agent in its own engine with its own identity.

A2A is a small HTTP contract that every ADK agent speaks. Each agent publishes an agent card at a known URL describing what it is and how to reach it. To call one you POST a message to its endpoint, which returns a task id, and then you poll that task until it's finished. The task is the unit of work, which is a detail that matters enormously in Step 5.

In ADK you construct a remote agent with the target's card and from then on you invoke it like a local sub-agent, so the HTTP is handled for you. The mental model to carry forward is that an agent running in another engine is a step you can call.

---

## 12:30 — Two things this mesh had to add

There are two details here that cost about a day each if nobody warns you.

The agent card names the wrong host. Agent Runtime's template hardcodes the plain aiplatform host into the card each engine serves, while the Agent Gateway in Step 7 only authorises the mTLS host and refuses the plain one. Since every standard A2A client just follows whatever the card says, you end up having to build the card yourself.

The stock client also sends blocking requests rather than send-and-poll. A2A is a send-then-poll protocol, but the stock client holds one long request open, and Agent Runtime terminates that at around 180 seconds while the callee is still working perfectly well. Fast hops never notice, and a long one fails in a way that's hard to interpret.

Both fixes are hidden inside a subclass so that every call site stays ordinary ADK, and now you know why that subclass exists.

---

## 14:30 — Deploying both, and the collect in the middle

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py legal
python deploy/collect_agent_identities.py
python deploy/deploy_agents_a2a.py vendor_clearance
python deploy/collect_agent_identities.py
```

There's a collect in the middle of that sequence and it's load-bearing.

Vendor clearance calls legal, so it has to be deployed already knowing legal's A2A URL. That URL contains legal's engine id, which doesn't exist until legal has been deployed, and the deploy script reads it out of the identities file that only the collect script writes. Deploy both back to back and vendor clearance looks up a URL that hasn't been recorded yet, so it skips and tells you it's skipping.

It's reasonable to ask why this one can't be computed away. In Step 6 you'll meet the mirror image of this problem, where the engines need the app's URL, and that one turns out to be derivable from your project number, so no second pass is required. Engine ids work differently, because Agent Runtime mints a random one, and the only way to learn legal's address is to deploy it and read it back.

[DO: start the deploys. Two agents here, so it's the longest wait in the workshop — jump cut.]

Then grant each of them its own access.

---

## 17:00 — Talking to legal on its own first

Before we watch the handoff, it's worth talking to legal directly, because in the handoff legal answers from inside another agent's workflow. If retrieval came back empty you'd see a vague vendor-clearance result rather than the actual cause.

[DO: mesh tab, then Dev UI on agents/legal.]

Ask it two questions in this order, because they're a matched pair and the second one is supposed to come up empty.

The first is something only the scattered documents know:

> What does "annual-volume band" mean, and what are the options?

[SCREEN: an answer, with the royalty tiers.]

Watch the trace and you'll see it call the search tool, and the answer it assembles comes from documents that never state it in one place.

The second is something the documents don't contain:

> Are there style guidelines for grogu, and any exclusivity in North America?

[SCREEN: "I could not find any information regarding..."]

---

## 20:00 — Why the second question has no answer

Nothing is broken here. Those two facts exist in your project, they're just held somewhere other than legal's corpus.

[SCREEN: the two-row table.]

There's a split here that mirrors everything else in this workshop. How the process works — the certification rules, the royalty tiers, the insurance minimums — lives in documents, in the RAG corpus, and legal reads it. The records themselves — exclusivity contracts, trademarks, style guidelines, the rate card — live in Firestore registries and the MCP servers read them through deterministic tools.

Prose that has to be interpreted belongs in RAG, and facts that have to be looked up exactly belong in a registry behind a tool. An exclusivity conflict is the second kind, and it's not something you want a language model inferring from a wiki page, which is why that check belongs to vendor clearance instead.

It's also worth noticing what legal did when it couldn't find an answer, which is that it said so. Admitting a gap is correct behaviour for a retrieval agent and it's worth considerably more than a confident guess.

---

## 22:00 — The handoff

[DO: stop both tabs. Start the mesh, then Dev UI on vendor_clearance.]

Stop both tabs first, because vendor clearance's Dev UI wants port 8000 which legal's Dev UI is holding, and the mesh starts its own MCP servers on the ports the current ones are using.

The mesh brings up all three MCP servers along with every agent as an A2A service, including legal. That's a shift worth noticing: a few minutes ago you were typing at legal in a playground, and now the same agent is running as a service, waiting to be called by another agent. Nothing about legal changed, only who talks to it.

---

## 23:30 — Three turns

What you're going to do is onboard a vendor into a category it doesn't already have, because that's the only thing that triggers the handoff.

The category genuinely has to be new for that vendor. This one already makes action figures, vinyl figures and resin statues, so if you ask for any of those the agent correctly clears the vendor and stops, since there's nothing to onboard. Apparel is one it doesn't have.

The gate lives in the code, and legal only runs when the report comes back cleared and the reasoner actually called update or create on the vendor. A quiet, correct no-op looks very similar to a broken handoff, so if legal doesn't fire, check the vendor's existing categories before you check anything else.

This takes three messages. The first is the request, and it comes back asking for approval before it touches the vendor record.

The second is where you approve, and you also have to restate the whole request. Answering with just "yes" comes back blocked, asking for the vendor, character, territory and category all over again, which surprises everyone the first time.

The reason is worth understanding. The reasoner's brief is a template of state fields, and its instruction tells it to take anything missing from the user's message. In the console you build in Step 6 those fields come from a form, so a user really can just click yes. The Dev UI has no form, so your message is the only channel available and every turn has to carry the whole picture. Same agent, different transport.

The third turn answers the human-in-the-loop question. Legal reconstructs its process, discovers it needs a safety-certification ID, and finds that value exists in no record anywhere, so it asks, and the question travels back up to you.

The id itself is arbitrary and any string works, because no document in the corpus defines a format for it. That's the point the documents themselves are making. One of them contains an unresolved action item to document the safety cert ID step, and another has somebody complaining that they've asked three times for it to be written down. The one field that blocks every contract is the one nobody ever specified.

---

## 26:30 — Do and don't

Use RAG for process and a registry for records, which is the interpretation-versus-exact-lookup split applied one level up.

Don't build a silent fallback. Expose which path ran, or you'll spend hours debugging answers that look fine.

Talk to a sub-agent directly before you test it inside a handoff, so you isolate failures before you nest them.

Don't assume a bare "yes" is enough input when nothing is supplying state, because the transport shapes the conversation.

And let the agent say it doesn't know, because a retrieval agent that admits a gap is working properly.

---

## 27:30 — Where that leaves us

You've added two more agents and watched work cross an agent boundary for the first time. Legal reconstructs an undocumented process from scattered prose, vendor clearance calls it over A2A, and a question from deep inside legal travelled all the way back up to you.

Next we build the orchestrator, which calls three agents at once rather than one. That's also where a genuinely difficult bug lives — one that never appears on your laptop or in testing, shows up under production load, and turns most of your polls into 404s.

See you there.
