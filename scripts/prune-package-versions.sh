#!/usr/bin/env bash
# Delete GHCR container versions that no longer carry a declared release tag.
#
# GHCR keeps every pushed version forever, so PR-validation candidates, access
# probes, and superseded release lines accumulate until they bury the current
# tags on the package page. This is the owner-run cleanup for that; it is
# deliberately not wired into a workflow, because deleting a published version
# is irreversible.
#
# The keep set is the release catalog rather than a naming pattern. Promotion
# re-tags the validated candidate instead of rebuilding it, so a release and the
# candidate it came from are one manifest and therefore one package version
# carrying both tags -- deleting anything that merely looks like a candidate
# would take the release image with it. Keeping every version that still carries
# a declared tag is the rule that survives that.
#
# Untagged versions are never touched: buildx provenance and SBOM attestations
# are untagged children of the release index, and deleting them breaks the
# release they belong to.
#
# Usage:
#   scripts/prune-package-versions.sh                      # dry run, this repo's catalog
#   scripts/prune-package-versions.sh --delete             # actually delete, with a prompt
#   scripts/prune-package-versions.sh --delete --yes       # no prompt
#   scripts/prune-package-versions.sh --catalog <file>     # e.g. a cookbook matrix
#   scripts/prune-package-versions.sh --package <name>     # limit to one package, repeatable
#
# Requires the gh CLI authenticated with read:packages and delete:packages:
#   gh auth refresh -h github.com -s read:packages,delete:packages
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
owner="LabPod"
catalog="$repo_root/.github/image-matrix.json"
delete=false
assume_yes=false
declare -a only_packages=()

die() {
	printf 'error: %s\n' "$1" >&2
	exit 1
}

while (($# > 0)); do
	case "$1" in
	--owner)
		[[ $# -ge 2 ]] || die "--owner needs a value"
		owner="$2"
		shift 2
		;;
	--catalog)
		[[ $# -ge 2 ]] || die "--catalog needs a value"
		catalog="$2"
		shift 2
		;;
	--package)
		[[ $# -ge 2 ]] || die "--package needs a value"
		only_packages+=("$2")
		shift 2
		;;
	--delete)
		delete=true
		shift
		;;
	--yes)
		assume_yes=true
		shift
		;;
	-h | --help)
		sed -n '2,29p' "${BASH_SOURCE[0]}" | sed 's|^# \{0,1\}||'
		exit 0
		;;
	*)
		die "unknown argument: $1"
		;;
	esac
done

command -v gh >/dev/null || die "gh CLI not found"
command -v jq >/dev/null || die "jq not found"
[[ -f "$catalog" ]] || die "catalog not found: $catalog"

# Both catalog shapes reduce to <package> <tag> pairs: this repo declares
# name/tag, the cookbook declares a full published ref per variant.
declared="$(jq -r '
	.variants[]
	| if has("name") and has("tag") then "\(.name)\t\(.tag)"
	  else (.ref | sub("^[^/]+/[^/]+/"; "") | split(":") | "\(.[0])\t\(.[1])")
	  end
' "$catalog" | sort -u)"
[[ -n "$declared" ]] || die "no release tags found in $catalog"

packages="$(cut -f1 <<<"$declared" | sort -u)"
if ((${#only_packages[@]} > 0)); then
	packages="$(printf '%s\n' "${only_packages[@]}" | sort -u)"
fi

total_delete=0
total_keep=0
plan="$(mktemp)"
trap 'rm -f "$plan"' EXIT

while read -r package; do
	[[ -n "$package" ]] || continue
	keep="$(awk -F'\t' -v p="$package" '$1 == p {print $2}' <<<"$declared" | jq -R . | jq -sc .)"
	# An empty keep set would mark every tagged version for deletion. That only
	# happens when the catalog does not describe this package, which is a
	# mistake, not an instruction to empty the package.
	[[ "$keep" != "[]" ]] || die "no declared tags for package '$package'; refusing to prune it"

	if ! versions="$(gh api --paginate \
		"/orgs/$owner/packages/container/$package/versions" \
		--jq '.[] | {id, tags: (.metadata.container.tags // [])}' 2>/dev/null)"; then
		printf '%-32s skipped (no such package, or missing read:packages)\n' "$package"
		continue
	fi

	doomed="$(jq -r --argjson keep "$keep" '
		select((.tags | length) > 0)
		| select(([.tags[] | select(IN($keep[]))] | length) == 0)
		| "\(.id)\t\(.tags | join(","))"' <<<"$versions")"
	kept="$(jq -r 'select((.tags | length) > 0) | .id' <<<"$versions" | wc -l)"
	count="$(grep -c . <<<"$doomed" || true)"
	total_delete=$((total_delete + count))
	total_keep=$((total_keep + kept - count))

	printf '%-32s keep %s  delete %s\n' "$package" "$((kept - count))" "$count"
	while IFS=$'\t' read -r id tags; do
		[[ -n "$id" ]] || continue
		printf '    %s  %s\n' "$id" "$tags"
		printf '%s\t%s\n' "$package" "$id" >>"$plan"
	done <<<"$doomed"
done <<<"$packages"

printf '\n%s tagged versions kept, %s to delete\n' "$total_keep" "$total_delete"

if [[ "$delete" != true ]]; then
	printf 'dry run; re-run with --delete to apply\n'
	exit 0
fi
if ((total_delete == 0)); then
	exit 0
fi
if [[ "$assume_yes" != true ]]; then
	read -r -p "Permanently delete these $total_delete versions? [y/N] " reply
	[[ "$reply" == [yY] ]] || die "aborted"
fi

while IFS=$'\t' read -r package id; do
	[[ -n "$id" ]] || continue
	printf 'deleting %s %s\n' "$package" "$id"
	gh api --method DELETE "/orgs/$owner/packages/container/$package/versions/$id"
done <"$plan"
