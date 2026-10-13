#!/bin/sh
# corsair-workspace setup (SPEC-0036): one XFS project per volume with hard byte and inode limits.
# Fails closed: no volume is created unless both limits are set and read back.
set -eu
MAX_BYTES=17179869184
BYTES_PER_INODE=16384
root=$(dirname "$VOL_DIR")
refuse() { echo "corsair-workspace refused: $*" >&2; [ "${created:-0}" = 1 ] && rm -rf "$VOL_DIR"; exit 1; }
[ "$VOL_MODE" = Filesystem ] || refuse "volume mode $VOL_MODE"
case "$VOL_SIZE_BYTES" in ''|*[!0-9]*) refuse "size '$VOL_SIZE_BYTES'";; esac
[ "$VOL_SIZE_BYTES" -ge 1048576 ] && [ "$VOL_SIZE_BYTES" -le "$MAX_BYTES" ] || refuse "size $VOL_SIZE_BYTES outside bounds"
[ "$(stat -f -c %T "$root")" = xfs ] || refuse "$root is not xfs"
xfs_quota -x -c state "$root" | awk '/^Project quota state/{p=1;next} /quota state/{p=0} p&&/Accounting: ON/{a=1} p&&/Enforcement: ON/{e=1} END{exit !(a&&e)}' \
  || refuse "project quota accounting and enforcement are not both on for $root"
kib=$((VOL_SIZE_BYTES / 1024))
inodes=$((VOL_SIZE_BYTES / BYTES_PER_INODE))
exec 9>"$root/.corsair-projid.lock"
flock 9
id=$(($(cat "$root/.corsair-projid" 2>/dev/null || echo 1000) + 1))
echo "$id" > "$root/.corsair-projid"
mkdir -m 0777 "$VOL_DIR" || refuse "$VOL_DIR exists or cannot be created"
created=1
xfs_quota -x -c "project -s -p $VOL_DIR $id" "$root" >/dev/null || refuse "project $id not set"
xfs_quota -x -c "limit -p bhard=${kib}k ihard=$inodes $id" "$root" || refuse "limits for project $id not set"
[ "$(xfs_io -c lsproj "$VOL_DIR" | awk '{print $3}')" = "$id" ] || refuse "project id not read back"
[ "$(xfs_quota -x -c 'report -p -b -n -N' "$root" | awk -v id="#$id" '$1==id{print $4}')" = "$kib" ] || refuse "byte limit not read back"
[ "$(xfs_quota -x -c 'report -p -i -n -N' "$root" | awk -v id="#$id" '$1==id{print $4}')" = "$inodes" ] || refuse "inode limit not read back"
echo "corsair-workspace project=$id bhard_kib=$kib ihard=$inodes dir=$VOL_DIR"
