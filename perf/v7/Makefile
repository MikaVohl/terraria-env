# Build the frozen v7 game (sources read-only under $(V7)) with this branch's
# capi.c (native autoreset, raw/compact batch rows), so the perf trainer paths
# run on v7. Output goes to $(BUILD) (gitignored); nothing under $(V7) is written.
#
#   make -C perf/v7                    # $(BUILD)/libterraria.so (CPU)
#   make -C perf/v7 LIGHT_WINDOW=1     # same, with the observation-window light patch
#   make -C perf/v7 gpu                # $(BUILD)/libgpusim.so, gs_main (HIP, GPU backend)
#   TERRARIA_LITE_LIB=$PWD/perf/v7/build/libterraria.so  selects it for the trainer.
V7      ?= $(HOME)/Projects/RL/builds/v7
LIGHT_WINDOW ?= 0
BUILD   ?= $(if $(filter 1,$(LIGHT_WINDOW)),build-lw,build)
ROOT    := ../..
CFLAGS  := -std=c11 -O2 -g -Wall -Wextra -Wno-unused-const-variable
CORE    := sim.c worldgen.c light.c obs.c
# Variant knobs for sources that define them (variants/v8), e.g.
#   make -C perf/v7 V7=$PWD/variants/v8 LIGHT_WINDOW=1 BUILD=build-v8-ore300 VARIANT="-DORE_PCT=300"
# Use one BUILD directory per VARIANT; the flags are recorded in $(BUILD)/variant.
VARIANT ?=

all: $(BUILD)/libterraria.so

$(BUILD)/stamp: $(addprefix $(V7)/src/,$(CORE)) $(wildcard $(V7)/include/*.h) light_window_v7.patch
	rm -rf $(BUILD)/src $(BUILD)/include && mkdir -p $(BUILD)/src $(BUILD)/include
	cp $(addprefix $(V7)/src/,$(CORE)) $(BUILD)/src/ && cp $(V7)/include/*.h $(BUILD)/include/
	if [ "$(LIGHT_WINDOW)" = 1 ]; then patch -s -d $(BUILD) -p1 < light_window_v7.patch; fi
	printf '%s\n' "$(VARIANT)" > $(BUILD)/variant
	touch $@

$(BUILD)/libterraria.so: $(BUILD)/stamp $(ROOT)/src/capi.c
	gcc $(CFLAGS) $(VARIANT) -I$(BUILD)/include -I$(BUILD)/src -pthread -fPIC -fvisibility=hidden -shared \
	  $(addprefix $(BUILD)/src/,$(CORE)) $(ROOT)/src/capi.c -o $@ -lm

gpu: $(BUILD)/stamp
	$(MAKE) -C ../gpusim SRC=$(abspath $(BUILD)/src) INC=$(abspath $(BUILD)/include) BUILD=$(abspath $(BUILD)) \
	  $(abspath $(BUILD))/libgpusim.so $(abspath $(BUILD))/gs_main

clean:
	rm -rf build build-lw

.PHONY: all gpu clean
