"""
PCC Runtime Performance Measurement System

Comprehensive performance comparison between:
- Pre-compilation: Python interpreted execution
- Post-compilation: Compiled executable execution

Measures:
- Execution time (wall clock and CPU time)
- Memory usage (peak and average)
- CPU utilization percentage
- Statistical analysis across multiple iterations

Usage:
    python test_runtime_performance.py
    python -m pytest test_runtime_performance.py -v
"""

import pytest
import sys
import time
import subprocess
import statistics
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pcc.core import Compiler


@dataclass
class RuntimeMetrics:
    """Runtime performance metrics for a single execution."""
    execution_time_ms: float
    user_time_ms: float
    system_time_ms: float
    peak_memory_mb: float
    avg_memory_mb: float
    cpu_percent: float
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class BenchmarkResult:
    """Aggregated benchmark results across multiple iterations."""
    test_name: str
    execution_type: str  # "python" or "compiled"
    iterations: int
    
    # Time metrics (ms)
    exec_time_mean: float
    exec_time_median: float
    exec_time_min: float
    exec_time_max: float
    exec_time_std: float
    
    # CPU time metrics (ms)
    user_time_mean: float
    system_time_mean: float
    
    # Memory metrics (MB)
    peak_memory_mean: float
    peak_memory_max: float
    
    # CPU utilization
    cpu_percent_mean: float
    
    # Raw data for detailed analysis
    raw_metrics: List[RuntimeMetrics] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_name": self.test_name,
            "execution_type": self.execution_type,
            "iterations": self.iterations,
            "execution_time_ms": {
                "mean": self.exec_time_mean,
                "median": self.exec_time_median,
                "min": self.exec_time_min,
                "max": self.exec_time_max,
                "std": self.exec_time_std,
            },
            "cpu_time_ms": {
                "user": self.user_time_mean,
                "system": self.system_time_mean,
            },
            "memory_mb": {
                "peak_mean": self.peak_memory_mean,
                "peak_max": self.peak_memory_max,
            },
            "cpu_percent": self.cpu_percent_mean,
        }


