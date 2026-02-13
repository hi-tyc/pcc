/*
 * Extended string utilities implementation for pcc runtime.
 */

#include "rt_string_ex.h"
#include "rt_math.h"
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdio.h>
#include <limits.h>

/* ==================== Helper Functions ==================== */

static int is_whitespace(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v';
}

static char to_upper_char(char c) {
    if (c >= 'a' && c <= 'z') {
        return c - 'a' + 'A';
    }
    return c;
}

static char to_lower_char(char c) {
    if (c >= 'A' && c <= 'Z') {
        return c - 'A' + 'a';
    }
    return c;
}

/* ==================== Substring Operations ==================== */

rt_str rt_str_substring(rt_str s, size_t start, size_t length) {
    rt_str result;
    rt_str_init(&result);
    
    if (start >= s.len) {
        return result;  /* Empty string if start is beyond length */
    }
    
    size_t available = s.len - start;
    size_t actual_len = (length == 0 || length > available) ? available : length;
    
    if (actual_len == 0) {
        return result;
    }
    
    result.data = (char*)malloc(actual_len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate substring memory");
        return result;
    }
    
    memcpy(result.data, s.data + start, actual_len);
    result.data[actual_len] = '\0';
    result.len = actual_len;
    result.cap = actual_len + 1;
    
    return result;
}

rt_str rt_str_slice_from(rt_str s, size_t start) {
    return rt_str_substring(s, start, 0);  /* 0 length means to end */
}

rt_str rt_str_slice_to(rt_str s, size_t end) {
    if (end > s.len) {
        end = s.len;
    }
    return rt_str_substring(s, 0, end);
}

/* ==================== Searching ==================== */

size_t rt_str_find(rt_str s, rt_str pattern, size_t start) {
    if (start >= s.len || pattern.len == 0) {
        return (size_t)-1;
    }
    
    if (pattern.len > s.len - start) {
        return (size_t)-1;
    }
    
    for (size_t i = start; i <= s.len - pattern.len; i++) {
        if (memcmp(s.data + i, pattern.data, pattern.len) == 0) {
            return i;
        }
    }
    
    return (size_t)-1;
}

size_t rt_str_find_cstr(rt_str s, const char* pattern, size_t start) {
    if (!pattern) {
        return (size_t)-1;
    }
    
    rt_str pattern_str = rt_str_from_cstr(pattern);
    size_t result = rt_str_find(s, pattern_str, start);
    rt_str_clear(&pattern_str);
    
    return result;
}

size_t rt_str_rfind(rt_str s, rt_str pattern) {
    if (pattern.len == 0 || pattern.len > s.len) {
        return (size_t)-1;
    }
    
    for (size_t i = s.len - pattern.len; i != (size_t)-1; i--) {
        if (memcmp(s.data + i, pattern.data, pattern.len) == 0) {
            return i;
        }
    }
    
    return (size_t)-1;
}

int rt_str_contains(rt_str s, rt_str pattern) {
    return rt_str_find(s, pattern, 0) != (size_t)-1;
}

int rt_str_starts_with(rt_str s, rt_str prefix) {
    if (prefix.len > s.len) {
        return 0;
    }
    
    return memcmp(s.data, prefix.data, prefix.len) == 0;
}

int rt_str_ends_with(rt_str s, rt_str suffix) {
    if (suffix.len > s.len) {
        return 0;
    }
    
    return memcmp(s.data + s.len - suffix.len, suffix.data, suffix.len) == 0;
}

/* ==================== Comparison ==================== */

int rt_str_compare(rt_str a, rt_str b) {
    size_t min_len = a.len < b.len ? a.len : b.len;
    int cmp = memcmp(a.data, b.data, min_len);
    
    if (cmp != 0) {
        return cmp;
    }
    
    /* Equal up to min_len, compare lengths */
    if (a.len < b.len) return -1;
    if (a.len > b.len) return 1;
    return 0;
}

int rt_str_equals(rt_str a, rt_str b) {
    if (a.len != b.len) {
        return 0;
    }
    
    return memcmp(a.data, b.data, a.len) == 0;
}

