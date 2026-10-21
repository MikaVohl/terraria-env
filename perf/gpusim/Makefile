# GPU (HIP) build of the simulator core plus benchmarks. By default it compiles
# this checkout's own src/ and include/; SRC/INC select another source tree
# (perf/v7 uses this for the frozen v7 sources) and BUILD the output directory.
# Nothing here edits the core; see REPORT.md.
HIPCC   ?= /opt/rocm/bin/hipcc
ARCH    ?= gfx950
ROOT    := ../..
SRC     ?= $(ROOT)/src
INC     ?= $(ROOT)/include
BUILD   ?= .
CORE    := $(SRC)/sim.c $(SRC)/worldgen.c $(SRC)/light.c $(SRC)/obs.c \
           $(INC)/env.h $(INC)/tiles.h $(INC)/rng.h
# fp-contract=off: no FMA contraction (the CPU build, gcc -O2 without -march,
# emits none); correctly rounded fp32 div/sqrt match IEEE host results.
HIPFLAGS ?= -O3 -std=c++17 --offload-arch=$(ARCH) -ffp-contract=off \
            -fhip-fp32-correctly-rounded-divide-sqrt -I. -I$(SRC) -I$(INC)
HDRS    := gpusim_kernels.h gpusim_core.h glibc_sincosf.h $(CORE)

all: $(BUILD)/gs_main $(BUILD)/gs_main_ocml $(BUILD)/trigtest $(BUILD)/libgpusim.so $(BUILD)/cpu_bench

$(BUILD)/gs_main: gs_main.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) gs_main.hip -o $@.tmp -ldl && mv $@.tmp $@

# Reproduces the 0.02% world mismatch with ROCm's own sinf/cosf.
$(BUILD)/gs_main_ocml: gs_main.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) -DGS_OCML_TRIG gs_main.hip -o $@.tmp -ldl && mv $@.tmp $@

$(BUILD)/libgpusim.so: gs_lib.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) -fPIC -shared gs_lib.hip -o $@.tmp && mv $@.tmp $@

$(BUILD)/trigtest: trigtest.hip glibc_sincosf.h
	$(HIPCC) $(HIPFLAGS) trigtest.hip -o $@

$(BUILD)/cpu_bench: cpu_bench.c $(INC)/env.h
	gcc -O2 -std=c11 -I$(INC) cpu_bench.c -o $@ -ldl -lpthread

resource: gs_main.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) -Rpass-analysis=kernel-resource-usage -c gs_main.hip -o /dev/null 2>&1 \
	  | grep -E "Function Name|ScratchSize|VGPRs:|Occupancy"

clean:
	cd $(BUILD) && rm -f gs_main gs_main_ocml trigtest libgpusim.so cpu_bench *.tmp

.PHONY: all resource clean
