/*
 * String runtime implementation for pcc.
 */

#include "rt_string.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ==================== Helper Functions ==================== */

/**
 * Ensure string has at least min_cap capacity.
 */
static rt_error_code_t rt_str_reserve(rt_str* s, size_t min_cap) {
    RT_CHECK_NULL(s, "s");

    if (min_cap <= s->cap) {
        return RT_OK;
    }

    /* Double capacity strategy */
    size_t new_cap = s->cap ? s->cap : RT_STR_INITIAL_CAPACITY;
    while (new_cap < min_cap) {
        new_cap *= 2;
    }

    char* new_data = (char*)realloc(s->data, new_cap);
    if (!new_data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate string memory");
        return RT_ERROR_NOMEM;
    }

    s->data = new_data;
    s->cap = new_cap;
    return RT_OK;
}

/* ==================== Lifecycle ==================== */

rt_error_code_t rt_str_init(rt_str* s) {
    RT_CHECK_NULL(s, "s");

    s->len = 0;
    s->cap = 0;
    s->data = NULL;
    return RT_OK;
}

rt_str rt_str_from_cstr(const char* cstr) {
    rt_str s;
    rt_str_init(&s);

    if (!cstr) {
        return s;
    }

    size_t n = strlen(cstr);
    if (n == 0) {
        return s;
    }

    s.data = (char*)malloc(n + 1);
    if (!s.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate string memory");
        return s;
    }

    memcpy(s.data, cstr, n + 1);
    s.len = n;
    s.cap = n + 1;
    return s;
}

void rt_str_clear(rt_str* s) {
    if (!s) return;

    if (s->data) {
        free(s->data);
        s->data = NULL;
    }
    s->len = 0;
    s->cap = 0;
}

/* ==================== Operations ==================== */

rt_str rt_str_concat(rt_str a, rt_str b) {
    rt_str result;
    rt_str_init(&result);

    size_t total_len = a.len + b.len;
    if (total_len == 0) {
        return result;
    }

    result.data = (char*)malloc(total_len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate string memory");
        return result;
    }

    if (a.len > 0 && a.data) {
        memcpy(result.data, a.data, a.len);
    }
    if (b.len > 0 && b.data) {
        memcpy(result.data + a.len, b.data, b.len);
    }
    result.data[total_len] = '\0';
    result.len = total_len;
    result.cap = total_len + 1;

    return result;
}

rt_error_code_t rt_str_append_cstr(rt_str* s, const char* cstr) {
    RT_CHECK_NULL(s, "s");

    if (!cstr || cstr[0] == '\0') {
        return RT_OK;
    }

    size_t cstr_len = strlen(cstr);
    size_t new_len = s->len + cstr_len;

    rt_error_code_t err = rt_str_reserve(s, new_len + 1);
    if (err != RT_OK) {
        return err;
    }

    memcpy(s->data + s->len, cstr, cstr_len + 1);
    s->len = new_len;

    return RT_OK;
}

/* ==================== I/O ==================== */

void rt_print_str(rt_str s) {
    if (s.data && s.len > 0) {
        fwrite(s.data, 1, s.len, stdout);
    }
    fputc('\n', stdout);
}

rt_error_code_t rt_str_fprint(FILE* fp, rt_str s) {
    RT_CHECK_NULL(fp, "fp");

    if (s.data && s.len > 0) {
        size_t written = fwrite(s.data, 1, s.len, fp);
        if (written != s.len) {
            RT_SET_ERROR(RT_ERROR_IO, "Failed to write string to file");
            return RT_ERROR_IO;
        }
    }

    return RT_OK;
}