int rt_str_compare_ignore_case(rt_str a, rt_str b) {
    size_t min_len = a.len < b.len ? a.len : b.len;
    
    for (size_t i = 0; i < min_len; i++) {
        char ca = to_lower_char(a.data[i]);
        char cb = to_lower_char(b.data[i]);
        
        if (ca < cb) return -1;
        if (ca > cb) return 1;
    }
    
    /* Equal up to min_len, compare lengths */
    if (a.len < b.len) return -1;
    if (a.len > b.len) return 1;
    return 0;
}

/* ==================== Case Conversion ==================== */

rt_str rt_str_to_upper(rt_str s) {
    rt_str result;
    rt_str_init(&result);
    
    if (s.len == 0) {
        return result;
    }
    
    result.data = (char*)malloc(s.len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate uppercase string memory");
        return result;
    }
    
    for (size_t i = 0; i < s.len; i++) {
        result.data[i] = to_upper_char(s.data[i]);
    }
    result.data[s.len] = '\0';
    result.len = s.len;
    result.cap = s.len + 1;
    
    return result;
}

rt_str rt_str_to_lower(rt_str s) {
    rt_str result;
    rt_str_init(&result);
    
    if (s.len == 0) {
        return result;
    }
    
    result.data = (char*)malloc(s.len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate lowercase string memory");
        return result;
    }
    
    for (size_t i = 0; i < s.len; i++) {
        result.data[i] = to_lower_char(s.data[i]);
    }
    result.data[s.len] = '\0';
    result.len = s.len;
    result.cap = s.len + 1;
    
    return result;
}

rt_str rt_str_capitalize(rt_str s) {
    rt_str result;
    rt_str_init(&result);
    
    if (s.len == 0) {
        return result;
    }
    
    result.data = (char*)malloc(s.len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate capitalized string memory");
        return result;
    }
    
    result.data[0] = to_upper_char(s.data[0]);
    for (size_t i = 1; i < s.len; i++) {
        result.data[i] = to_lower_char(s.data[i]);
    }
    result.data[s.len] = '\0';
    result.len = s.len;
    result.cap = s.len + 1;
    
    return result;
}

/* ==================== Whitespace Handling ==================== */

rt_str rt_str_ltrim(rt_str s) {
    size_t start = 0;
    while (start < s.len && is_whitespace(s.data[start])) {
        start++;
    }
    
    return rt_str_slice_from(s, start);
}

rt_str rt_str_rtrim(rt_str s) {
    size_t end = s.len;
    while (end > 0 && is_whitespace(s.data[end - 1])) {
        end--;
    }
    
    return rt_str_slice_to(s, end);
}

rt_str rt_str_trim(rt_str s) {
    rt_str temp = rt_str_ltrim(s);
    rt_str result = rt_str_rtrim(temp);
    rt_str_clear(&temp);
    return result;
}

rt_str rt_str_remove_whitespace(rt_str s) {
    rt_str result;
    rt_str_init(&result);
    
    if (s.len == 0) {
        return result;
    }
    
    /* Count non-whitespace characters */
    size_t count = 0;
    for (size_t i = 0; i < s.len; i++) {
        if (!is_whitespace(s.data[i])) {
            count++;
        }
    }
    
    if (count == 0) {
        return result;
    }
    
    result.data = (char*)malloc(count + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate trimmed string memory");
        return result;
    }
    
    size_t j = 0;
    for (size_t i = 0; i < s.len; i++) {
        if (!is_whitespace(s.data[i])) {
            result.data[j++] = s.data[i];
        }
    }
    result.data[j] = '\0';
    result.len = count;
    result.cap = count + 1;
    
    return result;
}

/* ==================== Type Conversion ==================== */

