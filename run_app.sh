#!/bin/bash
# LearnForge AI — Run Script (shim)
# Delegates to start.sh for the full production launch.
exec "$(dirname "${BASH_SOURCE[0]}")/start.sh" "$@"
