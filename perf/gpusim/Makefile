# GPU (HIP) build of the repo's own simulator sources (../../src, ../../include)
# plus benchmarks. Nothing here edits the core; see REPORT.md.
HIPCC   ?= /opt/rocm/bin/hipcc
ARCH    ?= gfx950
ROOT    := ../..
CORE    := $(ROOT)/src/sim.c $(ROOT)/src/worldgen.c $(ROOT)/src/light.c $(ROOT)/src/obs.c \
           $(ROOT)/include/env.h $(ROOT)/include/tiles.h $(ROOT)/include/rng.h
# fp-contract=off: no FMA contraction (the CPU build, gcc -O2 without -march,
# emits none); correctly rounded fp32 div/sqrt match IEEE host results.
HIPFLAGS ?= -O3 -std=c++17 --offload-arch=$(ARCH) -ffp-contract=off \
            -fhip-fp32-correctly-rounded-divide-sqrt -I. -I$(ROOT)/src -I$(ROOT)/include
HDRS    := gpusim_kernels.h gpusim_core.h glibc_sincosf.h $(CORE)

all: gs_main gs_main_ocml trigtest libgpusim.so cpu_bench

gs_main: gs_main.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) gs_main.hip -o $@.tmp -ldl && mv $@.tmp $@

# Reproduces the 0.02% world mismatch with ROCm's own sinf/cosf.
gs_main_ocml: gs_main.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) -DGS_OCML_TRIG gs_main.hip -o $@.tmp -ldl && mv $@.tmp $@

libgpusim.so: gs_lib.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) -fPIC -shared gs_lib.hip -o $@.tmp && mv $@.tmp $@

trigtest: trigtest.hip glibc_sincosf.h
	$(HIPCC) $(HIPFLAGS) trigtest.hip -o $@

cpu_bench: cpu_bench.c $(ROOT)/include/env.h
	gcc -O2 -std=c11 -I$(ROOT)/include cpu_bench.c -o $@ -ldl -lpthread

resource: gs_main.hip $(HDRS)
	$(HIPCC) $(HIPFLAGS) -Rpass-analysis=kernel-resource-usage -c gs_main.hip -o /dev/null 2>&1 \
	  | grep -E "Function Name|ScratchSize|VGPRs:|Occupancy"

clean:
	rm -f gs_main gs_main_ocml trigtest libgpusim.so cpu_bench *.tmp

.PHONY: all resource clean
