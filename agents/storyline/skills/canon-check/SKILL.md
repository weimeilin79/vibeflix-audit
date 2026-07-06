---
name: canon-check
description: >-
  Validate a prototype design concept against the franchise script/canon database
  and spoiler embargoes via query_script_canon, and report as a StorylineReport.
allowed-tools: query_script_canon
metadata:
  version: "1.0.0"
  domain: storyline
  # ADK surfaces these tools to the model once this skill is activated.
  adk_additional_tools:
    - query_script_canon
---

# Franchise Storyline & Lore Compliance

Call `query_script_canon` with `character_id='grogu'` and `design_concept='Grogu in
hover-pram'` to check the concept against the script/canon database.

Respond by filling the StorylineReport schema: set `status` to 'compliant' when the
concept is canon-consistent AND the spoiler embargo is cleared, otherwise
'unverified'. Copy `canon_consistent`, `spoiler_embargo_cleared`, and `message`
from the tool result. Output the schema only — never prose.
