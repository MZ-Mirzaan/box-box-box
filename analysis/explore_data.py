#!/usr/bin/env python3
"""
Box Box Box — Phase 1: Data Exploration
========================================
Loads historical races, analyzes parameter ranges, and begins extracting
compound/degradation insights using pairwise driver comparisons.

Run from repository root:
  python analysis/explore_data.py
"""

import json
import os
from collections import Counter, defaultdict

# ============================================================================
# 1. LOAD DATA
# ============================================================================

DATA_DIR = "data/historical_races"
# Adjust if running from a different directory
if not os.path.exists(DATA_DIR):
    DATA_DIR = "box-box-box/data/historical_races"

def load_races(num_files=3):
    """Load races from the first N data files."""
    all_races = []
    files = sorted(os.listdir(DATA_DIR))
    for fname in files[:num_files]:
        path = os.path.join(DATA_DIR, fname)
        with open(path, 'r') as f:
            races = json.load(f)
            all_races.extend(races)
        print(f"  Loaded {fname}: {len(races)} races")
    return all_races

print("=" * 70)
print("PHASE 1: DATA EXPLORATION")
print("=" * 70)
print()

print("[1/6] Loading historical races...")
races = load_races(num_files=3)  # First 3000 races
print(f"  Total races loaded: {len(races)}")
print()

# ============================================================================
# 2. RACE CONFIG STATISTICS
# ============================================================================

print("[2/6] Race configuration statistics...")
print("-" * 50)

tracks = Counter()
total_laps_list = []
base_times = []
pit_times = []
temps = []

for race in races:
    cfg = race["race_config"]
    tracks[cfg["track"]] += 1
    total_laps_list.append(cfg["total_laps"])
    base_times.append(cfg["base_lap_time"])
    pit_times.append(cfg["pit_lane_time"])
    temps.append(cfg["track_temp"])

print(f"  Tracks: {dict(tracks)}")
print(f"  Total laps:    min={min(total_laps_list)}, max={max(total_laps_list)}, avg={sum(total_laps_list)/len(total_laps_list):.1f}")
print(f"  Base lap time: min={min(base_times):.1f}, max={max(base_times):.1f}, avg={sum(base_times)/len(base_times):.1f}")
print(f"  Pit lane time: min={min(pit_times):.1f}, max={max(pit_times):.1f}, avg={sum(pit_times)/len(pit_times):.1f}")
print(f"  Track temp:    min={min(temps)}, max={max(temps)}, avg={sum(temps)/len(temps):.1f}")
print()

# ============================================================================
# 3. STRATEGY PATTERNS
# ============================================================================

print("[3/6] Strategy patterns...")
print("-" * 50)

pit_count_dist = Counter()
compound_usage = Counter()
starting_compound = Counter()

for race in races:
    for pos_key, strategy in race["strategies"].items():
        num_pits = len(strategy["pit_stops"])
        pit_count_dist[num_pits] += 1
        starting_compound[strategy["starting_tire"]] += 1
        # Track all compounds used in the race
        current = strategy["starting_tire"]
        compound_usage[current] += 1
        for stop in strategy["pit_stops"]:
            compound_usage[stop["to_tire"]] += 1

print(f"  Pit stop distribution: {dict(sorted(pit_count_dist.items()))}")
print(f"  Starting compound:     {dict(starting_compound)}")
print(f"  Overall compound usage: {dict(compound_usage)}")
print()

# ============================================================================
# 4. PAIRWISE COMPARISON ANALYSIS (The "Cheat Code")
# ============================================================================

print("[4/6] Pairwise comparison analysis (extracting compound insights)...")
print("-" * 50)

