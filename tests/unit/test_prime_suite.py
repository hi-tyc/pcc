"""
Comprehensive Prime Number Test Suite with Performance Comparison

This module provides:
1. Multiple prime finding algorithms (naive and optimized)
2. Comprehensive unit tests for correctness verification
3. Performance measurement and comparison capabilities
4. Structured output formatting for results

Test Methodology:
- Correctness tests verify algorithm accuracy across edge cases and various inputs
- Performance tests measure execution time and throughput
- Comparison tests evaluate relative efficiency of different algorithms

Expected Outcomes:
- All algorithms should correctly identify primes with 100% accuracy
- Optimized algorithms (Sieve of Eratosthenes, 6k±1) should outperform naive approaches
- Performance metrics should scale predictably with input size
"""

import pytest
import time
import math
from typing import List, Callable, Dict, Tuple, Union
from dataclasses import dataclass
from functools import wraps


# =============================================================================
# PRIME FINDING ALGORITHMS
# =============================================================================

def is_prime_naive(n: int) -> bool:
    """
    Naive prime checking algorithm.
    
    Checks divisibility from 2 to n-1.
    Time Complexity: O(n)
    Space Complexity: O(1)
    
    Args:
        n: Integer to check for primality
        
    Returns:
        bool: True if n is prime, False otherwise
        
    Raises:
        TypeError: If input is not an integer
        ValueError: If input is less than 0
    """
    # Input validation
    if not isinstance(n, int):
        raise TypeError(f"Input must be an integer, got {type(n).__name__}")
    if n < 0:
        raise ValueError(f"Input must be non-negative, got {n}")
    
    # Edge cases
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    # Check odd divisors up to n-1
    for i in range(3, n, 2):
        if n % i == 0:
            return False
    return True


def is_prime_optimized(n: int) -> bool:
    """
    Optimized prime checking using 6k±1 optimization.
    
    All primes greater than 3 can be written as 6k±1.
    Only checks divisors up to sqrt(n).
    Time Complexity: O(√n)
    Space Complexity: O(1)
    
    Args:
        n: Integer to check for primality
        
    Returns:
        bool: True if n is prime, False otherwise
        
    Raises:
        TypeError: If input is not an integer
        ValueError: If input is less than 0
    """
    # Input validation
    if not isinstance(n, int):
        raise TypeError(f"Input must be an integer, got {type(n).__name__}")
    if n < 0:
        raise ValueError(f"Input must be non-negative, got {n}")
    
    # Edge cases
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    
    # Check divisors of form 6k±1 up to sqrt(n)
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def is_prime_trial_division(n: int) -> bool:
    """
    Trial division with sqrt(n) optimization.
    
    Checks divisibility up to square root of n.
    Time Complexity: O(√n)
    Space Complexity: O(1)
    
    Args:
        n: Integer to check for primality
        
    Returns:
        bool: True if n is prime, False otherwise
        
    Raises:
        TypeError: If input is not an integer
        ValueError: If input is less than 0
    """
    # Input validation
    if not isinstance(n, int):
        raise TypeError(f"Input must be an integer, got {type(n).__name__}")
    if n < 0:
        raise ValueError(f"Input must be non-negative, got {n}")
    
    # Edge cases
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    # Check odd divisors up to sqrt(n)
    sqrt_n = int(math.sqrt(n)) + 1
    for i in range(3, sqrt_n, 2):
        if n % i == 0:
            return False
    return True


def sieve_of_eratosthenes(limit: int) -> List[int]:
    """
    Sieve of Eratosthenes algorithm for finding all primes up to limit.
    
    Efficient for finding all primes in a range.
    Time Complexity: O(n log log n)
    Space Complexity: O(n)
    
    Args:
        limit: Upper bound (inclusive) for finding primes
        
    Returns:
        List[int]: List of all primes up to limit
        
    Raises:
        TypeError: If input is not an integer
        ValueError: If input is less than 0
    """
    # Input validation
    if not isinstance(limit, int):
        raise TypeError(f"Input must be an integer, got {type(limit).__name__}")
    if limit < 0:
        raise ValueError(f"Input must be non-negative, got {limit}")
    
    if limit < 2:
        return []
    
    # Initialize boolean array
    is_prime = [True] * (limit + 1)
    is_prime[0] = is_prime[1] = False
    
    # Sieve algorithm
    for i in range(2, int(math.sqrt(limit)) + 1):
        if is_prime[i]:
            # Mark multiples of i as non-prime
            for j in range(i * i, limit + 1, i):
                is_prime[j] = False
    
    # Collect primes
    return [i for i in range(2, limit + 1) if is_prime[i]]


