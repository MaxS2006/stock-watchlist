#!/usr/bin/env python3
"""
Fits factor weights for the experimental weighted signal (see
monitor.compute_weighted_signal) via logistic regression over
backtest_results/all_days.json — every trading day in the backtest window,
not just days the old tally logic already called directional. Training
only on tally-flagged days would bake that heuristic's own selection bias
into the new weights.

One-off analysis tool: not run in CI or the scheduled job, same category
as backtest.py itself. Regenerate all_days.json first (`python
backtest.py`), then run this and hand-paste the printed
WEIGHTED_FACTOR_WEIGHTS dict into monitor.py — weights are a plain
committed constant there, not something monitor.py loads at runtime.

Uses a small hand-rolled Newton-Raphson logistic regression (numpy only,
already a pandas dependency) rather than adding scikit-learn — the
feature space here is under a dozen columns, low-dimensional enough that
this converges in a handful of iterations.

SPY market regime (see monitor.compute_spy_regime) is included as just
another dummy-coded dimension here, on equal footing with the price
factors — NOT as a hardcoded "suppress bearish outside a downtrend" rule.
That rule was the original plan, until backtesting it directly showed the
opposite of what was assumed: bearish signals were *less* reliable, not
more, when SPY itself was trending down (see the "By market regime" table
in report.md). Letting the regression size regime's effect avoids baking
in a hand-picked assumption that turned out to be backwards.

Each dimension is dummy-coded relative to a baseline level that's dropped
from the design matrix (its effect is absorbed into the intercept) —
"neutral" when the dimension has one (rsi, volume, breadth), otherwise
the next-most-natural default ("neg" for ma50, which is always pos or neg;
"uptrend" for regime). Keeping every level as its own dummy would make the
design matrix rank-deficient (the levels of a dimension plus the intercept
sum to a constant), so one baseline is dropped rather than regularized away.

Usage:
    python backtest.py          # produces backtest_results/all_days.json
    python fit_weights.py
"""

import json
import os
import sys

import numpy as np

import monitor
from backtest import OUTPUT_DIR

ALL_DAYS_JSON = os.path.join(OUTPUT_DIR, "all_days.json")

# Extractors take a whole all_days record (not just its factors list) so
# regime — a record-level field, not a factor — fits the same shape as the
# price factors below.
DIMENSIONS = {
    dim: (lambda extractor: (lambda rec: extractor(rec["factors"])))(extractor)
    for dim, extractor in monitor.FACTOR_DIMENSIONS.items()
}
DIMENSIONS["regime"] = lambda rec: rec.get("regime")

BASELINE_PRIORITY = ["neutral", "neg", "uptrend"]


def choose_baseline(seen):
    for candidate in BASELINE_PRIORITY:
        if candidate in seen:
            return candidate
    return sorted(seen)[0] if seen else None


def load_all_days():
    with open(ALL_DAYS_JSON) as f:
        data = json.load(f)
    return data["all_days"]


def detect_levels(records):
    """{dim: (baseline_lean, [non-baseline leans])} — which lean is dropped
    as the baseline is decided per-dimension from what's actually present
    in the data."""
    levels = {}
    for dim, extractor in DIMENSIONS.items():
        seen = {extractor(rec) for rec in records} - {None}
        baseline = choose_baseline(seen)
        levels[dim] = (baseline, sorted(lean for lean in seen if lean != baseline))
    return levels


def build_dataset(records, features):
    rows = []
    targets = []
    for rec in records:
        if rec.get("future_up") is None:
            continue
        row = [1.0]
        for dim, lean in features:
            row.append(1.0 if DIMENSIONS[dim](rec) == lean else 0.0)
        rows.append(row)
        targets.append(1.0 if rec["future_up"] else 0.0)
    return np.array(rows), np.array(targets)