class PerformanceMonitor:
    """Monitor and measure runtime performance of processes."""
    
    def __init__(self):
        self.has_psutil = self._check_psutil()
    
    def _check_psutil(self) -> bool:
        """Check if psutil is available for advanced monitoring."""
        try:
            import psutil
            return True
        except ImportError:
            return False
    
    def measure_python_execution(
        self,
        source_code: str,
        timeout: float = 30.0
    ) -> RuntimeMetrics:
        """
        Measure Python interpreted execution.
        
        Args:
            source_code: Python source code to execute
            timeout: Maximum execution time in seconds
            
        Returns:
            RuntimeMetrics: Performance metrics
        """
        import psutil
        
        # Write source to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source_code)
            temp_path = f.name
        
        try:
            # Start process with monitoring
            start_time = time.perf_counter()
            
            process = psutil.Popen(
                [sys.executable, temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor during execution
            peak_memory = 0
            cpu_percentages = []
            
            # Poll process with timeout check
            try:
                while True:
                    # Check if process is still running
                    if not process.is_running():
                        break
                    
                    try:
                        status = process.status()
                        if status == psutil.STATUS_ZOMBIE:
                            break
                        
                        # Get memory usage
                        try:
                            mem_info = process.memory_info()
                            peak_memory = max(peak_memory, mem_info.rss)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        
                        # Get CPU usage (non-blocking)
                        try:
                            cpu_pct = process.cpu_percent(interval=None)
                            if cpu_pct > 0:
                                cpu_percentages.append(cpu_pct)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        
                        # Check timeout
                        if time.perf_counter() - start_time > timeout:
                            process.kill()
                            raise TimeoutError(f"Execution exceeded {timeout}s")
                        
                        # Small sleep to prevent busy waiting
                        time.sleep(0.001)
                        
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
                        
            except TimeoutError:
                raise
            
            # Wait for completion and get output
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            
            end_time = time.perf_counter()
            
            # Get final CPU times
            try:
                cpu_times = process.cpu_times()
                user_time = cpu_times.user * 1000
                system_time = cpu_times.system * 1000
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                user_time = 0
                system_time = 0
            
            execution_time = (end_time - start_time) * 1000  # Convert to ms
            
            return RuntimeMetrics(
                execution_time_ms=execution_time,
                user_time_ms=user_time,
                system_time_ms=system_time,
                peak_memory_mb=peak_memory / (1024 * 1024),
                avg_memory_mb=peak_memory / (1024 * 1024),
                cpu_percent=statistics.mean(cpu_percentages) if cpu_percentages else 0,
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr
            )
            
        finally:
            os.unlink(temp_path)
    
    def measure_executable(
        self,
        executable_path: Path,
        timeout: float = 30.0
    ) -> RuntimeMetrics:
        """
        Measure compiled executable execution.
        
        Args:
            executable_path: Path to compiled executable
            timeout: Maximum execution time in seconds
            
        Returns:
            RuntimeMetrics: Performance metrics
        """
        import psutil
        
        if not executable_path.exists():
            raise FileNotFoundError(f"Executable not found: {executable_path}")
        
        start_time = time.perf_counter()
        
        process = psutil.Popen(
            [str(executable_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Monitor during execution
        peak_memory = 0
        cpu_percentages = []
        
        # Poll process with timeout check
        while True:
            # Check if process is still running
            if not process.is_running():
                break
            
            try:
                status = process.status()
                if status == psutil.STATUS_ZOMBIE:
                    break
                
                # Get memory usage
                try:
                    mem_info = process.memory_info()
                    peak_memory = max(peak_memory, mem_info.rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # Get CPU usage (non-blocking)
                try:
                    cpu_pct = process.cpu_percent(interval=None)
                    if cpu_pct > 0:
                        cpu_percentages.append(cpu_pct)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # Check timeout
                if time.perf_counter() - start_time > timeout:
                    process.kill()
                    raise TimeoutError(f"Execution exceeded {timeout}s")
                
                # Small sleep to prevent busy waiting
                time.sleep(0.001)
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
        
        # Wait for completion and get output
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        
        end_time = time.perf_counter()
        
        # Get final CPU times
        try:
            cpu_times = process.cpu_times()
            user_time = cpu_times.user * 1000
            system_time = cpu_times.system * 1000
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            user_time = 0
            system_time = 0
        
        execution_time = (end_time - start_time) * 1000
        
        return RuntimeMetrics(
            execution_time_ms=execution_time,
            user_time_ms=user_time,
            system_time_ms=system_time,
            peak_memory_mb=peak_memory / (1024 * 1024),
            avg_memory_mb=peak_memory / (1024 * 1024),
            cpu_percent=statistics.mean(cpu_percentages) if cpu_percentages else 0,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr
        )


class BenchmarkRunner:
    """Run comprehensive benchmarks comparing Python vs compiled execution."""
    
    def __init__(self, iterations: int = 10, warmup: int = 2):
        self.iterations = iterations
        self.warmup = warmup
        self.monitor = PerformanceMonitor()
        self.compiler = Compiler()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pcc_benchmark_"))
    
    def __del__(self):
        """Cleanup temporary files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def compile_program(self, source_code: str, name: str) -> Path:
        """Compile Python source to executable."""
        # Write source file
        source_path = self.temp_dir / f"{name}.py"
        source_path.write_text(source_code)
        
        # Compile
        exe_path = self.temp_dir / f"{name}.exe"
        result = self.compiler.build(
            input_py=source_path,
            out_exe=exe_path,
            toolchain="auto",
            emit_c_only=False
        )
        
        if not result.success:
            raise RuntimeError(f"Compilation failed: {result.error_message}")
        
        return exe_path
    
    def run_benchmark(
        self,
        test_name: str,
        source_code: str
    ) -> Tuple[BenchmarkResult, BenchmarkResult]:
        """
        Run complete benchmark comparing Python vs compiled.
        
        Returns:
            Tuple of (python_result, compiled_result)
        """
        print(f"\n  Benchmarking: {test_name}")
        print(f"  {'='*68}")
        
        # Compile the program
        print(f"  Compiling...")
        try:
            exe_path = self.compile_program(source_code, test_name)
        except Exception as e:
            print(f"  Compilation failed: {e}")
            raise
        
        # Warmup runs
        print(f"  Warmup ({self.warmup} iterations)...")
        for _ in range(self.warmup):
            try:
                self.monitor.measure_python_execution(source_code)
                self.monitor.measure_executable(exe_path)
            except Exception:
                pass
        
        # Measure Python execution
        print(f"  Measuring Python execution ({self.iterations} iterations)...")
        python_metrics = []
        for i in range(self.iterations):
            try:
                metric = self.monitor.measure_python_execution(source_code)
                python_metrics.append(metric)
                print(f"    Run {i+1}: {metric.execution_time_ms:.2f}ms")
            except Exception as e:
                print(f"    Run {i+1}: FAILED - {e}")
        
        # Measure compiled execution
        print(f"  Measuring compiled execution ({self.iterations} iterations)...")
        compiled_metrics = []
        for i in range(self.iterations):
            try:
                metric = self.monitor.measure_executable(exe_path)
                compiled_metrics.append(metric)
                print(f"    Run {i+1}: {metric.execution_time_ms:.2f}ms")
            except Exception as e:
                print(f"    Run {i+1}: FAILED - {e}")
        
        # Aggregate results
        python_result = self._aggregate_results(test_name, "python", python_metrics)
        compiled_result = self._aggregate_results(test_name, "compiled", compiled_metrics)
        
        return python_result, compiled_result
    
    def _aggregate_results(
        self,
        test_name: str,
        exec_type: str,
        metrics: List[RuntimeMetrics]
    ) -> BenchmarkResult:
        """Aggregate metrics into benchmark result."""
        if not metrics:
            raise ValueError(f"No metrics collected for {test_name} ({exec_type})")
        
        exec_times = [m.execution_time_ms for m in metrics]
        
        return BenchmarkResult(
            test_name=test_name,
            execution_type=exec_type,
            iterations=len(metrics),
            exec_time_mean=statistics.mean(exec_times),
            exec_time_median=statistics.median(exec_times),
            exec_time_min=min(exec_times),
            exec_time_max=max(exec_times),
            exec_time_std=statistics.stdev(exec_times) if len(exec_times) > 1 else 0,
            user_time_mean=statistics.mean([m.user_time_ms for m in metrics]),
            system_time_mean=statistics.mean([m.system_time_ms for m in metrics]),
            peak_memory_mean=statistics.mean([m.peak_memory_mb for m in metrics]),
            peak_memory_max=max([m.peak_memory_mb for m in metrics]),
            cpu_percent_mean=statistics.mean([m.cpu_percent for m in metrics]),
            raw_metrics=metrics
        )


class ReportGenerator:
    """Generate detailed comparison reports."""
    
    @staticmethod
    def generate_console_report(
        python_result: BenchmarkResult,
        compiled_result: BenchmarkResult
    ) -> str:
        """Generate console-formatted report."""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append(f"  BENCHMARK RESULTS: {python_result.test_name}")
        lines.append("=" * 70)
        
        # Execution time comparison
        lines.append("\n  EXECUTION TIME (ms)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Metric':<20} {'Python':>15} {'Compiled':>15} {'Change':>12}")
        lines.append("  " + "-" * 66)
        
        speedup = python_result.exec_time_mean / compiled_result.exec_time_mean
        change_pct = ((compiled_result.exec_time_mean - python_result.exec_time_mean) 
                      / python_result.exec_time_mean * 100)
        
        lines.append(f"  {'Mean':<20} {python_result.exec_time_mean:>15.2f} "
                    f"{compiled_result.exec_time_mean:>15.2f} {change_pct:>+11.1f}%")
        lines.append(f"  {'Median':<20} {python_result.exec_time_median:>15.2f} "
                    f"{compiled_result.exec_time_median:>15.2f}")
        lines.append(f"  {'Min':<20} {python_result.exec_time_min:>15.2f} "
                    f"{compiled_result.exec_time_min:>15.2f}")
        lines.append(f"  {'Max':<20} {python_result.exec_time_max:>15.2f} "
                    f"{compiled_result.exec_time_max:>15.2f}")
        lines.append(f"  {'Std Dev':<20} {python_result.exec_time_std:>15.2f} "
                    f"{compiled_result.exec_time_std:>15.2f}")
        
        lines.append("\n  " + "-" * 66)
        lines.append(f"  SPEEDUP: {speedup:.2f}x (compiled is {'faster' if speedup > 1 else 'slower'})")
        
        # Memory usage
        lines.append("\n  MEMORY USAGE (MB)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Peak (mean)':<20} {python_result.peak_memory_mean:>15.2f} "
                    f"{compiled_result.peak_memory_mean:>15.2f}")
        lines.append(f"  {'Peak (max)':<20} {python_result.peak_memory_max:>15.2f} "
                    f"{compiled_result.peak_memory_max:>15.2f}")
        
        # CPU utilization
        lines.append("\n  CPU UTILIZATION (%)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Average':<20} {python_result.cpu_percent_mean:>15.1f} "
                    f"{compiled_result.cpu_percent_mean:>15.1f}")
        
        lines.append("\n" + "=" * 70)
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_json_report(
        results: List[Tuple[BenchmarkResult, BenchmarkResult]],
        output_path: Path
    ):
        """Generate JSON report."""
        data = {
            "benchmarks": []
        }
        
        for python_result, compiled_result in results:
            benchmark_data = {
                "test_name": python_result.test_name,
                "python": python_result.to_dict(),
                "compiled": compiled_result.to_dict(),
                "comparison": {
                    "speedup": python_result.exec_time_mean / compiled_result.exec_time_mean,
                    "time_change_percent": (
                        (compiled_result.exec_time_mean - python_result.exec_time_mean)
                        / python_result.exec_time_mean * 100
                    ),
                }
            }
            data["benchmarks"].append(benchmark_data)
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)


# =============================================================================
# TEST PROGRAMS
# =============================================================================

TEST_PROGRAMS = {
    "simple_loop": """
total = 0
i = 0
while i < 1000000:
    total = total + i
    i = i + 1
print(total)
""",
    "factorial": """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(20)
print(result)
""",
    "fibonacci": """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

result = fibonacci(30)
print(result)
""",
    "string_concat": """
result = ""
i = 0
while i < 10000:
    result = result + "a"
    i = i + 1
print(len(result))
""",
    "list_operations": """
items = []
i = 0
while i < 100000:
    items = items + [i]
    i = i + 1
print(len(items))
""",
}


# =============================================================================
# PYTEST TEST CASES
# =============================================================================

class TestRuntimePerformance:
    """Runtime performance comparison tests."""
    
    @pytest.fixture(scope="class")
    def benchmark_runner(self):
        """Create benchmark runner fixture."""
        runner = BenchmarkRunner(iterations=5, warmup=2)
        yield runner
    
    @pytest.mark.skipif(
        not PerformanceMonitor().has_psutil,
        reason="psutil not installed"
    )
    def test_simple_loop_performance(self, benchmark_runner):
        """Benchmark simple loop execution."""
        source = TEST_PROGRAMS["simple_loop"]
        python_result, compiled_result = benchmark_runner.run_benchmark(
            "simple_loop", source
        )
        
        # Print report
        report = ReportGenerator.generate_console_report(python_result, compiled_result)
        print(report)
        
        # Assertions
        assert python_result.iterations == 5
        assert compiled_result.iterations == 5
        
        # Compiled should generally be faster for compute-heavy tasks
        speedup = python_result.exec_time_mean / compiled_result.exec_time_mean
        print(f"\n  Speedup: {speedup:.2f}x")
    
    @pytest.mark.skipif(
        not PerformanceMonitor().has_psutil,
        reason="psutil not installed"
    )
    def test_factorial_performance(self, benchmark_runner):
        """Benchmark factorial calculation."""
        source = TEST_PROGRAMS["factorial"]
        python_result, compiled_result = benchmark_runner.run_benchmark(
            "factorial", source
        )
        
        report = ReportGenerator.generate_console_report(python_result, compiled_result)
        print(report)
        
        assert python_result.iterations == 5
        assert compiled_result.iterations == 5
    
    @pytest.mark.skipif(
        not PerformanceMonitor().has_psutil,
        reason="psutil not installed"
    )
    def test_fibonacci_performance(self, benchmark_runner):
        """Benchmark fibonacci calculation."""
        source = TEST_PROGRAMS["fibonacci"]
        python_result, compiled_result = benchmark_runner.run_benchmark(
            "fibonacci", source
        )
        
        report = ReportGenerator.generate_console_report(python_result, compiled_result)
        print(report)
        
        assert python_result.iterations == 5
        assert compiled_result.iterations == 5


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_full_benchmark_suite():
    """Run complete benchmark suite."""
    print("\n" + "=" * 70)
    print("  PCC RUNTIME PERFORMANCE BENCHMARK SUITE")
    print("  Comparing Python Interpreted vs Compiled Execution")
    print("=" * 70)
    
    # Check psutil availability
    monitor = PerformanceMonitor()
    if not monitor.has_psutil:
        print("\n  WARNING: psutil not installed. Install with: pip install psutil")
        print("  Falling back to basic timing measurements only.")
        return
    
    runner = BenchmarkRunner(iterations=10, warmup=3)
    all_results = []
    
    for test_name, source in TEST_PROGRAMS.items():
        try:
            python_result, compiled_result = runner.run_benchmark(test_name, source)
            all_results.append((python_result, compiled_result))
            
            # Print individual report
            report = ReportGenerator.generate_console_report(python_result, compiled_result)
            print(report)
            
        except Exception as e:
            print(f"\n  ERROR in {test_name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Generate summary
    print("\n" + "=" * 70)
    print("  OVERALL SUMMARY")
    print("=" * 70)
    
    if all_results:
        speedups = [p.exec_time_mean / c.exec_time_mean for p, c in all_results]
        avg_speedup = statistics.mean(speedups)
        
        print(f"\n  Tests completed: {len(all_results)}/{len(TEST_PROGRAMS)}")
        print(f"  Average speedup: {avg_speedup:.2f}x")
        print(f"  Min speedup: {min(speedups):.2f}x")
        print(f"  Max speedup: {max(speedups):.2f}x")
        
        # Save JSON report
        report_path = Path("benchmark_report.json")
        ReportGenerator.generate_json_report(all_results, report_path)
        print(f"\n  Detailed report saved to: {report_path.absolute()}")
    
    print("\n" + "=" * 70)
    print("  Benchmark suite completed")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_full_benchmark_suite()
    print("\n  Running pytest...")
    pytest.main([__file__, "-v", "-s"])
