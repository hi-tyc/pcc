/*
 * Runtime configuration header for pcc.
 *
 * This header provides platform detection and configuration macros
 * for cross-platform compatibility.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Platform detection */
#if defined(_WIN32) || defined(_WIN64)
    #define RT_PLATFORM_WINDOWS 1
#elif defined(__APPLE__)
    #define RT_PLATFORM_MACOS 1
#elif defined(__linux__)
    #define RT_PLATFORM_LINUX 1
#else
    #define RT_PLATFORM_UNKNOWN 1
#endif

/* Compiler detection */
#if defined(_MSC_VER)
    #define RT_COMPILER_MSVC 1
#elif defined(__clang__)
    #define RT_COMPILER_CLANG 1
#elif defined(__GNUC__)
    #define RT_COMPILER_GCC 1
#endif

/* Attribute macros for better code safety */
#if defined(RT_COMPILER_MSVC)
    #define RT_NONNULL
    #define RT_MALLOC
    #define RT_INLINE __inline
#elif defined(RT_COMPILER_GCC) || defined(RT_COMPILER_CLANG)
    #define RT_NONNULL __attribute__((nonnull))
    #define RT_MALLOC __attribute__((malloc))
    #define RT_INLINE inline
#else
    #define RT_NONNULL
    #define RT_MALLOC
    #define RT_INLINE inline
#endif

/* Error handling configuration */
#define RT_ERROR_BUFFER_SIZE 256

/* BigInt configuration */
#define RT_INT_BASE 1000000000u  /* 1e9 */
#define RT_INT_BASE_DIGITS 9
#define RT_INT_INITIAL_CAPACITY 4

/* String configuration */
#define RT_STR_INITIAL_CAPACITY 16

#ifdef __cplusplus
}
#endif
