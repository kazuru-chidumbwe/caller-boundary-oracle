# gmrtd pins measured by the harness. Source from bootstrap / verify / evaluate scripts.
# 8fea245 = v0.45.0 (records a PACE error and continues to BAC)
# 64bd6ab = v1.1.3  (fails closed on a PACE error unless the caller opts in)
# b861835 = v1.3.2  (current release when measured)
GMRTD_PINS=(
  8fea245048d3b4e76483d048b202ff7f5269728c
  64bd6ab8fbf8802c718a6da0dcc6f6312a3404ca
  b861835cb0c5937b8ec4c77a0e00326974f033f2
)
GMRTD_REPO_URL="${GMRTD_REPO_URL:-https://github.com/gmrtd/gmrtd.git}"

# gmrtd_dir <full-commit> prints the worktree for that pin (matches go.mod / gomod/*.mod).
gmrtd_dir() {
  echo "$VENDOR_DIR/gmrtd-${1:0:7}"
}
