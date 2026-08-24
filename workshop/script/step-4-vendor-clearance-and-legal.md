# Step 4 — Vendor Clearance + Legal

**Target runtime:** 18–21 min · **Lab section:** `Vendor Clearance + Legal`

---

## 00:00 — Cold open

[SCREEN: an email thread, a personal checklist, a wiki page that stops mid-sentence.]

Almost every company has a process that works, that everyone follows, and that was never written down in one place. It lives in an email thread from eighteen months ago, somebody's onboarding checklist on their own laptop, and a Confluence page that stops mid-sentence.

This step builds an agent that reconstructs a process from that wreckage, then hands it real work from another agent, across a network boundary, with a human interrupting partway through.

---

## 01:00 — The tribal-knowledge problem

Legal clearance at Vibeflix is a real process. Certification rules for apparel, royalty tier definitions, insurance minimums, and the steps for amending a contract. None of it is in a database, because it's prose scattered across documents that were never meant to be read together.

You could put a lawyer in a room for a week and turn it into a decision table. That's expensive, it goes stale, and the moment the process changes you do it again.

Retrieval is the alternative. The agent looks the process up every time, from the documents themselves, so when the documents change the agent's behaviour changes with them.

---

## 02:00 — Building the knowledge base

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/setup_legal_rag.sh
```

[DO: run it. Several minutes.]

It uploads the documents, creates a corpus with an embedding model, imports the files, and RAG Engine chunks, embeds and indexes them.

The import is the slow part. It reports that it's importing and then appears to do nothing for minutes. It's working.

On a new project you may see it retry because Vector Search permissions are still propagating. Enabling the API grants the RAG service agent its role, that takes a couple of minutes to take effect, and the script waits it out.

When it finishes it writes the corpus id into your `.env`, so there's nothing for you to copy anywhere. Sourcing that file exports it, and it travels with the agent when you deploy legal.

---

## 03:30 — Asking the corpus directly

[DO: run the retrieveContexts curl.]

[SCREEN: three excerpts, with sources and scores.]

No agent, no model, straight at the RAG API.

Three excerpts come back from three different documents. An email thread, an onboarding checklist, and a wiki page. The answer to one question about apparel certifications is spread across three artefacts, none of them authoritative and none of them complete.

Two things to know while reading that output. A lower score means a closer match here. And if contexts come back empty right after the import, indexing hasn't caught up, so wait a minute and re-run.

---

## 05:00 — The trap in the retrieval tool

[SCREEN: `agents/legal/legal_kb.py`.]

The tool has two backends. With a corpus configured it queries Vertex RAG Engine. Without one, or when Vertex is unreachable, it falls back to local keyword search over the same files so the agent keeps working offline.

[DO: run the Python heredoc that calls the tool directly.]

[SCREEN: `retriever: vertex_rag` and three hits.]

Watch the `retriever` field. That's why we're calling the tool by hand instead of going through the agent.

The fallback is deliberate, so an agent doesn't die because RAG is unavailable. The consequence is that a broken corpus keeps answering, using keyword matches, confidently.

Run the same command with the corpus unset and you get `retriever: local_keyword`. The top hit for a certifications question becomes a document about customs codes. Plausible, wrong, and no error anywhere. When legal's answers start feeling subtly off, check that field first.

A silent fallback will eventually fool you, so make its state visible.

---

## 07:00 — A2A

Vendor clearance needs legal to do something, and legal is a separate agent in its own engine with its own identity.

A2A is a small HTTP contract every ADK agent speaks. Each agent publishes an agent card at a known URL describing what it is and how to reach it. You POST a message to its endpoint, get a task id, then poll that task until it's done. The task is the unit of work, which matters in Step 5.

In ADK you construct a remote agent with the target's card and invoke it like a local sub-agent, so the HTTP is handled for you. An agent in another engine becomes a step you can call.

---

## 08:00 — Two things this mesh had to add

The agent card names the wrong host. Agent Runtime hardcodes the plain aiplatform host into the card each engine serves, while the gateway in Step 7 only authorises the mTLS host and refuses the plain one. Standard A2A clients follow the card, so this project builds the card itself.

The stock client also sends blocking requests. A2A is send-then-poll, and the stock client holds one long request open. Agent Runtime terminates that at around 180 seconds while the callee is still working. Fast hops never notice, and long ones fail confusingly.

Both fixes live in a subclass, so every call site stays ordinary ADK.

---

## 09:30 — Deploying both

```bash
cd ~/vibeflix-audit
source ./env.sh
python deploy/deploy_agents_a2a.py legal
python deploy/collect_agent_identities.py
python deploy/deploy_agents_a2a.py vendor_clearance
python deploy/collect_agent_identities.py
```

Skip the collect in the middle and the second deploy comes out wrong.

Vendor clearance calls legal, so it deploys knowing legal's A2A URL. That URL contains legal's engine id, which doesn't exist until legal is deployed, and the deploy script reads it from the identities file that only collect writes. Deploy both back to back and vendor clearance looks up a URL that isn't recorded yet, so it skips the wiring and says so.

In Step 6 you meet the mirror image, where the engines need the app's URL, and that one is derivable from your project number so no second pass is needed. Engine ids are minted randomly by Agent Runtime, so the only way to learn legal's address is to deploy it and read it back.

[DO: start the deploys. Two agents, so it's the longest wait — jump cut.]

Then grant each of them its own access.

---

## 11:00 — Talking to legal alone first

In the handoff, legal answers from inside another agent's workflow, so empty retrieval shows up as a vague vendor-clearance result instead of the real cause.

[DO: mesh tab, then Dev UI on agents/legal.]

Ask two questions in this order. The second one is supposed to come up empty.

> What does "annual-volume band" mean, and what are the options?

[SCREEN: an answer, with the royalty tiers.]

It calls the search tool, and the answer it assembles comes from documents that never state it in one place.

> Are there style guidelines for grogu, and any exclusivity in North America?

[SCREEN: "I could not find any information regarding..."]

---

## 13:00 — Why the second has no answer

Those facts exist in your project, held somewhere other than legal's corpus.

[SCREEN: the two-row table.]

How the process works, so certification rules, royalty tiers and insurance minimums, lives in documents, in the RAG corpus, read by legal. The records, so exclusivity contracts, trademarks, style guidelines and the rate card, live in Firestore registries, read by MCP servers through deterministic tools.

Prose that has to be interpreted belongs in RAG. Facts that have to be looked up exactly belong in a registry behind a tool. An exclusivity conflict is the second kind, which is why that check belongs to vendor clearance.

Legal also said it couldn't find an answer instead of inventing one, which is correct behaviour for a retrieval agent.

---

## 14:30 — The handoff

[DO: stop both tabs. Start the mesh, then Dev UI on vendor_clearance.]

Stop both tabs, because vendor clearance's Dev UI wants port 8000 and the mesh starts its own MCP servers on the ports the current ones hold.

The mesh brings up all three MCP servers and every agent as an A2A service, including legal. A few minutes ago you were typing at legal in a playground, and now it's a service waiting to be called by another agent. Only who talks to it changed.

---

## 15:30 — Three turns

Onboard a vendor into a category it doesn't already have, because that's the only thing that triggers the handoff.

The category has to be new. This vendor already makes action figures, vinyl figures and resin statues, so asking for any of those clears the vendor and stops, since there's nothing to onboard. Apparel is one it lacks.

The gate is written in the code. Legal runs only when the report comes back cleared and the reasoner called update or create on the vendor. A quiet, correct no-op resembles a broken handoff, so if legal doesn't fire, check the vendor's categories first.

This takes three messages.

The first is the request, and it comes back asking approval before touching the vendor record.

The second approves and restates the whole request. Answering "yes" on its own comes back blocked, asking for the vendor, character, territory and category again.

The reasoner's brief is a template of state fields, and its instruction says to take anything missing from the user's message. In the console you build in Step 6 those fields come from a form, so a user can click yes. The Dev UI has no form, so your message is the only channel and every turn carries the whole picture.

The third answers the human-in-the-loop question. Legal reconstructs its process, finds it needs a safety-certification ID, discovers that value exists in no record, and asks. The question travels back up to you.

Any string works, because no document in the corpus defines a format for it. One document has an unresolved action item to document the safety cert ID step, and another has somebody complaining they've asked three times for it to be written down. The one field blocking every contract is the one nobody specified.

---

## 17:30 — Do and don't

Use RAG for process and a registry for records.

Expose which retrieval path ran, or you'll debug good-looking answers for hours.

Talk to a sub-agent directly before testing it inside a handoff.

Don't assume a bare "yes" is enough input when nothing supplies state.

Let the agent say it doesn't know.

---

## 18:15 — Where that leaves us

Two more agents, and work crossing an agent boundary for the first time. Legal reconstructs an undocumented process from scattered prose, vendor clearance calls it over A2A, and a question from inside legal reached you.

Next, the orchestrator calls three agents at once. That's also where a bug lives that never appears on your laptop or in testing, shows up under production load, and turns most of your polls into 404s.

See you there.
