import os
import sys 
import math
import random
import copy
from mutagen.mp3 import MP3

# Handle imports for different mutagen versions
try:
    from mutagen.id3._frames import TXXX, TBPM, COMM
except ImportError:
    from mutagen.id3 import TXXX, TBPM, COMM

# --- Configuration ---
BPM_TOLERANCE = 5               # Maximum BPM difference for a "good" transition bonus
BPM_MAX_PERCENT_SPREAD = 0.30   # Maximum allowed BPM spread (default 20%) - Hard limit

# --- Simulated Annealing Settings ---
SA_INITIAL_TEMP = 10000.0       # Initial temperature (high enough to accept worse solutions initially)
SA_COOLING_RATE = 0.99995       # Cooling rate (closer to 1.0 = slower cooling, more precise)
SA_ITERATIONS = 5000000         # Number of optimization steps (increase for very large playlists)
# ---------------------

def camelot_to_tuple(camelot_key):
    """Converts a Camelot key string (e.g., '8A') into a tuple (Number, Letter)."""
    camelot_key = camelot_key.strip().upper()
    if not camelot_key: return None
    try:
        # Extract number
        num_str = "".join(filter(str.isdigit, camelot_key))
        if not num_str: return None
        num = int(num_str)
        
        # Extract letter
        letter = "".join(filter(str.isalpha, camelot_key))
        letter = letter if letter in ('A', 'B') else None
        
        return (num, letter)
    except Exception:
        return None

def is_harmonically_compatible(key1_tuple, key2_tuple):
    """
    Checks compatibility based on the Camelot Wheel.
    Rules: Same Key, +/- 1 Hour, or Relative Major/Minor (A<->B).
    """
    if not key1_tuple or not key2_tuple: return False
    num1, letter1 = key1_tuple
    num2, letter2 = key2_tuple

    # 1. Exact Match
    if num1 == num2 and letter1 == letter2: return True
    
    # 2. Key Change (±1 on the wheel)
    if letter1 == letter2:
        if num2 == (num1 % 12) + 1: return True
        if num2 == ((num1 - 2 + 12) % 12) + 1: return True
        
    # 3. Mode Change (Major <-> Minor)
    if num1 == num2 and letter1 != letter2: return True
    
    return False

def get_track_info(filepath, m3u_base_dir): 
    """Reads BPM and Key tags from the MP3 file."""
    
    # Resolve relative paths relative to the M3U location
    if not os.path.isabs(filepath):
        abs_filepath = os.path.join(m3u_base_dir, filepath)
    else:
        abs_filepath = filepath
        
    try:
        audio = MP3(abs_filepath)
        if not audio.tags: return {'path': filepath, 'bpm': None, 'key_tuple': None}

        # 1. Read BPM
        bpm = None
        if audio.tags.get('TBPM') and audio.tags['TBPM'].text:
            bpm = int(audio.tags['TBPM'].text[0].split('.')[0])
        elif audio.tags.get('TXXX:BPM') and audio.tags['TXXX:BPM'].text:
            bpm = int(audio.tags['TXXX:BPM'].text[0].split('.')[0])
            
        # 2. Read Key
        key_str = None
        if audio.tags.get('COMM::eng') and audio.tags['COMM::eng'].text:
            key_str = audio.tags['COMM::eng'].text[0]
        elif audio.tags.get('COMM:') and audio.tags['COMM:'].text:
            key_str = audio.tags['COMM:'].text[0]
        elif audio.tags.get('TKEY') and audio.tags['TKEY'].text:
            key_str = audio.tags['TKEY'].text[0]
            
        key_camelot = key_str.strip().split()[0] if key_str else None
        key_tuple = camelot_to_tuple(key_camelot) if key_camelot else None
        
        # Return struct with ORIGINAL path (for M3U writing) but extracted data
        return {'path': filepath, 'bpm': bpm, 'key_tuple': key_tuple} 
    except Exception:
        # Ignore errors (file missing or corrupt)
        return {'path': filepath, 'bpm': None, 'key_tuple': None}

def calculate_score(current_track, next_track):
    """Calculates the score for a specific transition between two tracks."""
    if not next_track['key_tuple'] or not next_track['bpm']: return -9999
    if not current_track['key_tuple'] or not current_track['bpm']: return -9999

    bpm_diff = abs(current_track['bpm'] - next_track['bpm'])
    max_diff = current_track['bpm'] * BPM_MAX_PERCENT_SPREAD
    
    # Strict rule: If BPM differs by more than 20%, apply heavy penalty
    if bpm_diff > max_diff: return -2000 

    # Key Harmony Score
    key_score = 0
    if is_harmonically_compatible(current_track['key_tuple'], next_track['key_tuple']):
        key_score = 1000 
    else:
        key_score = -500 
            
    # BPM Score
    bpm_score = 0
    if bpm_diff <= BPM_TOLERANCE: bpm_score = 100
    elif bpm_diff <= 10: bpm_score = 50
    else: bpm_score = -10
            
    # Variation Bonus (prefer small changes over exactly same BPM)
    if bpm_score > 0 and bpm_diff > 0: bpm_score += 10
            
    return key_score + bpm_score

