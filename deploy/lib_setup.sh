#!/usr/bin/env bash
#
# lib_setup.sh — helpers shared by the deploy/setup_*.sh scripts.
#
# Sourced, not executed:  . "$(dirname "$0")/lib_setup.sh"

# ensure_created "<what>" <command…>
#
# Runs a create command and keeps its output quiet on success. Every setup
# script is re-runnable, so three different outcomes need three different
# voices — the old `|| echo "(may already exist)"` gave them all the same one,
# letting the provider's raw ERROR text through even when nothing was wrong:
#
#   already there  → say so plainly and continue (the NORMAL second-run case)
#   transient      → retry with backoff; the control plane returns INTERNAL /
#                    UNAVAILABLE often enough that one blip shouldn't cost you
#                    the whole run
#   real failure   → print the provider's error and STOP, with what to do next
#
# Never returns 0 for a resource that doesn't exist — a silently-skipped
# registry entry or database surfaces much later as a confusing 403.
ensure_created() {
  local what="$1"; shift
  local out attempt=1 max="${ENSURE_CREATED_RETRIES:-3}"

  while :; do
    if out=$("$@" 2>&1); then
      echo "  ✓ created $what"
      return 0
    fi

    # HTTP 409 IS "already exists" — but the two calls below never say those words:
    #   gcloud storage buckets create → "HTTPError 409: …you already own it."
    #   curl -f (authz policy)        → "curl: (22) The requested URL returned error: 409"
    # Match the status explicitly (never a bare 409, which appears inside operation ids).
    if printf '%s' "$out" | grep -qiE 'already exist|ALREADY_EXISTS|subject of a conflict|already been created|entity already|already own it|HTTPError 409|error: 409|409 Conflict|status: *409'; then
      echo "  ✓ $what already exists — skipping creation"
      return 0
    fi

    if [ "$attempt" -lt "$max" ] && printf '%s' "$out" \
         | grep -qiE '"code": *(13|14)|INTERNAL|UNAVAILABLE|DEADLINE_EXCEEDED|internal error|Try again|503|500'; then
      local wait=$((attempt * 10))
      echo "  … $what: the API returned a transient error (attempt $attempt of $max) — retrying in ${wait}s"
      sleep "$wait"
      attempt=$((attempt + 1))
      continue
    fi

    echo "  ✗ could not create $what. The API reported:" >&2
    printf '%s\n' "$out" | sed 's/^/      /' >&2
    echo "    Nothing was left half-built — fix the cause above and re-run this same script;" >&2
    echo "    everything already created is detected and skipped." >&2
    return 1
  done
}

# ensure_apis <api…> — enable only the APIs that are not already enabled.
#
# `gcloud services enable` is a MUTATE request even when the API is already on, and
# serviceusage caps mutations at 120 per minute — charged to your ADC QUOTA project, which is
# shared by every project you drive from one shell. Six setup scripts each re-enabling "their"
# APIs (setup.sh enables twenty, then setup_firestore re-enables firestore, setup_pubsub
# re-enables pubsub, deploy_mcp_cloudrun re-enables run+artifactregistry…) is what exhausts
# it. The 429 then lands on whichever script happened to be running when the budget ran out —
# so the error appears in a different place each run and looks unrelated to the real cause.
# gcloud's "This may be due to network connectivity issues" tail sends you to check DNS.
#
# Listing enabled services is a READ, and reads do not count against that quota. So ask first:
# on a re-run this costs ZERO mutations, and on a fresh project it makes exactly one batched
# call for whatever is genuinely missing.
ensure_apis() {
  local missing=() a enabled n=1
  enabled="$(gcloud services list --enabled --project="$PROJECT" --format='value(config.name)' 2>/dev/null)"
  for a in "$@"; do
    printf '%s\n' "$enabled" | grep -qx "$a" || missing+=("$a")
  done
  if [ "${#missing[@]}" -eq 0 ]; then
    echo "  ✓ APIs already enabled ($# checked, 0 changes)"
    return 0
  fi
  echo "  enabling ${#missing[@]} of $# APIs…"
  until gcloud services enable --project="$PROJECT" "${missing[@]}"; do
    if [ "$n" -ge 4 ]; then
      echo "  ✗ could not enable: ${missing[*]}" >&2
      echo "    A 429 here is the 'Mutate requests per minute' quota, not a failure: wait 60s" >&2
      echo "    and re-run. The re-run skips every API that is already on." >&2
      return 1
    fi
    echo "  ! enable failed (attempt $n/4) — waiting $((n * 30))s (limit: 120 mutations/min)"
    sleep $((n * 30)); n=$((n + 1))
  done
  echo "  ✓ enabled ${#missing[@]} API(s)"
}
