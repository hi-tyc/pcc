/*
 * Exception handling runtime module for pcc (M3).
 */

#include "rt_exc.h"

#include <stdio.h>
#include <stdlib.h>

static rt_try_ctx* g_try_top = NULL;
static rt_exc_t g_exc = { RT_EXC_Exception, NULL, NULL, 0 };

void rt_try_push(rt_try_ctx* ctx) {
    if (!ctx) return;
    ctx->prev = g_try_top;
    g_try_top = ctx;;
}

void rt_try_pop(rt_try_ctx* ctx) {
    if (!ctx) return;
    if (g_try_top == ctx) {
        g_try_top = ctx->prev;
    } else {
        /* Stack mismatch; treat as fatal programming error. */
        fprintf(stderr, "pcc runtime: try stack mismatch\n");
        abort();
    }
}

static void rt__print_unhandled(void) {
    const char* name = rt_exc_name(g_exc.type);
    const char* msg = g_exc.message ? g_exc.message : "";
    if (g_exc.file) {
        fprintf(stderr, "%s: %s (%s:%d)\n", name, msg, g_exc.file, g_exc.line);
    } else {
        fprintf(stderr, "%s: %s\n", name, msg);
    }
}

void rt_raise(rt_exc_type_t type, const char* message, const char* file, int line) {
    g_exc.type = type;
    g_exc.message = message;
    g_exc.file = file;
    g_exc.line = line;

    if (g_try_top) {
        longjmp(g_try_top->env, 1);
    }

    rt__print_unhandled();
    exit(1);
}

void rt_reraise(void) {
    if (g_try_top) {
        longjmp(g_try_top->env, 1);
    }
    rt__print_unhandled();
    exit(1);
}

const rt_exc_t* rt_exc_current(void) {
    return &g_exc;
}

void rt_exc_clear(void) {
    g_exc.type = RT_EXC_Exception;
    g_exc.message = NULL;
    g_exc.file = NULL;
    g_exc.line = 0;
}

const char* rt_exc_name(rt_exc_type_t type) {
    switch (type) {
        case RT_EXC_ZeroDivisionError: return "ZeroDivisionError";
        case RT_EXC_IndexError: return "IndexError";
        case RT_EXC_KeyError: return "KeyError";
        case RT_EXC_TypeError: return "TypeError";
        case RT_EXC_ValueError: return "ValueError";
        case RT_EXC_Exception:
        default: return "Exception";
    }
}

int rt_exc_is(rt_exc_type_t type) {
    return g_exc.type == type;
}