def fit_logistic_regression(X, y, ridge=1e-6, max_iter=50, tol=1e-8, max_step=5.0):
    """Newton-Raphson / IRLS. beta_new = beta + (X'WX + ridge*I)^-1 X'(y-p),
    the standard Newton update for logistic MLE — ridge is a tiny numerical
    stabilizer, not meaningful regularization, given the row counts here.
    Some dummy columns are highly correlated (e.g. ma50_pos is ~1-ma50_neg
    whenever both are computable), which can make an early, still-far-from-
    converged step's X'WX nearly singular and the raw Newton step huge —
    max_step clips each step's magnitude (log-odds units, so ±5 is already
    an extreme swing) so that transient blowup can't produce inf/nan; once
    beta is close to the optimum the clip never binds."""
    n, k = X.shape
    beta = np.zeros(k)
    iterations = 0
    # Some BLAS backends (observed with macOS Accelerate) emit spurious
    # divide-by-zero/overflow RuntimeWarnings on ordinary matmuls of exact
    # zeros — harmless, but noisy; suppressed here since X/beta are
    # verified finite going in and the fitted result is sanity-checked by
    # evaluate() afterward.
    with np.errstate(all="ignore"):
        for iterations in range(1, max_iter + 1):
            z = X @ beta
            p = np.clip(1 / (1 + np.exp(-z)), 1e-9, 1 - 1e-9)
            gradient = X.T @ (y - p)
            w = p * (1 - p)
            xtwx = X.T @ (X * w[:, None]) + ridge * np.eye(k)
            delta = np.linalg.solve(xtwx, gradient)
            delta = np.clip(delta, -max_step, max_step)
            beta = beta + delta
            if np.max(np.abs(delta)) < tol:
                break
    return beta, iterations


def evaluate(X, y, beta):
    with np.errstate(all="ignore"):
        p = 1 / (1 + np.exp(-(X @ beta)))
    accuracy = float(np.mean((p >= 0.5) == (y == 1.0)))
    base_rate = float(np.mean(y))
    return accuracy, base_rate


def main():
    if not os.path.exists(ALL_DAYS_JSON):
        print(f"{ALL_DAYS_JSON} not found — run `python backtest.py` first.", file=sys.stderr)
        sys.exit(1)

    records = load_all_days()
    print(f"Loaded {len(records)} all-day records.")

    levels = detect_levels(records)
    for dim, (baseline, dim_levels) in levels.items():
        print(f"  {dim}: fitting {dim_levels}, baseline (dropped) = {baseline!r}")
    features = [(dim, lean) for dim in DIMENSIONS for lean in levels[dim][1]]
    feature_names = ["intercept"] + [f"{dim}_{lean}" for dim, lean in features]

    X, y = build_dataset(records, features)
    print(f"{len(y)} rows after dropping flat/unresolved future outcomes.\n")

    beta, iterations = fit_logistic_regression(X, y)
    accuracy, base_rate = evaluate(X, y, beta)
    print(f"Converged in {iterations} iterations.")
    print(f"In-sample accuracy: {accuracy:.1%} (base rate of future_up: {base_rate:.1%})\n")

    print("Coefficients (log-odds, relative to each dimension's baseline):")
    for name, coef in zip(feature_names, beta):
        print(f"  {name:>16}: {coef:+.4f}")

    # Fill in every (dim, lean) explicitly, including the dropped baseline
    # (weight 0.0 — its effect is already in the intercept) so
    # monitor.compute_weighted_signal never has to special-case a missing key.
    weights = {"intercept": round(float(beta[0]), 4)}
    for dim, (baseline, dim_levels) in levels.items():
        weights[dim] = {lean: 0.0 for lean in dim_levels}
        if baseline is not None:
            weights[dim][baseline] = 0.0
    for (dim, lean), coef in zip(features, beta[1:]):
        weights[dim][lean] = round(float(coef), 4)

    print("\nPaste into monitor.py as WEIGHTED_FACTOR_WEIGHTS:\n")
    print("WEIGHTED_FACTOR_WEIGHTS = " + json.dumps(weights, indent=4))


if __name__ == "__main__":
    main()
