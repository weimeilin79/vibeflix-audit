# Step 1 — Setup & Foundations

**Target runtime:** 20–24 min · **Lab section:** `Setup & Foundations`

---

## 00:00 — Cold open

[SCREEN: the finished console, mid-audit. Three agent boxes light up at once, tool LEDs blink, a contract id appears.]

What you're looking at is a licensing audit running end to end. A vendor has applied to manufacture a product, and six agents are working out whether Vibeflix can approve it. They're checking the artwork against brand rules, checking the royalty numbers against a rate card, checking whether a competitor already holds an exclusive contract in that territory, and working out what the legal process for onboarding actually involves. About sixty seconds from now it will finish with either a signed contract or a specific reason it can't happen. The same decision used to take around three weeks.

Everything on this screen is really running. The six agents were each deployed separately and each has its own identity. They call three tool servers that are locked down tightly enough that if you open one of those URLs in a browser you'll get a 403, which is something I'll ask you to try for yourself later in this video.

[SCREEN: cut to an empty Cloud Shell.]

We're starting from nothing, and in this first step we won't build an agent at all. We're going to build the layer that everything else stands on, and I'll spend a fair bit of time on why it's shaped this way, because most of the decisions in the next seven steps only make sense once you understand what we set up here.

---

## 02:00 — The problem we're solving

It's worth starting with the business problem, because the architecture follows from it.

Vibeflix licenses characters to manufacturers. A vendor comes along and asks to make vinyl figures of a particular character, for North America, at a royalty rate they've proposed. Somebody has to decide whether that's allowed, and that decision breaks down into four fairly different jobs.

Someone has to look at the artwork and check it against the brand rules. Someone has to check the money — the royalty rate, the advance, the minimum guarantee — against a rate card that has tiers and modifiers in it. Someone has to check whether an exclusivity contract already locks that character and category in that territory. And someone has to know the legal process for onboarding a vendor into a category they've never manufactured before, which in most companies is knowledge that lives in people's heads rather than in a document.

That's four kinds of expertise, which in practice means four people, a shared inbox, and roughly three weeks of back and forth.

The obvious thing to try is handing all of it to one large language model. Give it the rate card, the contracts and the artwork, and ask it to make the call. I'd encourage you not to, and the reason is the most important idea in this entire workshop.

---

## 04:00 — The idea the whole build rests on

There are two kinds of work inside that decision, and they fail in very different ways.

The first kind is fuzzy. Looking at a piece of artwork and saying what it is — that's a vinyl figure, and there's no printed text on it. Reading a messy Slack thread and working out what the process actually is. Ask two people to do that and you'll get slightly different wording from each of them, and if you ask a model twice you'll get the same variation. That's inherent to the task, and it's fine.

The second kind is exact. Is a 10% royalty above or below a minimum of 10%? Is this particular vendor named on the exclusivity contract? Does a projection of 30,000 units qualify for a discount tier that begins at 100,000? These have one right answer, the answer has to be identical every time you ask, and it has to match what your finance team would get with a spreadsheet.

Language models are very good at the first kind of work and structurally unsuited to the second, because they're probabilistic. That matters more than it might sound. If your system returns one royalty rate on Monday and a different one on Tuesday for the same deal, you have a system that can't be used to sign contracts at all.

So the rule we follow for the whole build is that the model does the fuzzy work and ordinary code does the deciding. The model looks at the image and reports what it sees. A tool takes those facts, applies the rules, and returns a verdict. The model has no way to argue with that verdict and no way to produce one of its own.

[SCREEN: two columns — MODEL: extract, interpret, converse. TOOLS: compare, calculate, decide.]

Hold on to that split, because every step from here is another place where we apply it.

---

## 06:30 — Putting the exact work in tool servers

If the exact work belongs in tools, the next question is where those tools should live.

The simplest answer is inside the agent, as ordinary Python functions it imports. That works, and for a prototype it's a reasonable choice. We're going to do something else, for three reasons that all show up later.