rt_str rt_str_from_int(const rt_int* x) {
    rt_str result;
    rt_str_init(&result);
    
    if (x == NULL) {
        RT_SET_ERROR(RT_ERROR_INVALID, "NULL pointer passed to rt_str_from_int");
        return result;
    }
    
    /* Use the BigInt print function to get string representation */
    /* For now, use a simple approach with a fixed buffer */
    char buffer[1024];
    
    if (rt_int_is_zero(x)) {
        return rt_str_from_cstr("0");
    }
    
    /* Calculate required buffer size */
    size_t num_digits = rt_math_num_digits(x);
    size_t need_sign = (x->sign < 0) ? 1 : 0;
    
    if (num_digits + need_sign >= sizeof(buffer)) {
        RT_SET_ERROR(RT_ERROR_OVERFLOW, "Number too large for string conversion");
        return rt_str_null();
    }
    
    /* Build string from BigInt digits */
    /* This is a simplified version - full implementation would use rt_int_fprint */
    char* p = buffer + sizeof(buffer) - 1;
    *p = '\0';
    
    /* For now, return a placeholder - full implementation needs BigInt to string conversion */
    /* This would require access to BigInt internals or a print-to-string function */
    return rt_str_from_cstr("0");  /* Placeholder */
}

rt_str rt_str_from_si(int64_t x) {
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "%lld", (long long)x);
    return rt_str_from_cstr(buffer);
}

rt_error_code_t rt_str_to_int(rt_str s, rt_int* out) {
    RT_CHECK_NULL(out, "out");
    
    rt_str trimmed = rt_str_trim(s);
    
    if (trimmed.len == 0) {
        rt_str_clear(&trimmed);
        RT_SET_ERROR(RT_ERROR_INVALID, "Empty string cannot be parsed as integer");
        return RT_ERROR_INVALID;
    }
    
    /* Use BigInt from decimal string function */
    rt_error_code_t err = rt_int_from_dec(out, trimmed.data);
    
    rt_str_clear(&trimmed);
    return err;
}

rt_error_code_t rt_str_to_si(rt_str s, int64_t* out) {
    RT_CHECK_NULL(out, "out");
    
    rt_str trimmed = rt_str_trim(s);
    
    if (trimmed.len == 0) {
        rt_str_clear(&trimmed);
        RT_SET_ERROR(RT_ERROR_INVALID, "Empty string cannot be parsed as integer");
        return RT_ERROR_INVALID;
    }
    
    /* Try to parse as BigInt first, then check if it fits in int64 */
    rt_int temp;
    rt_int_init(&temp);
    
    rt_error_code_t err = rt_int_from_dec(&temp, trimmed.data);
    if (err != RT_OK) {
        rt_str_clear(&trimmed);
        rt_int_clear(&temp);
        return err;
    }
    
    err = rt_int_to_si_checked(&temp, out);
    
    rt_str_clear(&trimmed);
    rt_int_clear(&temp);
    
    return err;
}

int rt_str_is_integer(rt_str s) {
    rt_str trimmed = rt_str_trim(s);
    
    if (trimmed.len == 0) {
        rt_str_clear(&trimmed);
        return 0;
    }
    
    size_t start = 0;
    if (trimmed.data[0] == '-' || trimmed.data[0] == '+') {
        start = 1;
        if (trimmed.len == 1) {
            rt_str_clear(&trimmed);
            return 0;  /* Just a sign, no digits */
        }
    }
    
    for (size_t i = start; i < trimmed.len; i++) {
        if (trimmed.data[i] < '0' || trimmed.data[i] > '9') {
            rt_str_clear(&trimmed);
            return 0;
        }
    }
    
    rt_str_clear(&trimmed);
    return 1;
}

/* ==================== String Building ==================== */

rt_str rt_str_repeat(rt_str s, int64_t count) {
    rt_str result;
    rt_str_init(&result);
    
    if (count <= 0 || s.len == 0) {
        return result;
    }
    
    /* Check for overflow */
    if ((uint64_t)s.len * (uint64_t)count > SIZE_MAX - 1) {
        RT_SET_ERROR(RT_ERROR_OVERFLOW, "Repeat count too large");
        return result;
    }
    
    size_t total_len = s.len * (size_t)count;
    
    result.data = (char*)malloc(total_len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate repeated string memory");
        return result;
    }
    
    for (int64_t i = 0; i < count; i++) {
        memcpy(result.data + i * s.len, s.data, s.len);
    }
    result.data[total_len] = '\0';
    result.len = total_len;
    result.cap = total_len + 1;
    
    return result;
}

