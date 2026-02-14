/*
 * List runtime module for pcc (M2).
 */

#include "rt_list.h"

#include "rt_exc.h"

#include <stdlib.h>
#include <string.h>

static void rt__oom_abort(void) {
    /* Keep behavior consistent with existing runtime: hard abort on OOM. */
    abort();
}

rt_error_code_t rt_list_si_init(rt_list_si* l) {
    if (!l) return RT_ERROR_INVALID;
    l->len = 0;
    l->cap = 0;
    l->data = NULL;
    return RT_OK;
}

void rt_list_si_clear(rt_list_si* l) {
    if (!l) return;
    free(l->data);
    l->data = NULL;
    l->len = 0;
    l->cap = 0;
}

static void rt_list_si_ensure(rt_list_si* l, size_t need) {
    if (l->cap >= need) return;
    size_t newcap = l->cap ? l->cap : 4;
    while (newcap < need) newcap *= 2;
    long long* p = (long long*)realloc(l->data, newcap * sizeof(long long));
    if (!p) rt__oom_abort();
    l->data = p;
    l->cap = newcap;
}

rt_error_code_t rt_list_si_append(rt_list_si* l, long long v) {
    if (!l) return RT_ERROR_INVALID;
    rt_list_si_ensure(l, l->len + 1);
    l->data[l->len++] = v;
    return RT_OK;
}

size_t rt_list_si_len(const rt_list_si* l) {
    return l ? l->len : 0;
}

long long rt_list_si_get(const rt_list_si* l, long long idx) {
    if (!l) {
        RT_RAISE(RT_EXC_TypeError, "list is NULL");
    }
    /* Support negative indices like Python for M2. */
    long long i = idx;
    if (i < 0) i = (long long)l->len + i;
    if (i < 0 || (size_t)i >= l->len) {
        RT_RAISE(RT_EXC_IndexError, "list index out of range");
    }
    return l->data[i];
}
