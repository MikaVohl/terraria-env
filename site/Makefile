# Local website for Terraria-Lite (static: HTML, CSS, vanilla JS modules, JSON data).
#
#   make -C site serve     # http://localhost:8778 (builds viz/terraria.wasm and links the textures first)
#   make -C site data      # re-export site/data/{rl,llm}.json and tapes from local experiment artifacts
#
# The interactive parts (live policy, replays, world renders) import the viz modules
# through the committed symlink site/viz -> ../viz, so viz's simulator, policy weights
# and Terraria textures are reused, not copied. Art comes from a local Terraria install
# (viz/textures symlink); pass TEXTURES=<ExtractedTextures dir> if it is not at the
# default Steam path.
PORT     ?= 8778
TEXTURES ?= $(if $(filter Darwin,$(shell uname -s)),$(HOME)/Library/Application Support/Steam/steamapps/common/Terraria/ExtractedTextures,$(HOME)/.local/share/Steam/steamapps/common/Terraria/ExtractedTextures)
UV ?= $(or $(shell command -v uv),$(wildcard $(HOME)/.local/bin/uv),uv)

serve: viz
	@echo "site: http://localhost:$(PORT)"
	python3 tools/serve.py $(PORT)

viz:
	$(MAKE) -C ../viz terraria.wasm
	@test -e ../viz/textures/Tiles_0.png || $(MAKE) -C ../viz textures TEXTURES="$(TEXTURES)"

data:
	cd .. && $(UV) run --no-project --with pandas,numpy python site/tools/export_data.py

.PHONY: serve viz data

official:
	python3 tools/export_terrariabench.py

videos:
	cd .. && $(UV) run --no-project --with numpy python site/tools/fetch_videos.py

.PHONY: official videos