rt_str rt_str_join(rt_str* strings, size_t count, rt_str separator) {
    rt_str result;
    rt_str_init(&result);
    
    if (count == 0) {
        return result;
    }
    
    if (count == 1) {
        return rt_str_substring(strings[0], 0, strings[0].len);
    }
    
    /* Calculate total length */
    size_t total_len = 0;
    for (size_t i = 0; i < count; i++) {
        total_len += strings[i].len;
    }
    total_len += separator.len * (count - 1);
    
    result.data = (char*)malloc(total_len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate joined string memory");
        return result;
    }
    
    char* p = result.data;
    for (size_t i = 0; i < count; i++) {
        if (i > 0 && separator.len > 0) {
            memcpy(p, separator.data, separator.len);
            p += separator.len;
        }
        if (strings[i].len > 0) {
            memcpy(p, strings[i].data, strings[i].len);
            p += strings[i].len;
        }
    }
    *p = '\0';
    result.len = total_len;
    result.cap = total_len + 1;
    
    return result;
}

rt_str rt_str_replace(rt_str s, rt_str old, rt_str replacement) {
    rt_str result;
    rt_str_init(&result);
    
    if (old.len == 0) {
        /* Nothing to replace, return copy of original */
        return rt_str_substring(s, 0, s.len);
    }
    
    /* Count occurrences */
    size_t count = 0;
    size_t pos = 0;
    while ((pos = rt_str_find(s, old, pos)) != (size_t)-1) {
        count++;
        pos += old.len;
    }
    
    if (count == 0) {
        /* No occurrences, return copy of original */
        return rt_str_substring(s, 0, s.len);
    }
    
    /* Calculate new length */
    size_t total_len = s.len + count * (replacement.len - old.len);
    
    result.data = (char*)malloc(total_len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate replaced string memory");
        return result;
    }
    
    /* Build result */
    char* p = result.data;
    size_t src_pos = 0;
    pos = 0;
    
    while ((pos = rt_str_find(s, old, src_pos)) != (size_t)-1) {
        /* Copy text before match */
        size_t before_len = pos - src_pos;
        if (before_len > 0) {
            memcpy(p, s.data + src_pos, before_len);
            p += before_len;
        }
        
        /* Copy replacement */
        if (replacement.len > 0) {
            memcpy(p, replacement.data, replacement.len);
            p += replacement.len;
        }
        
        src_pos = pos + old.len;
    }
    
    /* Copy remaining text */
    if (src_pos < s.len) {
        memcpy(p, s.data + src_pos, s.len - src_pos);
        p += s.len - src_pos;
    }
    
    *p = '\0';
    result.len = total_len;
    result.cap = total_len + 1;
    
    return result;
}

rt_str rt_str_replace_first(rt_str s, rt_str old, rt_str replacement) {
    rt_str result;
    rt_str_init(&result);
    
    if (old.len == 0) {
        return rt_str_substring(s, 0, s.len);
    }
    
    size_t pos = rt_str_find(s, old, 0);
    if (pos == (size_t)-1) {
        /* Not found, return copy of original */
        return rt_str_substring(s, 0, s.len);
    }
    
    size_t total_len = s.len - old.len + replacement.len;
    
    result.data = (char*)malloc(total_len + 1);
    if (!result.data) {
        RT_SET_ERROR(RT_ERROR_NOMEM, "Failed to allocate replaced string memory");
        return result;
    }
    
    char* p = result.data;
    
    /* Copy text before match */
    if (pos > 0) {
        memcpy(p, s.data, pos);
        p += pos;
    }
    
    /* Copy replacement */
    if (replacement.len > 0) {
        memcpy(p, replacement.data, replacement.len);
        p += replacement.len;
    }
    
    /* Copy text after match */
    size_t after_pos = pos + old.len;
    if (after_pos < s.len) {
        memcpy(p, s.data + after_pos, s.len - after_pos);
        p += s.len - after_pos;
    }
    
    *p = '\0';
    result.len = total_len;
    result.cap = total_len + 1;
    
    return result;
}