def find_primes_in_range(start: int, end: int, algorithm: str = "optimized") -> List[int]:
    """
    Find all primes within a specified range.
    
    Args:
        start: Lower bound of range (inclusive)
        end: Upper bound of range (inclusive)
        algorithm: Algorithm to use ("naive", "optimized", "trial", "sieve")
        
    Returns:
        List[int]: List of primes in the range [start, end]
        
    Raises:
        TypeError: If inputs are not integers
        ValueError: If start > end or invalid algorithm
    """
    # Input validation
    if not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("Start and end must be integers")
    if start > end:
        raise ValueError(f"Start ({start}) must be <= end ({end})")
    if start < 0:
        raise ValueError("Start must be non-negative")
    
    # Select algorithm
    algorithms = {
        "naive": is_prime_naive,
        "optimized": is_prime_optimized,
        "trial": is_prime_trial_division,
    }
    
    if algorithm == "sieve":
        # Sieve is more efficient for finding all primes up to end
        all_primes = sieve_of_eratosthenes(end)
        return [p for p in all_primes if p >= start]
    elif algorithm in algorithms:
        is_prime_func = algorithms[algorithm]
        return [n for n in range(max(2, start), end + 1) if is_prime_func(n)]
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}. Choose from: naive, optimized, trial, sieve")


# =============================================================================
# PERFORMANCE MEASUREMENT
# =============================================================================

@dataclass
class PerformanceResult:
    """Data class to store performance measurement results."""
    algorithm_name: str
    execution_time_ms: float
    operations_count: int
    operations_per_second: float
    input_size: int
    
    def __str__(self) -> str:
        return (f"{self.algorithm_name}: {self.execution_time_ms:.4f}ms, "
                f"{self.operations_per_second:,.0f} ops/sec "
                f"(n={self.input_size})")


def measure_performance(
    func: Callable,
    *args,
    iterations: int = 1,
    warmup: int = 0,
    **kwargs
) -> PerformanceResult:
    """
    Measure performance of a function.
    
    Args:
        func: Function to measure
        *args: Positional arguments for the function
        iterations: Number of iterations to run
        warmup: Number of warmup iterations (not counted)
        **kwargs: Keyword arguments for the function
        
    Returns:
        PerformanceResult: Performance metrics
    """
    # Warmup runs
    for _ in range(warmup):
        func(*args, **kwargs)
    
    # Timed runs
    start_time = time.perf_counter()
    for _ in range(iterations):
        result = func(*args, **kwargs)
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_time = total_time / iterations
    
    # Determine input size and operation count
    if args and isinstance(args[0], int):
        input_size = args[0]
        operations_count = iterations
    else:
        input_size = 0
        operations_count = iterations
    
    ops_per_second = operations_count / total_time if total_time > 0 else float('inf')
    
    return PerformanceResult(
        algorithm_name=func.__name__,
        execution_time_ms=avg_time * 1000,
        operations_count=operations_count,
        operations_per_second=ops_per_second,
        input_size=input_size
    )


def compare_algorithms(
    algorithms: Dict[str, Callable],
    test_input: Union[int, Tuple],
    iterations: int = 10
) -> List[PerformanceResult]:
    """
    Compare performance of multiple algorithms.
    
    Args:
        algorithms: Dictionary mapping names to algorithm functions
        test_input: Input to test (int for single value, tuple for range)
        iterations: Number of iterations per algorithm
        
    Returns:
        List[PerformanceResult]: Performance results for each algorithm
    """
    results = []
    
    for name, algo in algorithms.items():
        if isinstance(test_input, tuple):
            # Range input
            result = measure_performance(algo, *test_input, iterations=iterations, warmup=2)
        else:
            # Single value input
            result = measure_performance(algo, test_input, iterations=iterations, warmup=2)
        result.algorithm_name = name
        results.append(result)
    
    # Sort by execution time
    results.sort(key=lambda x: x.execution_time_ms)
    return results


