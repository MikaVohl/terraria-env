CC      ?= cc
CFLAGS  ?= -std=c11 -O2 -g -Wall -Wextra -Wno-unused-const-variable -Iinclude
LDFLAGS ?= -lm

BIN      := terraria-lite
SELFTEST := selftest

GAME_SRC := $(wildcard src/*.c)
CORE_SRC := $(filter-out src/main.c src/render.c,$(GAME_SRC))

GAME_OBJ := $(GAME_SRC:.c=.o)
CORE_OBJ := $(CORE_SRC:.c=.o)

all: $(BIN) $(SELFTEST)

$(BIN): $(GAME_OBJ)
	$(CC) $^ -o $@ $(LDFLAGS)

$(SELFTEST): $(CORE_OBJ) tools/selftest.o
	$(CC) $^ -o $@ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

check: $(SELFTEST)
	./$(SELFTEST)

clean:
	rm -f $(GAME_OBJ) tools/selftest.o $(BIN) $(SELFTEST)

.PHONY: all check clean