If the pricing logic sits inside the pricing agent, then that agent becomes the only thing in your system that can price anything. When the orchestrator needs a rate card it has to go through the agent to get one. When someone in finance wants to check a number they can't, because the logic is buried inside a prompt loop. And when you want to audit which rules were applied to a particular deal, you end up reading model transcripts.

So instead the tools live in their own servers, and the agents call them over a protocol called MCP, the Model Context Protocol.

[SCREEN: three boxes — mcp_brand_style, mcp_licensing, mcp_market.]

There are three of them in this system. One runs the brand compliance checks. One owns the licensing data, which means vendors, rate cards, exclusivity contracts and executed contracts. And one handles market data, scanning marketplaces and checking volume caps.

The thing worth noticing is how ordinary these are. They're web services with URLs, deployed to Cloud Run, with IAM policies attached. You can point anything at them — another agent, a script, a dashboard — because the business logic is a service with an address.

That's also what makes the last step of this workshop possible. You can attach a policy to an HTTP endpoint, and there's no equivalent for a Python function buried inside a reasoning loop.

---

## 09:00 — The registry, and why we set it up now

The third piece we provision in this step is the Agent Registry, and it's the one people tend to skim past.

The registry is a catalogue. Every MCP server gets an entry in it, and later every agent does too, recording its name, its address and the interface it speaks. Given that the agents already receive their URLs through environment variables, it's reasonable to wonder what the catalogue is for.

The first answer is discovery, which is how the console can list every available tool without anyone grepping through the codebase. That's useful, but it isn't the real reason.

The real reason arrives in Step 7, when we put a governed gateway in front of all this traffic. That gateway works on a deny-by-default basis and it only routes requests to destinations that appear in the registry. Anything unregistered becomes unreachable, which turns registration into the enrolment step that makes governance possible at all. We do it now for the MCP servers, and again in Step 7 for the agents.

---

## 11:00 — Getting set up

[DO: Activate Cloud Shell.]

Everything in this workshop runs in Cloud Shell, which comes with gcloud, python3 and git already installed. One thing it no longer ships is terraform — there's a placeholder on the path that prints installation instructions if you call it, which is confusing the first time you hit it. Our init script deals with that, so hold off on installing anything yourself.

[DO: run the auth check.]

```
gcloud auth list
gcloud config get-value project
```

Your account should be listed as ACTIVE and the project should be the one you intend to spend money in. It's worth actually reading that output, because everything we create from here lands in whatever project it names.

[DO: clone.]

```bash
git clone https://github.com/weimeilin79/vibeflix-audit
cd vibeflix-audit
```

---

## 12:30 — How the repo is laid out

[SCREEN: the directory tree.]

Let me spend thirty seconds on the layout, because it makes everything that follows easier to read.

The `agents` folder holds the six agents, one folder each, and `mcp_servers` holds the three tool servers we just discussed. The `packages` folder contains the shared library, split into four subpackages named after who imports them: one for transport, one for ADK building blocks, one for MCP-only helpers, and one for auth and telemetry, which both sides use. That naming is deliberate, so when you're wondering whether it's reasonable to import something, the folder name answers you.

`deploy` holds the deploy and verify scripts, the Terraform, and your `.env` file. `frontend` is the React console. And `resource` holds seed data, including the legal documents we turn into a searchable knowledge base in Step 4.

In practice you'll spend most of your time reading `agents` and `mcp_servers`, and running things out of `deploy`.

---

## 14:00 — Running init.sh

```
cd ~/vibeflix-audit
./init.sh
```

[DO: run it.]

While that's going I'll tell you what it does, because it does more than the name suggests.

It begins by checking your environment before it creates anything — every CLI the workshop needs, that you're authenticated, and that application-default credentials exist. If something's missing it stops there, before any provisioning has started. That ordering is deliberate, because the alternative is a script that builds half your infrastructure and then dies on a missing binary, leaving you to work out what was created and what wasn't.

After that it points gcloud at your project, creates the virtual environment, installs every dependency, installs a working terraform if Cloud Shell's placeholder is in the way, and writes `deploy/.env`, which is the config file every other script in this workshop reads. It usually takes a few minutes, most of that being Python packages.