# =============================================================================
# UNIT TESTS
# =============================================================================

class TestPrimeCorrectness:
    """Test cases for prime finding algorithm correctness."""
    
    # Test data: (input, expected_result, description)
    PRIME_TEST_CASES = [
        # Edge cases
        (0, False, "zero is not prime"),
        (1, False, "one is not prime"),
        (2, True, "two is prime (smallest)"),
        
        # Small primes
        (3, True, "three is prime"),
        (5, True, "five is prime"),
        (7, True, "seven is prime"),
        (11, True, "eleven is prime"),
        (13, True, "thirteen is prime"),
        
        # Even numbers (all composite except 2)
        (4, False, "four is composite"),
        (6, False, "six is composite"),
        (8, False, "eight is composite"),
        (10, False, "ten is composite"),
        (100, False, "one hundred is composite"),
        
        # Odd composites
        (9, False, "nine is composite (3*3)"),
        (15, False, "fifteen is composite (3*5)"),
        (21, False, "twenty-one is composite (3*7)"),
        (25, False, "twenty-five is composite (5*5)"),
        (27, False, "twenty-seven is composite (3*9)"),
        
        # Medium primes
        (29, True, "twenty-nine is prime"),
        (31, True, "thirty-one is prime"),
        (37, True, "thirty-seven is prime"),
        (41, True, "forty-one is prime"),
        (43, True, "forty-three is prime"),
        
        # Larger primes
        (97, True, "ninety-seven is prime"),
        (101, True, "one hundred one is prime"),
        (103, True, "one hundred three is prime"),
        (107, True, "one hundred seven is prime"),
        (109, True, "one hundred nine is prime"),
        
        # Perfect squares
        (49, False, "forty-nine is composite (7*7)"),
        (121, False, "one twenty-one is composite (11*11)"),
        
        # Larger composites
        (1000, False, "one thousand is composite"),
        (1001, False, "one thousand one is composite (7*11*13)"),
    ]
    
    @pytest.mark.parametrize("n,expected,description", PRIME_TEST_CASES)
    def test_is_prime_naive(self, n, expected, description):
        """Test naive prime algorithm."""
        result = is_prime_naive(n)
        assert result == expected, f"Failed for {description}: expected {expected}, got {result}"
    
    @pytest.mark.parametrize("n,expected,description", PRIME_TEST_CASES)
    def test_is_prime_optimized(self, n, expected, description):
        """Test optimized prime algorithm."""
        result = is_prime_optimized(n)
        assert result == expected, f"Failed for {description}: expected {expected}, got {result}"
    
    @pytest.mark.parametrize("n,expected,description", PRIME_TEST_CASES)
    def test_is_prime_trial_division(self, n, expected, description):
        """Test trial division algorithm."""
        result = is_prime_trial_division(n)
        assert result == expected, f"Failed for {description}: expected {expected}, got {result}"
    
    def test_algorithms_agree(self):
        """Verify all algorithms produce the same results."""
        test_values = list(range(0, 200)) + [997, 1009, 1013]
        
        for n in test_values:
            naive = is_prime_naive(n)
            optimized = is_prime_optimized(n)
            trial = is_prime_trial_division(n)
            
            assert naive == optimized == trial, \
                f"Algorithms disagree for {n}: naive={naive}, optimized={optimized}, trial={trial}"


class TestSieveOfEratosthenes:
    """Test cases for Sieve of Eratosthenes."""
    
    def test_sieve_small_limit(self):
        """Test sieve with small limit."""
        result = sieve_of_eratosthenes(10)
        expected = [2, 3, 5, 7]
        assert result == expected
    
    def test_sieve_medium_limit(self):
        """Test sieve with medium limit."""
        result = sieve_of_eratosthenes(30)
        expected = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        assert result == expected
    
    def test_sieve_limit_less_than_2(self):
        """Test sieve with limit < 2."""
        assert sieve_of_eratosthenes(0) == []
        assert sieve_of_eratosthenes(1) == []
    
    def test_sieve_matches_individual_checks(self):
        """Verify sieve results match individual prime checks."""
        limit = 100
        sieve_primes = set(sieve_of_eratosthenes(limit))
        
        for n in range(2, limit + 1):
            is_prime = is_prime_optimized(n)
            in_sieve = n in sieve_primes
            assert is_prime == in_sieve, f"Mismatch for {n}"