# --- Simulated Annealing Logic ---

def calculate_total_cost(playlist):
    """
    Calculates the 'cost' of the entire playlist configuration.
    Simulated Annealing minimizes cost.
    Since we want to MAXIMIZE score, Cost = -(TotalScore).
    """
    total_score = 0
    # Iterate through list and sum up scores of all transitions
    for i in range(len(playlist) - 1):
        total_score += calculate_score(playlist[i], playlist[i+1])
    
    return -total_score # Return negative for minimization

def optimize_playlist_sa(tracks):
    """
    Optimizes the playlist using the Simulated Annealing algorithm.
    It attempts to find the global optimum rather than just the next best step.
    """
    if len(tracks) < 2:
        return tracks

    # Start with a random shuffle to avoid being stuck in the original sort order
    current_solution = copy.deepcopy(tracks)
    random.shuffle(current_solution)
    
    current_cost = calculate_total_cost(current_solution)
    
    best_solution = copy.deepcopy(current_solution)
    best_cost = current_cost
    
    temp = SA_INITIAL_TEMP
    
    print(f"Starting Optimization (Steps: {SA_ITERATIONS}, Start Temp: {temp})...")
    
    for i in range(SA_ITERATIONS):
        # Print progress every 10%
        if i % (SA_ITERATIONS // 10) == 0:
            sys.stdout.write(f"Step {i}/{SA_ITERATIONS} | Best Cost: {int(best_cost)}\r")
            sys.stdout.flush()

        # 1. Generate Neighbor: Swap two random tracks
        idx1, idx2 = random.sample(range(len(tracks)), 2)
        
        # Modify list in-place (faster than deepcopy inside loop)
        current_solution[idx1], current_solution[idx2] = current_solution[idx2], current_solution[idx1]
        
        # Calculate new cost
        # (Optimization note: could be faster by calculating only delta of the 2 cuts)
        neighbor_cost = calculate_total_cost(current_solution)
        
        delta = neighbor_cost - current_cost

        # 2. Acceptance Decision
        if delta < 0:
            # New solution is BETTER (lower cost -> higher score)
            current_cost = neighbor_cost
            if current_cost < best_cost:
                best_cost = current_cost
                best_solution = copy.deepcopy(current_solution)
        else:
            # New solution is WORSE. Do we accept it anyway?
            # Probability decreases as temp decreases and delta increases.
            if random.random() < math.exp(-delta / temp):
                current_cost = neighbor_cost
            else:
                # Reject: Revert swap
                current_solution[idx1], current_solution[idx2] = current_solution[idx2], current_solution[idx1]

        # 3. Cool down
        temp *= SA_COOLING_RATE
        if temp < 0.0001: break # Stop if temperature is near zero

    print(f"\nOptimization finished. Final Cost: {int(best_cost)} (Lower is better)")
    return best_solution

# --------------------------------------

def main():
    # 1. Parse Arguments
    if len(sys.argv) < 3:
        print("Error: Usage: python script.py <input.m3u> <output.m3u>")
        sys.exit(1)
        
    INPUT_PLAYLIST = sys.argv[1] 
    OUTPUT_PLAYLIST = sys.argv[2]
    
    # Determine base directory for resolving relative paths
    m3u_base_dir = os.path.dirname(os.path.abspath(INPUT_PLAYLIST))
    
    # 2. Read M3U File
    try:
        # 'latin-1' is robust for Western European special characters (umlauts)
        with open(INPUT_PLAYLIST, 'r', encoding='latin-1') as f:
            filepaths = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_PLAYLIST}' not found.")
        sys.exit(1)

    unique_filepaths = list(dict.fromkeys(filepaths))
    print(f"Reading {len(filepaths)} tracks...")
    
    # 3. Extract Tags
    tracks_info = [get_track_info(fp, m3u_base_dir) for fp in unique_filepaths]
    valid_tracks = [t for t in tracks_info if t['bpm'] is not None and t['key_tuple'] is not None]
    
    print(f"Found {len(valid_tracks)} valid tracks. Optimizing...")
    
    # 4. Run Optimization
    # Replacing the old 'sort_playlist' with the SA optimizer
    sorted_tracks = optimize_playlist_sa(valid_tracks)
    
    # 5. Write Output
    try:
        with open(OUTPUT_PLAYLIST, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for track in sorted_tracks:
                f.write(f"{track['path']}\n")
        print(f"Success! Optimized playlist saved to: '{OUTPUT_PLAYLIST}'")
    except Exception as e:
        print(f"Error writing output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()