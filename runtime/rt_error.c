/*
 * Error handling implementation for pcc runtime.
 */

#include "rt_error.h"
#include <stdio.h>
#include <string.h>

/* Global error state */
rt_error_t rt_last_error = {
    .code = RT_OK,
    .message = {0},
    .file = NULL,
    .line = 0
};

void rt_error_set(rt_error_code_t code, const char* message, const char* file, int line) {
    rt_last_error.code = code;
    rt_last_error.file = file;
    rt_last_error.line = line;

    if (message != NULL) {
        strncpy(rt_last_error.message, message, RT_ERROR_BUFFER_SIZE - 1);
        rt_last_error.message[RT_ERROR_BUFFER_SIZE - 1] = '\0';
    } else {
        strncpy(rt_last_error.message, rt_error_string(code), RT_ERROR_BUFFER_SIZE - 1);
        rt_last_error.message[RT_ERROR_BUFFER_SIZE - 1] = '\0';
    }
}

void rt_error_clear(void) {
    rt_last_error.code = RT_OK;
    rt_last_error.message[0] = '\0';
    rt_last_error.file = NULL;
    rt_last_error.line = 0;
}

const char* rt_error_string(rt_error_code_t code) {
    switch (code) {
        case RT_OK:
            return "Success";
        case RT_ERROR_NOMEM:
            return "Out of memory";
        case RT_ERROR_DIVZERO:
            return "Division by zero";
        case RT_ERROR_OVERFLOW:
            return "Arithmetic overflow";
        case RT_ERROR_INVALID:
            return "Invalid argument";
        case RT_ERROR_IO:
            return "I/O error";
        case RT_ERROR_UNKNOWN:
        default:
            return "Unknown error";
    }
}

void rt_error_print(void) {
    if (rt_last_error.code != RT_OK) {
        fprintf(stderr, "[pcc runtime error] %s (code %d)\n",
                rt_last_error.message, rt_last_error.code);
        if (rt_last_error.file != NULL) {
            fprintf(stderr, "  at %s:%d\n", rt_last_error.file, rt_last_error.line);
        }
    }
}
