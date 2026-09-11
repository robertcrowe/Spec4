# The §60.2 rename check, shell-only. Run from the repo root.
#   P      the pre-rename commit
#   C      the rename commit (leave unset to check the working tree)
#   MAP    a file of "old<TAB>new" lines, one per name in the batch
rename_check() {
  local W; W=$(mktemp -d)
  mkdir "$W/p" "$W/c"
  git archive "$P" | tar -x -C "$W/p"
  if [ -n "${C:-}" ]; then git archive "$C" | tar -x -C "$W/c"
  else git ls-files -co --exclude-standard | tar -cT - | tar -x -C "$W/c"; fi
  for d in "$W/p" "$W/c"; do
    while IFS=$'\t' read -r old new; do          # 1. new -> old, word boundary, both sides
      grep -rlIZw --exclude=CLEANUP_INVENTORY.md -- "$new" "$d" |
        xargs -0r perl -pi -e "s/(?<![A-Za-z0-9_])\Q$new\E(?![A-Za-z0-9_])/$old/g"
    done < "$MAP"
    find "$d" -name '*.py' -print0 |               # 2. fold §54.7's `x as x`
      xargs -0 perl -pi -e 's/\b([A-Za-z_]\w*) as \1\b/$1/g'
    uv run ruff format -q --no-cache \
      --config 'format.skip-magic-trailing-comma = true' "$d"   # 3. layout-blind
  done
  diff -ru --exclude=CLEANUP_INVENTORY.md "$W/p" "$W/c" && echo "rename check: EMPTY"
  local rc=$?; rm -rf "$W"; return $rc
}
