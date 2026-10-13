#!/bin/sh
# corsair-workspace teardown (SPEC-0036): remove the volume, then clear its project limits.
set -eu
root=$(dirname "$VOL_DIR")
[ -d "$VOL_DIR" ] || { echo "corsair-workspace teardown: $VOL_DIR absent"; exit 0; }
id=$(xfs_io -c lsproj "$VOL_DIR" | awk '{print $3}')
case "$id" in ''|*[!0-9]*|0) echo "corsair-workspace teardown: no project on $VOL_DIR" >&2; exit 1;; esac
rm -rf "$VOL_DIR"
xfs_quota -x -c "limit -p bhard=0 ihard=0 $id" "$root"
echo "corsair-workspace teardown project=$id dir=$VOL_DIR"
