# charter-core

The pure evaluation engine for [charter-kit](https://github.com/ianshank/CHARTER.md).

This package performs no I/O. It has no filesystem, network, subprocess, or
clock access; everything it needs from the outside world arrives through the
Protocols in `charter_core.ports`. That is what makes `evaluate()` deterministic
and lets the CLI, the GitHub Action, the MCP server, and the conformance suite
share one engine.

If you are looking for the command-line tool, install `charter-cli`.
