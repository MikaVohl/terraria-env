/* Compile the unmodified terraria-lite C core (copied verbatim into core/) as
 * HIP __host__ __device__ code. Nothing in core/ is edited:
 *  - `#pragma clang force_cuda_host_device` makes every function in the core
 *    host+device, so the same source is the CPU and GPU simulator.
 *  - `static const` tables are implicitly promoted to device constants by
 *    clang when referenced from device code.
 *  - Player-facing messages (snprintf into Env.msg) are compiled out of the
 *    device pass only; msg is not part of observations, masks or rewards.
 *  - Device sinf/cosf (worldgen only) are a bit-exact port of the host glibc
 *    FMA build (ROCm's ocml differs in ~1.3% of inputs, which changed 0.02% of
 *    worlds). -DGS_OCML_TRIG restores ocml to reproduce that.
 */
#pragma once
#include <hip/hip_runtime.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "glibc_sincosf.h"
#ifdef __HIP_DEVICE_COMPILE__
#define snprintf(...) 0
#ifndef GS_OCML_TRIG
#define sinf gs_sinf
#define cosf gs_cosf
#endif
#endif
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreorder-init-list"
#pragma clang diagnostic ignored "-Wc99-designator"
#pragma clang force_cuda_host_device begin
#include "sim.c"
#include "worldgen.c"
#include "light.c"
#include "obs.c"
#pragma clang force_cuda_host_device end
#pragma clang diagnostic pop
#ifdef __HIP_DEVICE_COMPILE__
#undef snprintf
#undef sinf
#undef cosf
#endif
