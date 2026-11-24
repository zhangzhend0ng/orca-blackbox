# Independent check (shares no code with facts.py or the repository): count extruding moves
# (G0/G1 with E > 0 and an X or Y word) by ";TYPE:" section and modal F, before the config block.
# usage: awk -f _verify_awk.awk <file.gcode>
BEGIN { type = "(none)"; f = ""; layer = 0 }
{
  sub(/\r$/, "")
  if ($0 ~ /^;LAYER_CHANGE/) { layer++; next }
  if ($0 ~ /^;TYPE:/) { type = substr($0, 7); next }
  if ($0 ~ /^; CONFIG_BLOCK_START/) { exit }
  if ($0 !~ /^G[01] /) { next }
  e = 0; hasE = 0; xy = 0
  n = split($0, w, " ")
  for (i = 2; i <= n; i++) {
    c = substr(w[i], 1, 1)
    if (c == "F") f = substr(w[i], 2) + 0
    if (c == "E") { e = substr(w[i], 2) + 0; hasE = 1 }
    if (c == "X" || c == "Y") xy = 1
  }
  if (hasE && e > 0 && xy) {
    cnt[type SUBSEP f]++
    any[f]++
    if (layer > 1 && type == "Outer wall" && f + 0 > maxow) maxow = f + 0
    if (layer > 1 && type == "Outer wall") ow++
  }
}
END {
  for (k in cnt) { split(k, p, SUBSEP); printf "TYPE %-24s F %-12g moves %d\n", p[1], p[2], cnt[k] | "sort" }
  close("sort")
  for (v in any) printf "ANY F %-12g moves %d\n", v, any[v] | "sort -t f -k3 -n"
  close("sort -t f -k3 -n")
  printf "OUTER-WALL after first layer: moves %d, max F %g (= %.4f mm/s)\n", ow, maxow, maxow / 60
}
