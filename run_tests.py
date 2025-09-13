#!/usr/bin/env python3
"""
Test runner script for the GitHub metadata extractor.
Provides different test execution modes and reporting.
"""
import sys
import subprocess
import argparse
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running {description}:")
        print(f"Return code: {e.returncode}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Run tests for GitHub metadata extractor")
    parser.add_argument(
        "--type",
        choices=["unit", "component", "integration", "all"],
        default="all",
        help="Type of tests to run"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run with coverage reporting"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--parallel",
        "-n",
        type=int,
        help="Run tests in parallel with specified number of workers"
    )
    parser.add_argument(
        "--html-report",
        action="store_true",
        help="Generate HTML coverage report"
    )
    parser.add_argument(
        "--xml-report",
        action="store_true",
        help="Generate XML test report"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test directory based on type
    if args.type == "unit":
        cmd.append("tests/unit/")
    elif args.type == "component":
        cmd.append("tests/component/")
    elif args.type == "integration":
        cmd.append("tests/component/test_integration.py")
    elif args.type == "all":
        cmd.append("tests/")
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
    
    # Add coverage
    if args.coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-report=html" if args.html_report else "--cov-report=html:htmlcov"
        ])
    
    # Add XML report
    if args.xml_report:
        cmd.append("--junitxml=test-results.xml")
    
    # Add test markers
    if args.type == "unit":
        cmd.extend(["-m", "unit"])
    elif args.type == "component":
        cmd.extend(["-m", "component"])
    elif args.type == "integration":
        cmd.extend(["-m", "integration"])
    
    # Run the tests
    success = run_command(cmd, f"{args.type.title()} tests")
    
    if success:
        print(f"\n✅ {args.type.title()} tests passed successfully!")
        
        if args.coverage and args.html_report:
            print(f"\n📊 HTML coverage report generated in htmlcov/index.html")
        
        if args.xml_report:
            print(f"\n📋 XML test report generated in test-results.xml")
    else:
        print(f"\n❌ {args.type.title()} tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