There's one habit I'd like you to build while this runs, because skipping it is the most common way people lose twenty minutes on this workshop. Every new terminal tab you open needs `cd ~/vibeflix-audit` followed by `source ./env.sh`.

A new Cloud Shell tab starts in your home directory with a clean environment, so without those two lines you'll be running Cloud Shell's system Python instead of the project's virtual environment. The failure that produces is an `ImportError` from somewhere deep inside a Google library, which gives you very little to go on and can cost you a while.

Do note the `source` at the front. Running `./env.sh` on its own achieves nothing, because a script can't change the environment of the shell that launched it, and it will tell you if you get that the wrong way round. Every command block in this lab begins with those two lines for exactly this reason, so you can copy any block into any tab and have it work.

---

## 16:30 — Running setup.sh

```bash
cd ~/vibeflix-audit
source ./env.sh
./workshop/setup.sh
```

[DO: run it. Several minutes — plan a jump cut.]

This runs nine steps in order: preflight, enabling APIs, foundations, buckets, Firestore, Pub/Sub, building and deploying the three MCP servers, and registering them.

Three of the things it creates are worth understanding rather than watching scroll past.

Firestore is the database for the whole mesh. It holds the registries that the MCP servers read from, and it holds the vendors collection, which is the one piece of data the agents actually modify at runtime when they onboard somebody new.

The Pub/Sub topic carries telemetry. Every agent publishes events as it works, and in Step 6 the console subscribes to that stream, which is what makes the workflow graph animate in real time.

Artifact Registry stores container images, because the MCP servers and the console app are all built into images before they're deployed.

There's an operational point I want to make here, because it'll save you frustration later. Every script in this workshop is safe to run again. If one stops with an error, fix whatever it reported and run the identical command — work that already completed gets detected and skipped rather than repeated.

You'll need that occasionally, and when you do it generally won't be your fault. These are real cloud APIs, several of them still in preview, and they sometimes return a transient internal error for reasons that have nothing to do with your project. The setup scripts retry those automatically and stop with a clear message if retrying doesn't help. So when you see a red cross, read what it says and then run `./workshop/setup.sh` again — it re-checks all nine steps and redoes only what's missing. Treat it as a to-do item.

---

## 19:00 — Verifying, and the check that makes the point

[DO: run it.]

```bash
cd ~/vibeflix-audit
source ./env.sh
./deploy/verify/step1.sh
```

This checks the image registry, the telemetry topic, the Firestore database, and all three MCP servers.

The last check is the interesting one, because it confirms the MCP servers are running and that they return a 403. That 403 is the test passing.

Those services are deployed with no public access whatsoever. A caller needs the Cloud Run invoker role to reach them, and at this moment nothing in your project has it, because no agent exists yet to grant it to.

[SCREEN: paste an MCP URL into a browser tab. 403.]

Go and try that yourself, because it's the first line of a security story we finish in Step 7. The tools that make the consequential decisions in this system have never been reachable from the open internet, and they still won't be when we're done.

---

## 21:00 — Do and don't

There are four things I'd take away from this step.

Put the exact logic in a tool server, where it has a URL that IAM can be pointed at. That turns out to be worth a great deal by Step 7.

Keep the model away from any decision you'd have to defend afterwards. If somebody could sue over it, audit it, or reproduce it in a spreadsheet, it belongs in a tool.

Re-run scripts when they fail, because idempotency here is a design feature rather than an accident.

And run `cd` and `source ./env.sh` in every new tab. That's the third time I've mentioned it, and it's still the thing most likely to cost you time today.

---

## 22:00 — Where that leaves us

[SCREEN: architecture diagram, foundation layer lit.]

At this point you have three deterministic, IAM-gated tool servers registered in the Agent Registry, along with a seeded database, a telemetry topic and an image registry. What you don't have is a single agent, and that's deliberate — the interesting decisions in the next seven steps are only available to us because this fairly unglamorous layer exists first.

In the next step we build the first agent, brand style. It looks at a product mock-up, works out what it's looking at, and hands those facts to a tool that produces the actual verdict. That's the fuzzy-versus-exact split running for real, and it takes about fifteen minutes.

See you there.
