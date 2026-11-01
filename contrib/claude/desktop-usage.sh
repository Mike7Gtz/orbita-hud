#!/usr/bin/env bash
# Reads the plan usage that the Claude desktop app samples every 15 min
# (~/.config/Claude/plan-usage-history.json) and writes ~/.claude/usage.json,
# adding reset times and time remaining:
#   - seven_day: optional user-configured schedule; not a server reset timestamp.
#   - five_hour: estimated (±15 min) from when usage rose above 0 % after
#     the previous window ended; window = 5 h.
# Usage: desktop-usage.sh                  -> write once and print a summary
#        desktop-usage.sh --watch [secs]   -> rewrite every secs (default 60)

# Optional local schedule copied from your own usage page. No account-specific default.
WEEKLY_RESET="${CLAUDE_WEEKLY_RESET:-}"

src="$HOME/.config/Claude/plan-usage-history.json"
out="$HOME/.claude/usage.json"

next_weekly_reset() {
  local now t
  [ -n "$WEEKLY_RESET" ] || return 1
  now=$(date +%s)
  t=$(date -d "$WEEKLY_RESET" +%s) || return 1
  [ "$t" -le "$now" ] && t=$((t + 7 * 86400))
  echo "$t"
}

# No new sample: recompute the countdown but preserve the observation timestamp.
keep_last() {
  [ -f "$out" ] || return 1
  local tmp
  tmp=$(mktemp "$out.XXXXXX") || return 1
  if jq --argjson now "$(date +%s)" '
      def refresh: if .resets_at == null then .
        else ([.resets_at - $now, 0] | max) as $r
          | .remaining_seconds = $r
          | .remaining = (if $r >= 86400 then "\($r / 86400 | floor)d \($r % 86400 / 3600 | floor)h"
                          else "\($r / 3600 | floor)h \($r % 3600 / 60 | floor)m" end)
        end;
      .five_hour |= refresh | .seven_day |= refresh
      | .checked_at = $now | .kept_last = true' "$out" >"$tmp"; then
    mv "$tmp" "$out"
  else
    rm -f "$tmp"; return 1
  fi
}

update() {
  build || keep_last || { echo "5h: –  7d: –"; return 1; }
  jq -r '
    def pct(v): if v == null then "–" else "\(v | round)%" end;
    def left(w): if w.remaining == null then "" else " (\(if w.resets_at_estimated then "~" else "" end)\(w.remaining))" end;
    "5h: \(pct(.five_hour.used_percentage))\(left(.five_hour))  7d: \(pct(.seven_day.used_percentage))\(left(.seven_day))"' "$out"
}

build() {
  [ -f "$src" ] || return 1
  local tmp weekly
  weekly=$(next_weekly_reset) || weekly=null
  tmp=$(mktemp "$out.XXXXXX") || return 1
  if jq --argjson now "$(date +%s)" --argjson weekly "$weekly" '
      def remaining($at):
        if $at == null then {remaining_seconds: null, remaining: null}
        else ([$at - $now, 0] | max) as $r
          | {remaining_seconds: $r,
             remaining: (if $r >= 86400 then "\($r / 86400 | floor)d \($r % 86400 / 3600 | floor)h"
                         else "\($r / 3600 | floor)h \($r % 3600 / 60 | floor)m" end)}
        end;

      (.samples[-1].org) as $org
      | [.samples[] | select(.org == $org) | {t: (.t / 1000 | floor), fh: .u.fh, sd: .u.sd}] as $s

      # Walk the history: a 5 h window starts between the last sample with
      # no active window and the first sample where usage is above 0 %.
      | (reduce range(1; $s | length) as $i ({until: null};
          $s[$i - 1] as $p | $s[$i] as $c
          | if .until != null and $c.t < .until and $c.fh < $p.fh then
              .until = (($p.t + $c.t) / 2 | floor)           # reset came earlier than estimated
            else . end
          | if (.until == null or $c.t >= .until) and $c.fh > 0 then
              ([$p.t, (.until // 0), $c.t - 900] | max) as $lo
              | .until = ((($lo + $c.t) / 2 | floor) + 18000)
            else . end
        ) | .until) as $fh_end
      | ($s[-1]) as $last
      | (if $fh_end != null and $fh_end > $now and $last.fh > 0 then $fh_end else null end) as $fh_reset
      | {
          five_hour: ({used_percentage: $last.fh, resets_at: $fh_reset, resets_at_estimated: true}
                      + remaining($fh_reset)),
          seven_day: ({used_percentage: $last.sd, resets_at: $weekly, resets_at_estimated: true}
                      + remaining($weekly)),
          sampled_at: $last.t,
          source: "claude-desktop",
          updated_at: $now
        }' "$src" >"$tmp"; then
    mv "$tmp" "$out"
  else
    rm -f "$tmp"; return 1
  fi
}

if [ "$1" = "--watch" ]; then
  interval=${2:-60}
  while true; do update; sleep "$interval"; done
else
  update
fi