class TestPrimeRangeFinding:
    """Test cases for finding primes in a range."""
    
    def test_find_primes_in_range_basic(self):
        """Test basic range finding."""
        result = find_primes_in_range(10, 20, algorithm="optimized")
        expected = [11, 13, 17, 19]
        assert result == expected
    
    def test_find_primes_in_range_with_sieve(self):
        """Test range finding with sieve."""
        result = find_primes_in_range(10, 20, algorithm="sieve")
        expected = [11, 13, 17, 19]
        assert result == expected
    
    def test_find_primes_range_starting_at_0(self):
        """Test range starting at 0."""
        result = find_primes_in_range(0, 10, algorithm="optimized")
        expected = [2, 3, 5, 7]
        assert result == expected
    
    def test_find_primes_empty_range(self):
        """Test empty range."""
        result = find_primes_in_range(14, 16, algorithm="optimized")
        assert result == []


class TestInputValidation:
    """Test cases for input validation and error handling."""
    
    def test_negative_input_naive(self):
        """Test negative input handling for naive algorithm."""
        with pytest.raises(ValueError, match="non-negative"):
            is_prime_naive(-5)
    
    def test_negative_input_optimized(self):
        """Test negative input handling for optimized algorithm."""
        with pytest.raises(ValueError, match="non-negative"):
            is_prime_optimized(-5)
    
    def test_non_integer_input(self):
        """Test non-integer input handling."""
        with pytest.raises(TypeError, match="integer"):
            is_prime_naive(3.14)
        with pytest.raises(TypeError, match="integer"):
            is_prime_optimized("17")
    
    def test_invalid_algorithm_name(self):
        """Test invalid algorithm name."""
        with pytest.raises(ValueError, match="Unknown algorithm"):
            find_primes_in_range(1, 10, algorithm="invalid")
    
    def test_invalid_range(self):
        """Test invalid range (start > end)."""
        with pytest.raises(ValueError, match="Start"):
            find_primes_in_range(20, 10)


class TestPerformance:
    """Performance comparison tests."""
    
    def test_performance_small_prime(self):
        """Compare performance on small prime."""
        algorithms = {
            "naive": is_prime_naive,
            "optimized": is_prime_optimized,
            "trial": is_prime_trial_division,
        }
        
        results = compare_algorithms(algorithms, 97, iterations=100)
        
        # All should complete quickly for small inputs
        for result in results:
            assert result.execution_time_ms < 10, f"{result.algorithm_name} too slow"
    
    def test_performance_medium_prime(self):
        """Compare performance on medium prime."""
        algorithms = {
            "optimized": is_prime_optimized,
            "trial": is_prime_trial_division,
        }
        
        results = compare_algorithms(algorithms, 1009, iterations=50)
        
        # Optimized should be faster than trial for medium inputs
        optimized_time = next(r.execution_time_ms for r in results if r.algorithm_name == "optimized")
        trial_time = next(r.execution_time_ms for r in results if r.algorithm_name == "trial")
        
        # Optimized should not be significantly slower
        assert optimized_time <= trial_time * 2, "Optimized algorithm unexpectedly slow"
    
    def test_sieve_performance(self):
        """Test sieve performance for range queries."""
        # Measure time to find all primes up to 10000
        result = measure_performance(sieve_of_eratosthenes, 10000, iterations=10, warmup=2)
        
        # Should complete in reasonable time
        assert result.execution_time_ms < 100, f"Sieve too slow: {result.execution_time_ms}ms"
        
        # Verify correctness
        primes = sieve_of_eratosthenes(10000)
        assert len(primes) == 1229  # There are 1229 primes <= 10000


# =============================================================================
# MAIN EXECUTION - COMPREHENSIVE TEST RUNNER
# =============================================================================

def print_header(title: str):
    """Print formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print formatted subheader."""
    print(f"\n  {title}")
    print("  " + "-" * 66)


