/*
 * Dict runtime module for pcc (M2).
 *
 * Minimal dict implementation:
 *  - Keys: rt_str
 *  - Values: signed 64-bit integers
 *  - Lookup is linear (good enough for small fixtures)
 */

#pragma once

#include "rt_config.h"
#include "rt_error.h"
#include "rt_string.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>

typedef struct {
    size_t len;
    size_t cap;
    rt_str* keys;
    long long* vals;
} rt_dict_ssi;

rt_error_code_t rt_dict_ssi_init(rt_dict_ssi* d) RT_NONNULL;
void rt_dict_ssi_clear(rt_dict_ssi* d) RT_NONNULL;

rt_error_code_t rt_dict_ssi_set(rt_dict_ssi* d, rt_str key, long long val) RT_NONNULL;
long long rt_dict_ssi_get(const rt_dict_ssi* d, rt_str key) RT_NONNULL;
size_t rt_dict_ssi_len(const rt_dict_ssi* d) RT_NONNULL;

#ifdef __cplusplus
}
#endif
