# Interactive visualisation (viz/index.html). The simulator is the v8 core with
# default knobs (byte-identical to frozen v7), compiled to WebAssembly with
# LLVM + lld; no Emscripten, no sysroot (wasm/shim is the libc).
#
#   make -C viz            # viz/terraria.wasm
#   make -C viz textures   # viz/textures -> your Terraria install's ExtractedTextures (symlink)
#   make -C viz serve      # http://localhost:8777 (Workers need http, not file://)
#
# Art is Terraria's own, read from a local install through the gitignored
# viz/textures symlink: nothing is copied into the repository, and the page
# cannot be published with textures it does not ship.
#   make -C viz parity     # wasm world/rollout hash == native libterraria hash
#   make -C viz policies   # re-export viz/data/*.bin from checkpoints in $(CKPT)
ifeq ($(shell uname -s),Darwin)
LLVM   ?= /opt/homebrew/opt/llvm/bin
LLD    ?= /opt/homebrew/opt/lld/bin
else
LLVM   ?= $(patsubst %/,%,$(dir $(shell command -v clang)))
LLD    ?= $(or $(patsubst %/,%,$(dir $(shell command -v wasm-ld))),/usr/bin)
endif
CORE   := ../variants/v8
SRC    := $(addprefix $(CORE)/src/,sim.c worldgen.c light.c obs.c) wasm/web.c wasm/policy.c
CFLAGS := --target=wasm32 -std=c11 -O3 -msimd128 -mbulk-memory -ffreestanding -nostdlib \
          -fno-builtin-sinf -fno-builtin-cosf -fno-builtin-logf \
          -Wall -Wextra -Wno-unused-const-variable -Wno-unused-function \
          -Iwasm/shim -I$(CORE)/include
LDFLAGS := -fuse-ld=$(LLD)/wasm-ld -Wl,--no-entry -Wl,--export-dynamic -Wl,--allow-undefined \
           -Wl,--export=__heap_base -Wl,-z,stack-size=1048576 -Wl,--initial-memory=33554432

terraria.wasm: $(SRC) $(wildcard $(CORE)/include/*.h wasm/shim/*.h)
	$(LLVM)/clang $(CFLAGS) $(SRC) $(LDFLAGS) -o $@

TEXTURES ?= $(HOME)/Library/Application Support/Steam/steamapps/common/Terraria/ExtractedTextures
textures:
	@test -f "$(TEXTURES)/Tiles_0.png" || { echo "textures: no Tiles_0.png in $(TEXTURES)"; \
	  echo "textures: pass TEXTURES=<Terraria ExtractedTextures directory>"; exit 1; }
	ln -sfn "$(TEXTURES)" textures

CKPT ?= /tmp/vizck
policies:
	$(MAKE) -C ../perf/v7 V7=$(abspath $(CORE)) BUILD=mac-v8-plain
	cd .. && TERRARIA_LITE_LIB=$$PWD/perf/v7/mac-v8-plain/libterraria.so uv run python tools/viz_export_policy.py $(CKPT) viz/data

parity: terraria.wasm
	$(MAKE) -C ../perf/v7 V7=$(abspath $(CORE)) BUILD=mac-v8-plain
	cd .. && uv run python tools/viz_parity.py

serve: terraria.wasm textures
	python3 -m http.server 8777

.PHONY: textures policies parity serve
