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
