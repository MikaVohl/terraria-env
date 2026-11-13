/* Freestanding libc subset for the wasm32 build (no sysroot). Only what the
   v8 core and web.c call. sinf/cosf/logf come from the JS host (Math.* rounded
   to float); parity with native builds is checked by tools/viz_parity.mjs. */
#ifndef VIZ_SHIM_H
#define VIZ_SHIM_H
#include <stddef.h>
#include <stdarg.h>
#define WASM_IMPORT(n) __attribute__((import_module("env"), import_name(n)))
void *memcpy(void *restrict d, const void *restrict s, size_t n);
void *memset(void *d, int c, size_t n);
void *memmove(void *d, const void *s, size_t n);
size_t strlen(const char *s);
int vsnprintf(char *restrict out, size_t n, const char *restrict fmt, va_list ap);
int snprintf(char *restrict out, size_t n, const char *restrict fmt, ...);
WASM_IMPORT("sinf") float sinf(float);
WASM_IMPORT("cosf") float cosf(float);
WASM_IMPORT("logf") float logf(float);
static inline float sqrtf(float x) { return __builtin_sqrtf(x); }
static inline float floorf(float x) { return __builtin_floorf(x); }
static inline float fabsf(float x) { return __builtin_fabsf(x); }
static inline int abs(int x) { return x < 0 ? -x : x; }
void *malloc(size_t n);
void free(void *p);
void *calloc(size_t n, size_t m);
#endif