def get_driver_stints(strategy, total_laps):
    """Convert a driver's strategy into a list of stints.
    Each stint: (compound, num_laps)
    """
    stints = []
    current_compound = strategy["starting_tire"]
    current_start = 1  # Lap 1

    for stop in sorted(strategy["pit_stops"], key=lambda s: s["lap"]):
        pit_lap = stop["lap"]
        stint_laps = pit_lap - current_start + 1
        stints.append((current_compound, stint_laps))
        current_compound = stop["to_tire"]
        current_start = pit_lap + 1

    # Final stint
    final_laps = total_laps - current_start + 1
    stints.append((current_compound, final_laps))
    return stints

def compute_compound_laps(strategy, total_laps):
    """Count how many laps were spent on each compound."""
    stints = get_driver_stints(strategy, total_laps)
    laps_per_compound = defaultdict(int)
    for compound, num_laps in stints:
        laps_per_compound[compound] += num_laps
    return dict(laps_per_compound)

# For each race, compare pairs of drivers to estimate compound effects
# Focus on simple cases: drivers with the same number of pit stops
# The idea: if two drivers have similar stint structures but different
# compounds, the finishing order reveals compound speed differences

# Track: for pairs on same number of pits, which compound combos win?
compound_wins = defaultdict(lambda: [0, 0])  # (compound_A, compound_B) -> [A_wins, B_wins]

for race in races:
    cfg = race["race_config"]
    total_laps = cfg["total_laps"]
    finishing = race["finishing_positions"]

    # Build driver info
    drivers = {}
    for pos_key, strategy in race["strategies"].items():
        did = strategy["driver_id"]
        drivers[did] = {
            "strategy": strategy,
            "stints": get_driver_stints(strategy, total_laps),
            "compound_laps": compute_compound_laps(strategy, total_laps),
            "num_pits": len(strategy["pit_stops"]),
            "finish_pos": finishing.index(did) + 1
        }

    # Compare 1-stop drivers with each other
    one_stop_drivers = [d for d in drivers.values() if d["num_pits"] == 1]
    for i, dA in enumerate(one_stop_drivers):
        for dB in one_stop_drivers[i+1:]:
            # Which compound did each use more?
            a_compounds = set(dA["compound_laps"].keys())
            b_compounds = set(dB["compound_laps"].keys())

            # Simple: compare starting compounds
            a_start = dA["strategy"]["starting_tire"]
            b_start = dB["strategy"]["starting_tire"]

            if a_start != b_start:
                winner = "A" if dA["finish_pos"] < dB["finish_pos"] else "B"
                pair = tuple(sorted([a_start, b_start]))
                if winner == "A":
                    idx = 0 if pair[0] == a_start else 1
                else:
                    idx = 0 if pair[0] == b_start else 1
                compound_wins[pair][idx] += 1

print("  Compound head-to-head (1-stop drivers, by starting compound):")
for pair, (wins_0, wins_1) in sorted(compound_wins.items()):
    total = wins_0 + wins_1
    print(f"    {pair[0]} vs {pair[1]}: {pair[0]} wins {wins_0}/{total} ({100*wins_0/total:.1f}%), "
          f"{pair[1]} wins {wins_1}/{total} ({100*wins_1/total:.1f}%)")
print()

# ============================================================================
# 5. STINT-BASED TOTAL TIME ANALYSIS
# ============================================================================

print("[5/6] Stint structure analysis (understanding race dynamics)...")
print("-" * 50)

# Analyze typical stint lengths per compound
stint_lengths = defaultdict(list)
for race in races:
    total_laps = race["race_config"]["total_laps"]
    for pos_key, strategy in race["strategies"].items():
        stints = get_driver_stints(strategy, total_laps)
        for compound, num_laps in stints:
            stint_lengths[compound].append(num_laps)

for compound in ["SOFT", "MEDIUM", "HARD"]:
    lengths = stint_lengths[compound]
    print(f"  {compound:6s} stint lengths: min={min(lengths):2d}, max={max(lengths):2d}, "
          f"avg={sum(lengths)/len(lengths):.1f}, count={len(lengths)}")
print()

# ============================================================================
# 6. TEMPERATURE CORRELATION
# ============================================================================

print("[6/6] Temperature correlation analysis...")
print("-" * 50)

