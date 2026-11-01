#!/usr/bin/env bash
# Status line for Claude Code: saves rate limits to ~/.claude/usage.json
# and prints "5h: N%  7d: N%".

input=$(cat)
out="$HOME/.claude/usage.json"
umask 077

if printf '%s' "$input" | jq -e '.rate_limits != null' >/dev/null 2>&1; then
  tmp=$(mktemp "$out.XXXXXX") &&
    printf '%s' "$input" | jq --argjson now "$(date +%s)" '.rate_limits + {updated_at: $now}' >"$tmp" &&
    mv "$tmp" "$out" || rm -f "$tmp"
fi

printf '%s' "$input" | jq -r '
  def pct(v): if v == null then "–" else "\(v | round)%" end;
  "5h: \(pct(.rate_limits.five_hour.used_percentage))  7d: \(pct(.rate_limits.seven_day.used_percentage))"
' 2>/dev/null || echo "5h: –  7d: –"
