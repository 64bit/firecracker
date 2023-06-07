# Copyright 2023 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Optional benchmarks-do-not-regress test"""

import json
import logging
import os
import platform

import pytest

from framework import utils
from host_tools.cargo_build import cargo

TARGET_BRANCH = os.environ.get("BUILDKITE_PULL_REQUEST_BASE_BRANCH") or "main"
LOGGER = logging.getLogger(__name__)


@pytest.mark.no_block_pr
@pytest.mark.timeout(600)
def test_no_regression_relative_to_target_branch():
    """
    Run the microbenchmarks in this repository, comparing results from pull
    request target branch against what's achieved on HEAD
    """
    # First, run benchmarks on pull request target branch (usually main). For this, cache the commit at which
    # the test was originally executed
    _, pr_head_commit_sha, _ = utils.run_cmd("git rev-parse HEAD")
    utils.run_cmd(f"git switch {TARGET_BRANCH}")
    cargo("bench", f"--all --quiet --target {platform.machine()}-unknown-linux-musl")

    # Switch back to pull request, and run benchmarks again. Criterion will automatically notice that
    # data from a previous run exists, and do a comparison
    utils.run_cmd(f"git checkout {pr_head_commit_sha}")
    _, criterion_output, _ = cargo(
        "bench", f"--all --quiet --target {platform.machine()}-unknown-linux-musl"
    )

    # Criterion separates reports for benchmarks by two newlines. We filter and print the ones
    # that contain the string 'Performance has regression.', which criterion uses to indicate a regression
    regressions_only = "\n\n".join(
        result
        for result in criterion_output.split("\n\n")
        if "Performance has regressed." in result
    )

    for benchmark in os.listdir("../build/cargo_target/criterion"):
        with open(
            f"../build/cargo_target/criterion/{benchmark}/new/estimates.json",
            encoding="utf-8",
        ) as file:
            data = json.load(file)
        average_ns = data["mean"]["point_estimate"]

        LOGGER.info("%s mean: %iµs", benchmark, average_ns / 1000)

    # If this string is anywhere in stdout, then at least one of our benchmarks
    # is now performing worse with the PR changes.
    assert not regressions_only, "\n" + regressions_only