# Group races by temperature and see if certain strategies perform better
# at different temps
temp_buckets = defaultdict(list)
for race in races:
    temp = race["race_config"]["track_temp"]
    total_laps = race["race_config"]["total_laps"]
    winner_id = race["finishing_positions"][0]
    # Find winner's strategy
    for pos_key, strategy in race["strategies"].items():
        if strategy["driver_id"] == winner_id:
            winner_start = strategy["starting_tire"]
            winner_pits = len(strategy["pit_stops"])
            temp_buckets[temp].append((winner_start, winner_pits))
            break

print("  Winner profiles by track temperature:")
for temp in sorted(temp_buckets.keys()):
    entries = temp_buckets[temp]
    starts = Counter(e[0] for e in entries)
    pits = Counter(e[1] for e in entries)
    total = len(entries)
    print(f"  Temp {temp}°C ({total:3d} races): "
          f"Start={dict(starts)}, "
          f"Pits={dict(sorted(pits.items()))}")

print()

# ============================================================================
# 7. FIRST ATTEMPT: Simple Formula Test
# ============================================================================

print("=" * 70)
print("BONUS: Testing simple formula against first 100 races")
print("=" * 70)
print()

# Try a very simple model:
# lap_time = base + compound_offset + degradation_rate * tire_age
# where tire_age starts at 1
#
# Initial guesses (to be refined in Phase 2):
COMPOUND_OFFSET_GUESS = {"SOFT": -0.4, "MEDIUM": 0.0, "HARD": 0.3}
DEGRADATION_RATE_GUESS = {"SOFT": 0.08, "MEDIUM": 0.04, "HARD": 0.02}

def simulate_race_simple(race, compound_offsets, deg_rates, temp_factor=0.0):
    """Simple lap-by-lap simulation with guessed parameters."""
    cfg = race["race_config"]
    base = cfg["base_lap_time"]
    pit_time = cfg["pit_lane_time"]
    total_laps = cfg["total_laps"]
    temp = cfg["track_temp"]

    driver_times = {}
    for pos_key, strategy in race["strategies"].items():
        did = strategy["driver_id"]
        stints = get_driver_stints(strategy, total_laps)
        total_time = len(strategy["pit_stops"]) * pit_time

        for compound, stint_laps in stints:
            offset = compound_offsets[compound]
            deg = deg_rates[compound]
            # Stint time with simple linear degradation
            # Each lap: base + offset + deg * age * (1 + temp_factor * (temp - 30))
            temp_mult = 1.0 + temp_factor * (temp - 30)
            for age in range(1, stint_laps + 1):
                lap_time = base + offset + deg * age * temp_mult
                total_time += lap_time

        driver_times[did] = total_time

    # Sort by total time
    sorted_drivers = sorted(driver_times.items(), key=lambda x: x[1])
    return [d[0] for d in sorted_drivers]

# Test on first 100 races
correct = 0
test_races = races[:100]
for race in test_races:
    predicted = simulate_race_simple(race, COMPOUND_OFFSET_GUESS, DEGRADATION_RATE_GUESS)
    expected = race["finishing_positions"]
    if predicted == expected:
        correct += 1

print(f"  Simple model accuracy (first 100 races): {correct}/100 = {correct}%")
print(f"  (This is with completely guessed parameters — Phase 2 will auto-fit)")
print()

# Also test with slight temperature factor
for tf in [0.005, 0.01, 0.02, 0.03]:
    correct = 0
    for race in test_races:
        predicted = simulate_race_simple(race, COMPOUND_OFFSET_GUESS, DEGRADATION_RATE_GUESS, temp_factor=tf)
        expected = race["finishing_positions"]
        if predicted == expected:
            correct += 1
    print(f"  With temp_factor={tf}: {correct}/100 correct")

print()
print("=" * 70)
print("Phase 1 exploration complete. Key findings will guide Phase 2 fitting.")
print("=" * 70)
