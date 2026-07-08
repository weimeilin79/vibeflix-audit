#!/usr/bin/env bash
# setup_registry.sh — superseded by setup_firestore.sh, which provisions the SAME
# database + registry seed AND the app's audit_history collection. Kept as a
# compatibility wrapper.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_firestore.sh" "$@"