def run_comprehensive_tests():
    """
    Run comprehensive tests with performance comparison.
    
    This function provides a standalone test runner that can be executed
    directly to see both correctness verification and performance metrics.
    """
    print_header("PRIME NUMBER TEST SUITE")
    print("\n  Testing prime finding algorithms with performance comparison")
    print("  " + "-" * 66)
    
    # Test 1: Correctness Verification
    print_subheader("1. CORRECTNESS VERIFICATION")
    
    test_cases = [
        (0, False, "zero"),
        (1, False, "one"),
        (2, True, "two (smallest prime)"),
        (17, True, "seventeen (small prime)"),
        (100, False, "one hundred (composite)"),
        (97, True, "ninety-seven (medium prime)"),
        (1009, True, "1009 (larger prime)"),
    ]
    
    algorithms = {
        "Naive": is_prime_naive,
        "Optimized": is_prime_optimized,
        "Trial Division": is_prime_trial_division,
    }
    
    print("\n  Algorithm correctness check:")
    all_correct = True
    for name, algo in algorithms.items():
        correct = 0
        for n, expected, desc in test_cases:
            try:
                result = algo(n)
                if result == expected:
                    correct += 1
            except Exception as e:
                print(f"    {name}: ERROR on {desc}: {e}")
                all_correct = False
        
        status = "✓ PASS" if correct == len(test_cases) else "✗ FAIL"
        print(f"    {name:20s}: {correct}/{len(test_cases)} correct {status}")
        if correct != len(test_cases):
            all_correct = False
    
    # Test 2: Performance Comparison
    print_subheader("2. PERFORMANCE COMPARISON")
    
    # Small input performance
    print("\n  Small input (n=97):")
    small_results = compare_algorithms(algorithms, 97, iterations=1000)
    for result in small_results:
        print(f"    {result}")
    
    # Medium input performance
    print("\n  Medium input (n=1009):")
    medium_algorithms = {k: v for k, v in algorithms.items() if k != "Naive"}
    medium_results = compare_algorithms(medium_algorithms, 1009, iterations=500)
    for result in medium_results:
        print(f"    {result}")
    
    # Large input performance
    print("\n  Large input (n=10007):")
    large_results = compare_algorithms(medium_algorithms, 10007, iterations=100)
    for result in large_results:
        print(f"    {result}")
    
    # Test 3: Range Finding Performance
    print_subheader("3. RANGE FINDING PERFORMANCE")
    
    range_algorithms = {
        "Optimized": lambda s, e: find_primes_in_range(s, e, "optimized"),
        "Sieve": lambda s, e: find_primes_in_range(s, e, "sieve"),
    }
    
    print("\n  Finding primes in range [1, 10000]:")
    range_results = compare_algorithms(range_algorithms, (1, 10000), iterations=10)
    for result in range_results:
        print(f"    {result}")
    
    # Verify sieve found correct number of primes
    sieve_primes = sieve_of_eratosthenes(10000)
    print(f"\n  Sieve found {len(sieve_primes)} primes (expected: 1229)")
    
    # Test 4: Sieve Performance
    print_subheader("4. SIEVE OF ERATOSTHENES PERFORMANCE")
    
    sieve_limits = [1000, 10000, 100000]
    for limit in sieve_limits:
        result = measure_performance(sieve_of_eratosthenes, limit, iterations=10, warmup=3)
        primes_count = len(sieve_of_eratosthenes(limit))
        print(f"    Limit {limit:>6d}: {result.execution_time_ms:>8.4f}ms, "
              f"found {primes_count:>5d} primes")
    
    # Summary
    print_subheader("5. SUMMARY")
    print(f"\n  All correctness tests: {'PASSED' if all_correct else 'FAILED'}")
    print(f"  Fastest single-check algorithm: {medium_results[0].algorithm_name}")
    print(f"  Fastest range algorithm: {range_results[0].algorithm_name}")
    
    print("\n" + "=" * 70)
    print("  Test suite completed")
    print("=" * 70 + "\n")
    
    return all_correct


if __name__ == "__main__":
    # Run the comprehensive test suite
    success = run_comprehensive_tests()
    
    # Optionally run pytest for detailed test output
    print("\n  Running pytest for detailed test output...")
    print("  " + "-" * 66)
    pytest.main([__file__, "-v", "--tb=short"])
