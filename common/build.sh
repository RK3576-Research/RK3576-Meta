#!/bin/sh
# Build a maskrom payload to a flat binary.
#
#   common/build.sh path/to/payload.S   ->  path/to/payload.bin
set -eu
D=$(cd "$(dirname "$0")" && pwd)
for s in "$@"; do
    b="${s%.S}"
    clang --target=aarch64-none-elf -ffreestanding -nostdlib -I"$D" -c -o "$b.o" "$s"
    ld.lld -T "$D/payload.ld" -o "$b.elf" "$b.o"
    llvm-objcopy -O binary "$b.elf" "$b.bin"
    printf '%s  %s\n' "$(sha256sum "$b.bin" | cut -d' ' -f1 | cut -c1-16)" "$b.bin"
done
