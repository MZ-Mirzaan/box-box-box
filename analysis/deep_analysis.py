#!/usr/bin/env python3
"""
Box Box Box — Phase 1b: Deep Parameter Extraction
===================================================
Uses the "cheat code" technique to reverse-engineer formula parameters
from pairwise driver comparisons within races.

Key approach:
- For each race, assume formula: lap_time = base + offset[c] + deg_rate[c] * age * temp_mult
- Two drivers in same race differ only in strategy
- Finishing order constrains: total_time(winner) < total_time(loser)
- Across 30k races, these constraints pin down the exact parameters

Run: python analysis/deep_analysis.py
"""

import json
import os
import sys
from collections import defaultdict
import math

# ============================================================================
# DATA LOADING
# ============================================================================

DATA_DIR = "data/historical_races"
if not os.path.exists(DATA_DIR):
    DATA_DIR = "box-box-box/data/historical_races"

def load_races(num_files=5):
    all_races = []
    files = sorted(os.listdir(DATA_DIR))
    for fname in files[:num_files]:
        with open(os.path.join(DATA_DIR, fname), 'r') as f:
            all_races.extend(json.load(f))
    return all_races

print("Loading data...")
races = load_races(num_files=5)  # 5000 races
print(f"Loaded {len(races)} races")
print()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_driver_stints(strategy, total_laps):
    stints = []
    current_compound = strategy["starting_tire"]
    current_start = 1
    for stop in sorted(strategy["pit_stops"], key=lambda s: s["lap"]):
        pit_lap = stop["lap"]
        stint_laps = pit_lap - current_start + 1
        stints.append((current_compound, stint_laps))
        current_compound = stop["to_tire"]
        current_start = pit_lap + 1
    final_laps = total_laps - current_start + 1
    stints.append((current_compound, final_laps))
    return stints

def stint_degradation_sum_linear(N):
    """Sum of 1+2+...+N = N*(N+1)/2"""
    return N * (N + 1) / 2

def stint_degradation_sum_quadratic(N):
    """Sum of 1^2+2^2+...+N^2 = N*(N+1)*(2N+1)/6"""
    return N * (N + 1) * (2 * N + 1) / 6

def compute_total_time(strategy, total_laps, base_lap_time, pit_lane_time,
                       compound_offsets, deg_rates, temp, deg_power=1,
                       temp_ref=30, temp_coeff=0.0):
    """Compute total race time for a driver given formula parameters."""
    stints = get_driver_stints(strategy, total_laps)
    num_pits = len(strategy["pit_stops"])
    total_time = num_pits * pit_lane_time
    temp_mult = 1.0 + temp_coeff * (temp - temp_ref)

    for compound, N in stints:
        offset = compound_offsets[compound]
        deg = deg_rates[compound]
        # Base time for stint
        total_time += N * base_lap_time
        # Compound offset for stint
        total_time += N * offset
        # Degradation sum
        if deg_power == 1:
            total_time += deg * stint_degradation_sum_linear(N) * temp_mult
        elif deg_power == 2:
            total_time += deg * stint_degradation_sum_quadratic(N) * temp_mult
        else:
            # General power
            total_time += deg * sum(i**deg_power for i in range(1, N+1)) * temp_mult

    return total_time

def predict_race(race, compound_offsets, deg_rates, deg_power=1,
                 temp_ref=30, temp_coeff=0.0):
    """Predict finishing order for a race."""
    cfg = race["race_config"]
    driver_times = {}
    for pos_key, strategy in race["strategies"].items():
        did = strategy["driver_id"]
        t = compute_total_time(
            strategy, cfg["total_laps"], cfg["base_lap_time"],
            cfg["pit_lane_time"], compound_offsets, deg_rates,
            cfg["track_temp"], deg_power, temp_ref, temp_coeff
        )
        driver_times[did] = t
    sorted_drivers = sorted(driver_times.items(), key=lambda x: x[1])
    return [d[0] for d in sorted_drivers]

def score_params(races_subset, compound_offsets, deg_rates, deg_power=1,
                 temp_ref=30, temp_coeff=0.0):
    """Score: fraction of races predicted correctly."""
    correct = 0
    for race in races_subset:
        predicted = predict_race(race, compound_offsets, deg_rates,
                                 deg_power, temp_ref, temp_coeff)
        if predicted == race["finishing_positions"]:
            correct += 1
    return correct / len(races_subset)

