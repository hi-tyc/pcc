/*
 * List runtime module for pcc (M2).
 *
 * This is a deliberately minimal list implementation to support the PCC
 * roadmap milestone M2.
 *
 * Current restrictions:
 *  - List elements are signed 64-bit integers ("si" = signed integer).
 *  - No slicing.
 *  - Bounds errors raise IndexError when inside a try/except context; otherwise abort.
 */

#pragma once

#include "rt_config.h"
#include "rt_error.h"
#include "rt_exc.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>

typedef struct {
    size_t len;
    size_t cap;
    long long* data;
} rt_list_si;

rt_error_code_t rt_list_si_init(rt_list_si* l) RT_NONNULL;
void rt_list_si_clear(rt_list_si* l) RT_NONNULL;

rt_error_code_t rt_list_si_append(rt_list_si* l, long long v) RT_NONNULL;
size_t rt_list_si_len(const rt_list_si* l) RT_NONNULL;
long long rt_list_si_get(const rt_list_si* l, long long idx) RT_NONNULL;

#ifdef __cplusplus
}
#endif
