"""
PCC Compiler Performance Benchmark

Compares compilation performance between:
- Parser V1 (AST-based) vs Parser V2 (tokenize-based)
- Different input sizes and complexities
- Parse time vs total compile time
"""

import pytest
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Callable

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pcc.core import Compiler


@dataclass
class CompileResult:
    """Results from a compilation benchmark."""
    parser_version: int
    test_name: str
    parse_time_ms: float
    total_time_ms: float
    lines_of_code: int
    success: bool
    error_message: str = ""


def measure_compile_time(
    compiler: Compiler,
    source: str,
    iterations: int = 5,
    warmup: int = 2
) -> tuple[float, float, bool]:
    """
    Measure compilation time.
    
    Returns:
        (parse_time_ms, total_time_ms, success)
    """
    # Warmup runs
    for _ in range(warmup):
        try:
            compiler.parse(source)
        except Exception:
            pass
    
    # Measure parse time
    parse_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            ir = compiler.parse(source)
            success = True
        except Exception:
            success = False
        end = time.perf_counter()
        parse_times.append((end - start) * 1000)
    
    avg_parse_time = sum(parse_times) / len(parse_times)
    
    # Measure total compile time (parse + codegen)
    total_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            ir = compiler.parse(source)
            c_source = compiler.generate_c(ir)
            success = True
        except Exception:
            success = False
        end = time.perf_counter()
        total_times.append((end - start) * 1000)
    
    avg_total_time = sum(total_times) / len(total_times)
    
    return avg_parse_time, avg_total_time, success


# Test programs of varying complexity
TEST_PROGRAMS = {
    "tiny": """
x = 1
print(x)
""",
    "small": """
x = 10
y = 20
z = x + y
print(z)
""",
    "medium": """
def add(a, b):
    return a + b

def multiply(a, b):
    result = 0
    i = 0
    while i < b:
        result = add(result, a)
        i = i + 1
    return result

x = multiply(5, 3)
print(x)
""",
    "large": """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

def is_even(n):
    if n == 0:
        return 1
    return is_odd(n - 1)

def is_odd(n):
    if n == 0:
        return 0
    return is_even(n - 1)

result1 = factorial(5)
result2 = fibonacci(10)
result3 = is_even(8)
print(result1)
print(result2)
print(result3)
""",
    "with_class": """
class Counter:
    value = 0
    
    def increment(self):
        self.value = self.value + 1
    
    def get_value(self):
        return self.value

c = Counter()
c.increment()
c.increment()
c.increment()
print(c.get_value())
""",
    "with_loop": """
total = 0
i = 1
while i <= 100:
    total = total + i
    i = i + 1
print(total)

for j in range(10):
    print(j)
""",
}