# ============================================================================
# GRID SEARCH: Find approximate parameters
# ============================================================================

print("=" * 70)
print("GRID SEARCH: Finding approximate compound offsets and degradation rates")
print("=" * 70)
print()

# Use a smaller subset for fast grid search
search_races = races[:1000]

# We can fix MEDIUM offset = 0 as reference
# Search over: SOFT offset, HARD offset, SOFT deg, MEDIUM deg, HARD deg

best_score = 0
best_params = None

# Coarse grid search
print("Phase A: Coarse grid search (linear degradation, no temp effect)...")
soft_offsets = [-1.0, -0.6, -0.4, -0.3, -0.2, -0.1, 0.0]
hard_offsets = [0.0, 0.1, 0.2, 0.3, 0.4, 0.6, 1.0]
soft_degs = [0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
med_degs = [0.01, 0.03, 0.05, 0.08, 0.10]
hard_degs = [0.005, 0.01, 0.02, 0.03, 0.05]

total_combos = len(soft_offsets) * len(hard_offsets) * len(soft_degs) * len(med_degs) * len(hard_degs)
print(f"  Searching {total_combos} parameter combinations...")

tested = 0
for so in soft_offsets:
    for ho in hard_offsets:
        for sd in soft_degs:
            for md in med_degs:
                for hd in hard_degs:
                    offsets = {"SOFT": so, "MEDIUM": 0.0, "HARD": ho}
                    degs = {"SOFT": sd, "MEDIUM": md, "HARD": hd}
                    score = score_params(search_races, offsets, degs)
                    if score > best_score:
                        best_score = score
                        best_params = (offsets.copy(), degs.copy())
                        print(f"    New best: {score:.1%} | offsets={offsets} | degs={degs}")
                    tested += 1
                    if tested % 1000 == 0:
                        print(f"    ...tested {tested}/{total_combos}, current best: {best_score:.1%}")

print(f"\n  Coarse search best: {best_score:.1%}")
print(f"  Offsets: {best_params[0]}")
print(f"  Deg rates: {best_params[1]}")
print()

# ============================================================================
# REFINE: Fine grid around best params
# ============================================================================

print("Phase B: Fine grid search around best parameters...")
bo, bd = best_params

# Refine offsets within +/- 0.15 of best
fine_soft_offsets = [bo["SOFT"] + d for d in [-0.15, -0.1, -0.05, 0.0, 0.05, 0.1, 0.15]]
fine_hard_offsets = [bo["HARD"] + d for d in [-0.15, -0.1, -0.05, 0.0, 0.05, 0.1, 0.15]]
fine_soft_degs = [bd["SOFT"] + d for d in [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03]]
fine_med_degs = [bd["MEDIUM"] + d for d in [-0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02]]
fine_hard_degs = [bd["HARD"] + d for d in [-0.01, -0.005, 0.0, 0.005, 0.01]]

# Filter out negative degradation rates
fine_soft_degs = [x for x in fine_soft_degs if x > 0]
fine_med_degs = [x for x in fine_med_degs if x > 0]
fine_hard_degs = [x for x in fine_hard_degs if x > 0]

total_fine = len(fine_soft_offsets) * len(fine_hard_offsets) * len(fine_soft_degs) * len(fine_med_degs) * len(fine_hard_degs)
print(f"  Searching {total_fine} fine combinations...")

tested = 0
for so in fine_soft_offsets:
    for ho in fine_hard_offsets:
        for sd in fine_soft_degs:
            for md in fine_med_degs:
                for hd in fine_hard_degs:
                    offsets = {"SOFT": so, "MEDIUM": 0.0, "HARD": ho}
                    degs = {"SOFT": sd, "MEDIUM": md, "HARD": hd}
                    score = score_params(search_races, offsets, degs)
                    if score > best_score:
                        best_score = score
                        best_params = (offsets.copy(), degs.copy())
                        print(f"    New best: {score:.1%} | offsets={offsets} | degs={degs}")
                    tested += 1

print(f"\n  Fine search best: {best_score:.1%}")
print(f"  Offsets: {best_params[0]}")
print(f"  Deg rates: {best_params[1]}")
print()

# ============================================================================
# TEST: Quadratic degradation
# ============================================================================

print("Phase C: Testing quadratic degradation with best offsets...")
bo, _ = best_params

quad_best_score = 0
quad_best_params = None

# Quadratic degradation rates are much smaller (since age^2 grows faster)
q_soft_degs = [0.001, 0.002, 0.003, 0.005, 0.008, 0.01, 0.015]
q_med_degs = [0.0005, 0.001, 0.002, 0.003, 0.005]
q_hard_degs = [0.0002, 0.0005, 0.001, 0.002, 0.003]

for sd in q_soft_degs:
    for md in q_med_degs:
        for hd in q_hard_degs:
            degs = {"SOFT": sd, "MEDIUM": md, "HARD": hd}
            score = score_params(search_races, bo, degs, deg_power=2)
            if score > quad_best_score:
                quad_best_score = score
                quad_best_params = (bo.copy(), degs.copy())

print(f"  Quadratic best: {quad_best_score:.1%}")
print(f"  Offsets: {quad_best_params[0]}")
print(f"  Deg rates: {quad_best_params[1]}")
print(f"  Compare linear best: {best_score:.1%}")
print()

# ============================================================================
# TEMPERATURE EFFECT
# ============================================================================

print("Phase D: Adding temperature effect to best model...")

# Determine which model (linear/quad) was better
if quad_best_score > best_score:
    use_power = 2
    use_offsets, use_degs = quad_best_params
    print(f"  Using quadratic model (score={quad_best_score:.1%})")
else:
    use_power = 1
    use_offsets, use_degs = best_params
    print(f"  Using linear model (score={best_score:.1%})")

temp_best_score = max(best_score, quad_best_score)
temp_best_coeff = 0.0
temp_best_ref = 30

for temp_ref in [25, 28, 30, 32, 35]:
    for temp_coeff in [0.001, 0.003, 0.005, 0.008, 0.01, 0.015, 0.02, 0.03, 0.05]:
        score = score_params(search_races, use_offsets, use_degs,
                             deg_power=use_power, temp_ref=temp_ref,
                             temp_coeff=temp_coeff)
        if score > temp_best_score:
            temp_best_score = score
            temp_best_coeff = temp_coeff
            temp_best_ref = temp_ref
            print(f"    New best: {score:.1%} | temp_ref={temp_ref}, temp_coeff={temp_coeff}")

print(f"\n  With temperature: {temp_best_score:.1%}")
print(f"  temp_ref={temp_best_ref}, temp_coeff={temp_best_coeff}")
print()

# ============================================================================
# VALIDATE ON LARGER SET
# ============================================================================

print("=" * 70)
print("VALIDATION: Testing best parameters on all loaded races")
print("=" * 70)
print()

final_score = score_params(races, use_offsets, use_degs,
                           deg_power=use_power, temp_ref=temp_best_ref,
                           temp_coeff=temp_best_coeff)
print(f"  Final accuracy on {len(races)} races: {final_score:.1%}")
print()

# Also test on test cases
TEST_DIR = "data/test_cases"
if not os.path.exists(TEST_DIR):
    TEST_DIR = "box-box-box/data/test_cases"

test_correct = 0
test_total = 0
for i in range(1, 101):
    input_path = os.path.join(TEST_DIR, "inputs", f"test_{i:03d}.json")
    expected_path = os.path.join(TEST_DIR, "expected_outputs", f"test_{i:03d}.json")
    if os.path.exists(input_path) and os.path.exists(expected_path):
        with open(input_path) as f:
            tc = json.load(f)
        with open(expected_path) as f:
            exp = json.load(f)
        predicted = predict_race(tc, use_offsets, use_degs,
                                 deg_power=use_power, temp_ref=temp_best_ref,
                                 temp_coeff=temp_best_coeff)
        if predicted == exp["finishing_positions"]:
            test_correct += 1
        test_total += 1

print(f"  Test case accuracy: {test_correct}/{test_total} = {100*test_correct/test_total:.1f}%")
print()

# ============================================================================
# SUMMARY
# ============================================================================

print("=" * 70)
print("PHASE 1 SUMMARY — Discovered Parameters")
print("=" * 70)
print()
print(f"  Model type: {'quadratic' if use_power == 2 else 'linear'} degradation")
print(f"  Compound offsets: {use_offsets}")
print(f"  Degradation rates: {use_degs}")
print(f"  Temperature: ref={temp_best_ref}, coeff={temp_best_coeff}")
print(f"  Degradation power: {use_power}")
print()
print(f"  Historical accuracy: {final_score:.1%} ({len(races)} races)")
print(f"  Test case accuracy:  {test_correct}/{test_total}")
print()
print("  Next: Phase 2 will refine with scipy.optimize and more races.")
