#!/usr/bin/env python3
"""
PCC Fixture Test Runner

A modern Python script for running PCC compiler fixture tests.

This script compiles Python test fixtures to executables using the PCC compiler
and verifies their output against expected results.

Usage:
    python run_tests.py [options]

Examples:
    python run_tests.py
    python run_tests.py --toolchain msvc
    python run_tests.py --verbose --fail-fast
    python run_tests.py --fixtures-dir ./custom_tests

Author: PCC Team
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator, Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


class Toolchain(Enum):
    """Supported compiler toolchains."""
    AUTO = "auto"
    MSVC = "msvc"
    CLANG_CL = "clang-cl"
    GCC = "gcc"


@dataclass(frozen=True)
class TestResult:
    """Represents the result of a single test."""
    name: str
    passed: bool
    build_success: bool
    expected_output: str = ""
    actual_output: str = ""
    error_message: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}"


@dataclass
class TestSuite:
    """Manages a collection of test results."""
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        """Return the number of passed tests."""
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        """Return the number of failed tests."""
        return sum(1 for r in self.results if not r.passed)

    @property
    def total_count(self) -> int:
        """Return the total number of tests."""
        return len(self.results)

    def add_result(self, result: TestResult) -> None:
        """Add a test result to the suite."""
        self.results.append(result)

    def print_summary(self) -> None:
        """Print a summary of all test results."""
        print("\n" + "=" * 50)
        print(f"Test Summary: {self.passed_count} passed, {self.failed_count} failed")
        print("=" * 50)

        if self.failed_count > 0:
            print("\nFailed tests:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.name}")


class TestRunner:
    """
    Main test runner class for PCC fixture tests.

    This class handles the discovery, compilation, and execution of fixture tests.
    """

    def __init__(
        self,
        fixtures_dir: Path,
        output_dir: Path,
        toolchain: Toolchain = Toolchain.AUTO,
        verbose: bool = False,
        fail_fast: bool = False
    ) -> None:
        """
        Initialize the test runner.

        Args:
            fixtures_dir: Directory containing test fixtures
            output_dir: Directory for compiled executables
            toolchain: Compiler toolchain to use
            verbose: Enable verbose output
            fail_fast: Stop on first failure
        """
        self.fixtures_dir = fixtures_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.toolchain = toolchain
        self.verbose = verbose
        self.fail_fast = fail_fast
        self.test_suite = TestSuite()

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.verbose:
            logger.setLevel(logging.DEBUG)

    def discover_tests(self) -> Iterator[Path]:
        """
        Discover all test fixture files in the fixtures directory.

        Yields:
            Path objects to test fixture Python files
        """
        if not self.fixtures_dir.exists():
            raise FileNotFoundError(f"Fixtures directory not found: {self.fixtures_dir}")

        test_files = sorted(self.fixtures_dir.glob("t*.py"))

        if len(test_files) < 3:
            raise ValueError(
                f"Expected at least 3 tests, found {len(test_files)} in {self.fixtures_dir}"
            )

        logger.debug(f"Discovered {len(test_files)} test files")
        yield from test_files

    def normalize_output(self, text: str) -> str:
        """
        Normalize text output for comparison.

        Converts CRLF to LF and trims trailing whitespace.

        Args:
            text: Raw output text

        Returns:
            Normalized text
        """
        return text.replace("\r\n", "\n").rstrip()

    def _needs_hpf(self, test_file: Path) -> bool:
        """Check if a test file needs HPF (BigInt/Class) support."""
        # Check filename patterns
        name = test_file.stem.lower()
        if "bigint" in name or "divmod_big" in name or "class" in name:
            return True
        # Check for large integers in source
        try:
            content = test_file.read_text(encoding="utf-8")
            # Check for class definitions
            if "class " in content:
                return True
            import re
            # Find all integer literals
            for match in re.finditer(r'\b(\d+)\b', content):
                num_str = match.group(1)
                # If number is larger than 64-bit max, needs HPF
                if len(num_str) > 18:  # 2^63-1 has 19 digits
                    return True
                try:
                    val = int(num_str)
                    if val > 9223372036854775807 or val < -9223372036854775808:
                        return True
                except ValueError:
                    pass
        except IOError:
            pass
        return False

    def build_test(self, test_file: Path, exe_path: Path) -> bool:
        """
        Compile a test fixture to an executable.

        Args:
            test_file: Path to the Python test fixture
            exe_path: Path for the output executable

        Returns:
            True if compilation succeeded, False otherwise
        """
        cmd = [
            sys.executable, "-m", "pcc", "build",
            str(test_file),
            "-o", str(exe_path),
            "--toolchain", self.toolchain.value,
            "--parser-version", "2"
        ]
        
        # Add --use-hpf flag for tests that need BigInt support
        if self._needs_hpf(test_file):
            cmd.append("--use-hpf")

        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                logger.error(f"Build failed for {test_file.name}:")
                if result.stderr:
                    logger.error(result.stderr)
                return False

            return True

        except subprocess.SubprocessError as e:
            logger.error(f"Build subprocess error for {test_file.name}: {e}")
            return False

    def run_executable(self, exe_path: Path) -> str:
        """
        Run a compiled executable and capture its output.

        Args:
            exe_path: Path to the executable

        Returns:
            Captured stdout as string
        """
        try:
            result = subprocess.run(
                [str(exe_path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30  # 30 second timeout
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error(f"Test executable timed out: {exe_path}")
            return ""
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run executable {exe_path}: {e}")
            return ""

    def load_expected_output(self, expected_file: Path) -> str:
        """
        Load expected output from a file.

        Args:
            expected_file: Path to the expected output file

        Returns:
            Expected output as string
        """
        try:
            return expected_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(f"Expected output file not found: {expected_file}")
        except IOError as e:
            raise IOError(f"Failed to read expected output file {expected_file}: {e}")

    def run_single_test(self, test_file: Path) -> TestResult:
        """
        Run a single test fixture.

        Args:
            test_file: Path to the test fixture Python file

        Returns:
            TestResult containing the test outcome
        """
        test_name = test_file.stem
        expected_file = self.fixtures_dir / f"{test_name}.expected.txt"
        exe_path = self.output_dir / f"{test_name}.exe"

        print(f"\n==> [test] {test_name}")
        logger.debug(f"Test file: {test_file}")
        logger.debug(f"Expected file: {expected_file}")
        logger.debug(f"Output executable: {exe_path}")

        # Check for expected file
        if not expected_file.exists():
            return TestResult(
                name=test_name,
                passed=False,
                build_success=False,
                error_message=f"Missing expected file: {expected_file}"
            )

        # Build the test
        build_success = self.build_test(test_file, exe_path)

        if not build_success:
            print(f"[test] BUILD FAILED: {test_name}")
            return TestResult(
                name=test_name,
                passed=False,
                build_success=False,
                error_message="Build failed"
            )

        # Run the executable
        actual_output = self.run_executable(exe_path)
        actual_normalized = self.normalize_output(actual_output)

        # Load expected output
        try:
            expected_output = self.load_expected_output(expected_file)
            expected_normalized = self.normalize_output(expected_output)
        except (FileNotFoundError, IOError) as e:
            return TestResult(
                name=test_name,
                passed=False,
                build_success=True,
                actual_output=actual_normalized,
                error_message=str(e)
            )

        # Compare outputs
        passed = actual_normalized == expected_normalized

        if passed:
            print(f"[test] PASS: {test_name}")
            return TestResult(
                name=test_name,
                passed=True,
                build_success=True,
                expected_output=expected_normalized,
                actual_output=actual_normalized
            )
        else:
            print(f"[test] FAIL: {test_name}")
            if self.verbose:
                print("---- expected ----")
                print(expected_normalized)
                print("---- actual ----")
                print(actual_normalized)
            return TestResult(
                name=test_name,
                passed=False,
                build_success=True,
                expected_output=expected_normalized,
                actual_output=actual_normalized,
                error_message="Output mismatch"
            )

    def run_all_tests(self) -> int:
        """
        Run all discovered tests.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("=" * 50)
        print("PCC Fixture Test Runner")
        print("=" * 50)
        print(f"Fixtures directory: {self.fixtures_dir}")
        print(f"Output directory: {self.output_dir}")
        print(f"Toolchain: {self.toolchain.value}")
        print(f"Verbose: {self.verbose}")
        print(f"Fail fast: {self.fail_fast}")

        try:
            test_files = list(self.discover_tests())
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Test discovery failed: {e}")
            return 1

        print(f"\nFound {len(test_files)} test(s)")

        for test_file in test_files:
            result = self.run_single_test(test_file)
            self.test_suite.add_result(result)

            if not result.passed and self.fail_fast:
                logger.info("Fail-fast enabled, stopping after first failure")
                break

        # Print summary
        self.test_suite.print_summary()

        return 0 if self.test_suite.failed_count == 0 else 1


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        prog="run_tests.py",
        description="Run PCC compiler fixture tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py
  python run_tests.py --toolchain msvc
  python run_tests.py --verbose --fail-fast
  python run_tests.py --fixtures-dir ./custom_tests --output-dir ./build
        """
    )

    parser.add_argument(
        "--toolchain",
        type=str,
        choices=[t.value for t in Toolchain],
        default="auto",
        help="Compiler toolchain to use (default: auto)"
    )

    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=None,
        help="Directory containing test fixtures (default: ../tests/fixtures)"
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for compiled executables (default: ../build/test_out)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--fail-fast", "-x",
        action="store_true",
        help="Stop on first failure"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0"
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the test runner.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_arguments()

    # Determine directories
    script_dir = Path(__file__).parent.resolve()
    repo_root = script_dir.parent

    if args.fixtures_dir:
        fixtures_dir = args.fixtures_dir
    else:
        fixtures_dir = repo_root / "tests" / "fixtures"

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = repo_root / "build" / "test_out"

    # Create and run the test runner
    runner = TestRunner(
        fixtures_dir=fixtures_dir,
        output_dir=output_dir,
        toolchain=Toolchain(args.toolchain),
        verbose=args.verbose,
        fail_fast=args.fail_fast
    )

    return runner.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
