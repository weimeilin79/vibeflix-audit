# Step 7 — Companion: Identity and the Gateway, in Plain Words

**Target runtime:** 10–13 min · **Companion to:** `step-7-identity-gateway-registry.md`

Optional explainer. Watch this before the main Step 7 if badges, tokens and certificates are new, or after it if any of it didn't land. It uses one picture the whole way through: an office building with a security desk.

---

## 00:00 — One building, one picture

[SCREEN: a simple office building. A security desk at the door. Rooms inside.]

Everything in this step is a building with a security desk.

Your agents are workers in that building. The tool servers are other buildings across the street. The security desk sits at the door and watches everyone going in and out.

Every idea in Step 7 is one piece of that picture, so let's put them in one at a time.

---

## 01:00 — The badge

Each worker has a badge with their own name on it.

Before agent identity, workers shared a badge. It said STAFF and it lived in a drawer, and whoever needed it took it. That's a service account. It works, and it has two problems. When something goes wrong you can't tell which worker did it, because the badge doesn't say. And anyone who can reach the drawer becomes that worker.

With agent identity, every worker gets their own badge with their own name printed on it. That's the `principal://` string you saw in the file. When a badge appears somewhere, you know exactly which worker was there. Take a worker away and their badge stops existing.

One badge each, and you can't have both kinds. A worker with a personal badge has no shared badge to fall back on.

---

## 02:15 — Who prints the badge

The building prints it.

Workers don't make their own badges, and neither do you. When you hire a worker — when you deploy an engine with agent identity — building security prints a badge for that worker and hands it over. That badge is the certificate.

You can't bring your own badge printer. The building prints badges for this building, and a badge printed somewhere else means nothing at this desk. That's what people mean when they say the identity comes from the platform.

---

## 03:15 — The day pass

A badge says who you are. A day pass says you're allowed to do something today.

Workers get day passes from a machine inside the building, and the machine gives out two kinds.

A plain day pass has nothing on it but today's date. If it falls out of your pocket, whoever picks it up can use it.

A **matched** day pass has your badge number printed on it. If that one falls out of your pocket, the person who picks it up can't use it, because the door also asks to see the badge with that number, and they don't have your badge.

The matched pass is the one you want, and it's called a certificate-bound token.

---

## 04:15 — Why the door has to see the badge

[SCREEN: two people at a door. Both hold up a badge.]

A matched pass only helps if somebody checks the match.

So at these doors, both sides show a badge. The worker shows theirs, the door shows its own, and then the door compares the pass in the worker's hand against the badge in the worker's other hand. Both showing badges is what mTLS means.

That's why badge settings are part of how the passes work, rather than a detail about doors. The pass has a badge number on it, and the badge has to be visible for anyone to check it.

---

## 05:15 — Two passes for one trip

[SCREEN: a worker walking out with two slips of paper.]

When a worker goes to visit another building, they carry two passes, and they are different documents.

The first is their **own day pass**, from the machine in their own building, with their badge number on it. It says who this worker is.

The second is a **visitor pass made out to one named building**. It says where they are going, and it works at that address and nowhere else.

Each pass is for a different desk. The security desk in their own building reads the first one and asks whether this worker may leave for that destination. The reception desk at the far building reads the second one and asks whether this visitor may come in. Neither desk can answer the other one's question.

---

## 06:15 — A pass you can read, and a pass you have to phone about

The visiting building's reception desk can be handed two kinds of pass.

One kind has to be phoned in. Reception rings head office and asks whether the pass is real, and waits. When six workers arrive at once, the phone line gets busy and somebody gets turned away for no good reason.

The other kind can be read on the spot. It has a stamp reception already knows how to recognise, and it names this specific building, so nobody has to ring anyone.

We use the second kind. That's the difference between an access token and an ID token.

---

## 07:15 — The worker who can't collect that pass

There's a wrinkle. The readable pass is issued to people with a shared STAFF badge, and our workers gave those up when they got personal badges.

So the worker asks a runner to collect it for them. The runner does have that kind of badge, and the worker has written permission to send that runner on errands.

That permission is the token-creator role granted back in Step 2. The runner is the invoker service account.

---

## 08:00 — The desk works both ways

[SCREEN: the security desk, with arrows going in and out through it.]

The security desk watches two directions, and it's one desk.

People coming **in** is ingress. The desk asks which visitors are allowed into the building and whether what they're carrying is safe.

Workers going **out** is egress. The desk asks where this worker is going and whether what they're carrying is safe to take there.

Vibeflix only staffs the outward direction, because nobody from outside visits these workers — the console is in the same building. If you opened your agents up to outside callers, you'd staff the inward direction too.

---

## 09:00 — Three questions on the way out

Every time a worker walks out, the desk asks three things in order.

**Is that building on the list?** The desk keeps a list of buildings that exist and can be visited. A building nobody wrote down can't be visited, and that list is the registry.

**Is this worker allowed at that building?** Being on the list makes a building visitable, and each worker is separately named for the ones they may enter.

**And which room?** The permission says which room in that building this worker may go to. A worker allowed into the library to borrow a book has no permission to enter the room where the records are kept.

That third question is the one plain IAM can't ask. It's the difference between letting a worker into a building and letting them into one room in it.

---

## 10:15 — When somebody gets turned away

If a worker comes back saying they were refused at the desk, one of those three answers was no. The building wasn't on the list, the worker wasn't named for it, or they tried a room they don't have.

Being refused is the desk doing its job. In a building with no desk, the same mistake means the worker walks in and nobody finds out until much later.

There's a second kind of refusal worth telling apart. Turned away at your own desk on the way out is a permission problem. Turned away at the far building's reception is a pass problem — the pass was missing, expired, or made out to the wrong building.

---

## 11:15 — The whole picture

[SCREEN: the full building diagram, labels appearing one at a time.]

Every worker has their own badge, printed by the building, naming them alone.

Their day passes have their badge number on them, so a dropped pass is useless to anyone else.

Doors check badge and pass together, which is why both sides show badges.

Workers carry two passes on a trip, one for their own desk and one for the reception at the far end.

The desk watches both directions and asks three questions before letting anyone out.

And every one of those checks happens on the way, not in a document somebody wrote about how the building should work.

---

## 12:15 — Back to the real names

Badge is the agent identity, written `principal://`, and the certificate that proves it.

Day pass is a token, and a matched day pass is a certificate-bound token.

Both sides showing badges is mTLS.

Your own day pass is the `Proxy-Authorization` header, read by your own desk. The visitor pass made out to one building is the `Authorization` header, read by the far end.

The runner is the invoker service account you impersonate.

The desk is the Agent Gateway, the list is the Agent Registry, the worker's name on a building's list is the egress role, and the room is the per-tool policy.

That's the whole of Step 7. Go and watch the main video, and the code will look like the building.