class TestPCCPerformance:
    """Performance tests for pcc compiler."""
    
    def test_parser_v1_vs_v2_tiny(self):
        """Compare parsers with tiny program."""
        source = TEST_PROGRAMS["tiny"]
        
        compiler_v1 = Compiler(parser_version=1)
        compiler_v2 = Compiler(parser_version=2)
        
        parse_v1, total_v1, success_v1 = measure_compile_time(compiler_v1, source, iterations=10)
        parse_v2, total_v2, success_v2 = measure_compile_time(compiler_v2, source, iterations=10)
        
        assert success_v1, "Parser V1 failed"
        assert success_v2, "Parser V2 failed"
        
        # Both should be fast, V2 might be slightly slower due to tokenization
        # but should be within reasonable bounds
        print(f"\nTiny program ({len(source.splitlines())} lines):")
        print(f"  V1: parse={parse_v1:.4f}ms, total={total_v1:.4f}ms")
        print(f"  V2: parse={parse_v2:.4f}ms, total={total_v2:.4f}ms")
        print(f"  Ratio V2/V1: {parse_v2/parse_v1:.2f}x")
    
    def test_parser_v1_vs_v2_small(self):
        """Compare parsers with small program."""
        source = TEST_PROGRAMS["small"]
        
        compiler_v1 = Compiler(parser_version=1)
        compiler_v2 = Compiler(parser_version=2)
        
        parse_v1, total_v1, success_v1 = measure_compile_time(compiler_v1, source, iterations=10)
        parse_v2, total_v2, success_v2 = measure_compile_time(compiler_v2, source, iterations=10)
        
        assert success_v1 and success_v2
        
        print(f"\nSmall program ({len(source.splitlines())} lines):")
        print(f"  V1: parse={parse_v1:.4f}ms, total={total_v1:.4f}ms")
        print(f"  V2: parse={parse_v2:.4f}ms, total={total_v2:.4f}ms")
        print(f"  Ratio V2/V1: {parse_v2/parse_v1:.2f}x")
    
    def test_parser_v1_vs_v2_medium(self):
        """Compare parsers with medium program."""
        source = TEST_PROGRAMS["medium"]
        
        compiler_v1 = Compiler(parser_version=1)
        compiler_v2 = Compiler(parser_version=2)
        
        parse_v1, total_v1, success_v1 = measure_compile_time(compiler_v1, source, iterations=5)
        parse_v2, total_v2, success_v2 = measure_compile_time(compiler_v2, source, iterations=5)
        
        assert success_v1 and success_v2
        
        print(f"\nMedium program ({len(source.splitlines())} lines):")
        print(f"  V1: parse={parse_v1:.4f}ms, total={total_v1:.4f}ms")
        print(f"  V2: parse={parse_v2:.4f}ms, total={total_v2:.4f}ms")
        print(f"  Ratio V2/V1: {parse_v2/parse_v1:.2f}x")
    
    def test_parser_v1_vs_v2_large(self):
        """Compare parsers with large program."""
        source = TEST_PROGRAMS["large"]
        
        compiler_v1 = Compiler(parser_version=1)
        compiler_v2 = Compiler(parser_version=2)
        
        parse_v1, total_v1, success_v1 = measure_compile_time(compiler_v1, source, iterations=3)
        parse_v2, total_v2, success_v2 = measure_compile_time(compiler_v2, source, iterations=3)
        
        assert success_v1 and success_v2
        
        print(f"\nLarge program ({len(source.splitlines())} lines):")
        print(f"  V1: parse={parse_v1:.4f}ms, total={total_v1:.4f}ms")
        print(f"  V2: parse={parse_v2:.4f}ms, total={total_v2:.4f}ms")
        print(f"  Ratio V2/V1: {parse_v2/parse_v1:.2f}x")
    
    def test_parser_v1_vs_v2_with_class(self):
        """Compare parsers with class definition."""
        source = TEST_PROGRAMS["with_class"]
        
        compiler_v1 = Compiler(parser_version=1)
        compiler_v2 = Compiler(parser_version=2)
        
        parse_v1, total_v1, success_v1 = measure_compile_time(compiler_v1, source, iterations=5)
        parse_v2, total_v2, success_v2 = measure_compile_time(compiler_v2, source, iterations=5)
        
        assert success_v1 and success_v2
        
        print(f"\nProgram with class ({len(source.splitlines())} lines):")
        print(f"  V1: parse={parse_v1:.4f}ms, total={total_v1:.4f}ms")
        print(f"  V2: parse={parse_v2:.4f}ms, total={total_v2:.4f}ms")
        print(f"  Ratio V2/V1: {parse_v2/parse_v1:.2f}x")
    
    def test_parser_v1_vs_v2_with_loop(self):
        """Compare parsers with loops."""
        source = TEST_PROGRAMS["with_loop"]
        
        compiler_v1 = Compiler(parser_version=1)
        compiler_v2 = Compiler(parser_version=2)
        
        parse_v1, total_v1, success_v1 = measure_compile_time(compiler_v1, source, iterations=5)
        parse_v2, total_v2, success_v2 = measure_compile_time(compiler_v2, source, iterations=5)
        
        assert success_v1 and success_v2
        
        print(f"\nProgram with loops ({len(source.splitlines())} lines):")
        print(f"  V1: parse={parse_v1:.4f}ms, total={total_v1:.4f}ms")
        print(f"  V2: parse={parse_v2:.4f}ms, total={total_v2:.4f}ms")
        print(f"  Ratio V2/V1: {parse_v2/parse_v1:.2f}x")


def run_comprehensive_benchmark():
    """Run comprehensive performance benchmark."""
    print("\n" + "=" * 70)
    print("  PCC COMPILER PERFORMANCE BENCHMARK")
    print("  Comparing Parser V1 (AST) vs Parser V2 (Tokenize)")
    print("=" * 70)
    
    results_v1 = []
    results_v2 = []
    
    for name, source in TEST_PROGRAMS.items():
        lines = len(source.strip().split('\n'))
        
        print(f"\n  Test: {name} ({lines} lines)")
        print("  " + "-" * 66)
        
        # V1
        compiler_v1 = Compiler(parser_version=1)
        try:
            parse_v1, total_v1, _ = measure_compile_time(compiler_v1, source, iterations=5)
            results_v1.append((name, lines, parse_v1, total_v1))
            print(f"    V1 (AST):     parse={parse_v1:>8.4f}ms  total={total_v1:>8.4f}ms")
        except Exception as e:
            print(f"    V1 (AST):     ERROR - {e}")
        
        # V2
        compiler_v2 = Compiler(parser_version=2)
        try:
            parse_v2, total_v2, _ = measure_compile_time(compiler_v2, source, iterations=5)
            results_v2.append((name, lines, parse_v2, total_v2))
            print(f"    V2 (Token):   parse={parse_v2:>8.4f}ms  total={total_v2:>8.4f}ms")
        except Exception as e:
            print(f"    V2 (Token):   ERROR - {e}")
        
        # Comparison
        if len(results_v1) > 0 and len(results_v2) > 0:
            ratio = results_v2[-1][2] / results_v1[-1][2] if results_v1[-1][2] > 0 else 0
            faster = "V1" if ratio > 1 else "V2"
            print(f"    Winner: {faster} ({ratio:.2f}x ratio)")
    
    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    
    if results_v1 and results_v2:
        avg_ratio = sum(r2[2] for r2 in results_v2) / sum(r1[2] for r1 in results_v1)
        print(f"\n  Average parse time ratio (V2/V1): {avg_ratio:.2f}x")
        print(f"  Overall winner: {'V1 (AST)' if avg_ratio > 1 else 'V2 (Tokenize)'}")
    
    print("\n" + "=" * 70)
    print("  Benchmark completed")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_comprehensive_benchmark()
    print("\n  Running pytest...")
    pytest.main([__file__, "-v", "-s"])
