# Oracle planner for terraria-lite v7. Builds against the vendored, byte-identical
# copy of the frozen v7 game (v7/, see v7/SHA256SUMS); override V7=<dir> to build
# against the original experiment tree instead.
CC     ?= cc
V7     ?= v7
CFLAGS ?= -std=c11 -O2 -g -Wall -Wextra -Wno-unused-const-variable -Wno-unused-function
CORE   := $(V7)/src/sim.c $(V7)/src/worldgen.c $(V7)/src/light.c $(V7)/src/obs.c
LIBEXT := $(if $(filter Darwin,$(shell uname -s)),dylib,so)

all: oracle_v7 lib

oracle_v7: oracle_v7.c $(CORE)
	$(CC) $(CFLAGS) -I$(V7)/include -I$(V7)/src $^ -o $@ -lm

# The normal v7 shared library + python binding, for replay verification.
lib: $(V7)/python/terraria_lite/libterraria.$(LIBEXT)
$(V7)/python/terraria_lite/libterraria.$(LIBEXT): $(CORE) $(V7)/src/capi.c
	$(CC) -std=c11 -O2 -fPIC -shared -I$(V7)/include -I$(V7)/src $^ -o $@ -lm

verify-sources:
	cd $(V7) && shasum -a 256 -c SHA256SUMS

clean:
	rm -f oracle_v7 $(V7)/python/terraria_lite/libterraria.*
.PHONY: all lib clean verify-sources
