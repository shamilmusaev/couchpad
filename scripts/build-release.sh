#!/usr/bin/env bash
# Build dist/couchpad-<version>.tar.gz (+ .sha256) from the git tree.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' couchpad/__init__.py)
NAME="couchpad-$VERSION"
mkdir -p dist
git archive --format=tar --prefix="$NAME/" HEAD \
    couchpad system tests install.sh README.md LICENSE THIRD_PARTY.md CHANGELOG.md \
    | gzip -9 > "dist/$NAME.tar.gz"
(cd dist && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
echo "dist/$NAME.tar.gz"
