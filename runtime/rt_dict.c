/*
 * Dict runtime module for pcc (M2).
 */

#include "rt_dict.h"

#include "rt_exc.h"

#include <stdlib.h>
#include <string.h>

static void rt__oom_abort(void) {
    abort();
}

static int rt__str_eq(rt_str a, rt_str b) {
    if (a.len != b.len) return 0;
    if (a.len == 0) return 1;
    if (!a.data || !b.data) return 0;
    return memcmp(a.data, b.data, a.len) == 0;
}

rt_error_code_t rt_dict_ssi_init(rt_dict_ssi* d) {
    if (!d) return RT_ERROR_INVALID;
    d->len = 0;
    d->cap = 0;
    d->keys = NULL;
    d->vals = NULL;
    return RT_OK;
}

void rt_dict_ssi_clear(rt_dict_ssi* d) {
    if (!d) return;
    if (d->keys) {
        for (size_t i = 0; i < d->len; i++) {
            rt_str_clear(&d->keys[i]);
        }
    }
    free(d->keys);
    free(d->vals);
    d->keys = NULL;
    d->vals = NULL;
    d->len = 0;
    d->cap = 0;
}

static void rt_dict_ssi_ensure(rt_dict_ssi* d, size_t need) {
    if (d->cap >= need) return;
    size_t newcap = d->cap ? d->cap : 4;
    while (newcap < need) newcap *= 2;
    rt_str* nk = (rt_str*)realloc(d->keys, newcap * sizeof(rt_str));
    if (!nk) rt__oom_abort();
    long long* nv = (long long*)realloc(d->vals, newcap * sizeof(long long));
    if (!nv) rt__oom_abort();
    d->keys = nk;
    d->vals = nv;
    d->cap = newcap;
}

rt_error_code_t rt_dict_ssi_set(rt_dict_ssi* d, rt_str key, long long val) {
    if (!d) return RT_ERROR_INVALID;
    /* Update existing */
    for (size_t i = 0; i < d->len; i++) {
        if (rt__str_eq(d->keys[i], key)) {
            d->vals[i] = val;
            return RT_OK;
        }
    }
    rt_dict_ssi_ensure(d, d->len + 1);
    /* Copy key (deep copy) */
    rt_str k2 = rt_str_from_cstr(key.data ? key.data : "");
    d->keys[d->len] = k2;
    d->vals[d->len] = val;
    d->len++;
    return RT_OK;
}

long long rt_dict_ssi_get(const rt_dict_ssi* d, rt_str key) {
    if (!d) {
        RT_RAISE(RT_EXC_TypeError, "dict is NULL");
    }
    for (size_t i = 0; i < d->len; i++) {
        if (rt__str_eq(d->keys[i], key)) {
            return d->vals[i];
        }
    }
    RT_RAISE(RT_EXC_KeyError, "key not found");
}

size_t rt_dict_ssi_len(const rt_dict_ssi* d) {
    return d ? d->len : 0;
}
