CC      ?= cc
CFLAGS  ?= -std=c11 -O2 -g -Wall -Wextra -Wno-unused-const-variable -Iinclude -Isrc

# Header dependencies, generated as a side effect of compiling. Without these a
# change to include/tiles.h rebuilds nothing whose .c did not also change, and
# because TILE_INFO is a static table in the header, each stale object keeps its
# own outdated copy. Inserting one tile then silently gave light.o a table where
# the new torch id indexed the old lantern row. Costly to debug, trivial to
# prevent.
DEPFLAGS := -MMD -MP
LDFLAGS ?= -lm

BIN      := terraria-lite
SELFTEST := selftest
PXBIN    := terraria-px

# macOS wants .dylib, everyone else .so. The Python binding probes for both.
LIBEXT   := $(if $(filter Darwin,$(shell uname -s)),dylib,so)
LIB      := python/terraria_lite/libterraria.$(LIBEXT)

ALL_SRC  := $(wildcard src/*.c)
PX_SRC   := src/px_main.c src/px_render.c
CAPI_SRC := src/capi.c

# capi.c is the FFI surface and belongs to nothing but the shared library.
GAME_SRC := $(filter-out $(PX_SRC) $(CAPI_SRC),$(ALL_SRC))
CORE_SRC := $(filter-out src/main.c src/render.c,$(GAME_SRC))

GAME_OBJ := $(GAME_SRC:.c=.o)
CORE_OBJ := $(CORE_SRC:.c=.o)
PX_OBJ   := $(PX_SRC:.c=.px.o)
LIB_OBJ  := $(CORE_SRC:.c=.pic.o) $(CAPI_SRC:.c=.pic.o)

# The pixel frontend is opt-in: `all` never needs SDL2, so a machine without it
# still gets the terminal frontend and the selftest.
SDL_CFLAGS := $(shell sdl2-config --cflags 2>/dev/null)
SDL_LIBS   := $(shell sdl2-config --libs 2>/dev/null)

all: $(BIN) $(SELFTEST)

$(BIN): $(GAME_OBJ)
	$(CC) $^ -o $@ $(LDFLAGS)

$(SELFTEST): $(CORE_OBJ) tools/selftest.o
	$(CC) $^ -o $@ $(LDFLAGS)

# Separate object suffix so the frontend's SDL and stb include paths never leak
# into the core translation units.
src/%.px.o: src/%.c
	$(CC) $(CFLAGS) $(DEPFLAGS) -Ithird_party $(SDL_CFLAGS) -c $< -o $@

%.o: %.c
	$(CC) $(CFLAGS) $(DEPFLAGS) -c $< -o $@

ifeq ($(strip $(SDL_LIBS)),)
$(PXBIN):
	@echo "terraria-px: skipped -- sdl2-config was not found on PATH."
	@echo "  install SDL2 (brew install sdl2, apt install libsdl2-dev) and re-run."
	@echo "  '$(BIN)' and '$(SELFTEST)' do not need it and were unaffected."
else
$(PXBIN): $(CORE_OBJ) $(PX_OBJ)
	$(CC) $^ -o $@ $(LDFLAGS) $(SDL_LIBS)
endif

check: $(SELFTEST)
	./$(SELFTEST)

# The shared library the Python binding loads. Built PIC and separate from the
# executables' objects so -fPIC never leaks into them.
lib: $(LIB)

$(LIB): $(LIB_OBJ)
	$(CC) -shared $^ -o $@ $(LDFLAGS)

src/%.pic.o: src/%.c
	$(CC) $(CFLAGS) $(DEPFLAGS) -fPIC -fvisibility=hidden -c $< -o $@

clean:
	rm -f $(GAME_OBJ) $(PX_OBJ) $(LIB_OBJ) tools/selftest.o $(DEPS) \
	      $(BIN) $(SELFTEST) $(PXBIN) $(LIB)

DEPS := $(GAME_OBJ:.o=.d) $(PX_OBJ:.o=.d) $(LIB_OBJ:.o=.d) tools/selftest.d
-include $(DEPS)

.PHONY: all check clean lib
