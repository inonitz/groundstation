#!/usr/bin/env bash
# List every installed agent skill: user-level, this repo's, and plugin-provided.
# The plugin cache keeps old versions; sort -u collapses them.
# Not shown: slash commands defined as commands/*.md, and harness built-ins.
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
REPO_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
find "$CLAUDE_DIR/skills" "$REPO_DIR/.claude/skills" "$CLAUDE_DIR/plugins/cache" -name SKILL.md 2>/dev/null \
| sed -E "s|^$CLAUDE_DIR/plugins/cache/[^/]+/([^/]+)/.*/([^/]+)/SKILL\.md|\1: \2|; \
          s|^$CLAUDE_DIR/skills/([^/]+)/SKILL\.md|user: \1|; \
          s|^$REPO_DIR/\.claude/skills/([^/]+)/SKILL\.md|repo: \1|" \
| sort -u
