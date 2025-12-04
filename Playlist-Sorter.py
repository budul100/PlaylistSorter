import os
import sys 
from mutagen.mp3 import MP3
from mutagen.id3._frames import TXXX, TBPM, COMM

# --- Configuration ---
BPM_TOLERANCE = 5    # Maximum BPM difference for a "good" transition (for scoring)
BPM_MAX_PERCENT_SPREAD = 0.20 # Maximum allowed BPM spread (20%)
MIN_SCORE_THRESHOLD = 50 # Minimum score to continue the current set
# ---------------------

# ... (camelot_to_tuple and is_harmonically_compatible remain unchanged) ...

def camelot_to_tuple(camelot_key):
    """Converts a Camelot key (e.g., '8A', '12B') into a tuple (Number, Letter)."""
    camelot_key = camelot_key.strip().upper()
    if not camelot_key:
        return None
        
    try:
        # Extract the number part
        num_str = "".join(filter(str.isdigit, camelot_key))
        if not num_str:
            return None
        num = int(num_str)
        
        # Extract the letter part (A or B)
        letter = "".join(filter(str.isalpha, camelot_key))
        letter = letter if letter in ('A', 'B') else None
        
        return (num, letter)
    except Exception:
        return None

def is_harmonically_compatible(key1_tuple, key2_tuple):
    """
    Checks if two keys are compatible according to the Camelot Wheel rules.
    Compatibility includes: same key, +/- 1 on the wheel, or switching between Major/Minor.
    """
    if not key1_tuple or not key2_tuple:
        return False
        
    num1, letter1 = key1_tuple
    num2, letter2 = key2_tuple

    # 1. Perfect Harmonic Match (Same Key)
    if num1 == num2 and letter1 == letter2:
        return True

    # 2. Same Letter, one step on the Wheel (±1)
    if letter1 == letter2:
        # Check for +1 (e.g., 8 to 9, handles 12 to 1 wrap-around)
        if num2 == (num1 % 12) + 1:
            return True
        # Check for -1 (e.g., 8 to 7, handles 1 to 12 wrap-around)
        if num2 == ((num1 - 2 + 12) % 12) + 1:
            return True

    # 3. Switch between Major/Minor (A to B or B to A) with the same number
    if num1 == num2 and letter1 != letter2:
        return True

    return False

# Die Funktion erwartet nun den Basis-Pfad des M3U-Files
def get_track_info(filepath, m3u_base_dir): 
    """Reads BPM (TBPM or TXXX:BPM) and Key (COMM or TKEY) from ID3 tags robustly."""
    
    # NEU: Absolute Pfadgenerierung
    # Wenn der Pfad nicht bereits absolut ist, wird er relativ zum M3U-Basis-Ordner aufgelöst.
    if not os.path.isabs(filepath):
        abs_filepath = os.path.join(m3u_base_dir, filepath)
    else:
        abs_filepath = filepath
        
    try:
        audio = MP3(abs_filepath) # <-- Jetzt mit absolutem Pfad
        
        # Check if tags exist at all
        if not audio.tags:
            return {'path': filepath, 'bpm': None, 'key_tuple': None}

        # 1. BPM
        bpm = None
        if audio.tags.get('TBPM') and audio.tags['TBPM'].text:
            bpm = int(audio.tags['TBPM'].text[0].split('.')[0])
        elif audio.tags.get('TXXX:BPM') and audio.tags['TXXX:BPM'].text:
            bpm = int(audio.tags['TXXX:BPM'].text[0].split('.')[0])
            
        # 2. Key
        key_str = None
        if audio.tags.get('COMM::eng') and audio.tags['COMM::eng'].text:
            key_str = audio.tags['COMM::eng'].text[0]
        elif audio.tags.get('COMM:') and audio.tags['COMM:'].text:
            key_str = audio.tags['COMM:'].text[0]
        elif audio.tags.get('TKEY') and audio.tags['TKEY'].text:
            key_str = audio.tags['TKEY'].text[0]
            
        key_camelot = None
        if key_str:
            key_camelot = key_str.strip().split()[0]
            
        # 3. Key as tuple for calculation
        key_tuple = camelot_to_tuple(key_camelot) if key_camelot else None
        
        # Wichtig: Wir speichern den ORIGINALEN relativen/absoluten Pfad zurück, 
        # damit die neue M3U-Datei die gleichen Pfad-Referenzen verwendet wie die Eingabedatei.
        return {'path': filepath, 'bpm': bpm, 'key_tuple': key_tuple} 

    except Exception as e:
        # File could not be read (e.g., file not found, tags corrupt/missing)
        # print(f"Warning: Could not read file {abs_filepath}. Error: {e}") 
        return {'path': filepath, 'bpm': None, 'key_tuple': None}


# ... (calculate_score und sort_playlist bleiben unverändert) ...

def calculate_score(current_track, next_track):
    """Evaluates the suitability of the next track based on mixing criteria."""
    
    # Penalty if key or BPM is missing for the potential next track (Highest penalty)
    if not next_track['key_tuple'] or not next_track['bpm']:
        return -9999

    # --- 1. BPM Spread Check (STRICT RULE) ---
    bpm_diff = 0
    if next_track['bpm'] and current_track['bpm']:
        # Calculate the maximum allowed difference (20% of current BPM)
        max_diff = current_track['bpm'] * BPM_MAX_PERCENT_SPREAD
        bpm_diff = abs(current_track['bpm'] - next_track['bpm'])
        
        # If difference exceeds 20%, assign a strong penalty that forces a "new set"
        if bpm_diff > max_diff:
            return -1000 
            
    # --- 2. Key Harmony Check (High Priority) ---
    key_score = 0
    if next_track['key_tuple'] and current_track['key_tuple']:
        if is_harmonically_compatible(current_track['key_tuple'], next_track['key_tuple']):
            key_score = 1000  # Strong bonus for a mixable key transition
        else:
            key_score = -500 # Strong penalty for incompatible keys
            
    # --- 3. BPM Compatibility and Variation Check (Medium Priority) ---
    bpm_score = 0
    if next_track['bpm'] and current_track['bpm']:
        # 1. Very good BPM match (mixable)
        if bpm_diff <= BPM_TOLERANCE:
            bpm_score = 100
        # 2. Acceptable BPM match (± 10 BPM)
        elif bpm_diff <= 10:
            bpm_score = 50
        # 3. Small penalty for a jump within the 20% limit
        else:
            bpm_score = -10
            
        # Small bonus for tempo variation, as long as it's mixable
        if bpm_score > 0 and bpm_diff > 0:
            bpm_score += 10
            
    return key_score + bpm_score

def sort_playlist(tracks):
    """
    Dynamically sorts the tracks. If no suitable next track is found (score too low), 
    it starts a new set with the next available track (to ensure all songs are included).
    """
    if not tracks:
        return []

    # Start the playlist with the first track
    sorted_tracks = [tracks.pop(0)]
    
    while tracks:
        current_track = sorted_tracks[-1]
        best_score = -float('inf')
        best_next_index = -1
        
        # 1. Find the best next track for the current set
        for i, next_track in enumerate(tracks):
            score = calculate_score(current_track, next_track)
            
            if score > best_score:
                best_score = score
                best_next_index = i
        
        # 2. Check if the best score is above the threshold for a harmonic mix
        if best_score >= MIN_SCORE_THRESHOLD and best_next_index != -1:
            # Continue the current set
            sorted_tracks.append(tracks.pop(best_next_index))
        else:
            # Current set ends (no good transition found).
            # Start a new set with the next available track (the first one remaining)
            new_set_start_track = tracks.pop(0)
            sorted_tracks.append(new_set_start_track)
            
    return sorted_tracks

def main():
    # 1. Read the M3U file paths from command line arguments
    if len(sys.argv) < 3:
        print("Error: Please provide both the input and output M3U file paths.")
        print(f"Usage: python {sys.argv[0]} <path/to/input.m3u> <path/to/output.m3u>")
        sys.exit(1)
        
    INPUT_PLAYLIST = sys.argv[1] 
    OUTPUT_PLAYLIST = sys.argv[2]
    
    # NEU: Bestimme den Basis-Ordner des M3U-Files
    # Dies ist der Ordner, relativ zu dem die Song-Pfade in der M3U aufgelöst werden.
    m3u_base_dir = os.path.dirname(os.path.abspath(INPUT_PLAYLIST))
    
    # 2. Read the M3U file and extract unique file paths
    try:
        with open(INPUT_PLAYLIST, 'r', encoding='latin-1') as f:
            filepaths = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_PLAYLIST}' not found.")
        sys.exit(1)

    # Remove duplicates based on path
    unique_filepaths = list(dict.fromkeys(filepaths))
    duplicate_count = len(filepaths) - len(unique_filepaths)
    
    print(f"Reading {len(filepaths)} tracks from playlist...")
    if duplicate_count > 0:
        print(f"Removed {duplicate_count} duplicate track path(s).")
    
    # 3. Extract BPM and Key for each unique track
    # Jetzt wird m3u_base_dir übergeben
    tracks_info = [get_track_info(fp, m3u_base_dir) for fp in unique_filepaths]
    
    # Filter out tracks that could not be read (e.g. missing tags or invalid MP3s)
    # Beachte: Wenn eine Datei wegen eines ungültigen Pfades nicht gelesen werden kann,
    # wird sie hier ignoriert.
    valid_tracks = [t for t in tracks_info if t['bpm'] is not None and t['key_tuple'] is not None]
    invalid_count = len(tracks_info) - len(valid_tracks)
    print(f"Finished. Found {len(valid_tracks)} tracks with BPM/Key, {invalid_count} ignored.")
    
    # 4. Sort the tracks dynamically
    print("Sorting tracks harmonically and by tempo...")
    sorted_tracks = sort_playlist(valid_tracks)
    
    # 5. Create the new M3U file
    try:
        with open(OUTPUT_PLAYLIST, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n") # M3U Header
            for track in sorted_tracks:
                # Wichtig: Hier schreiben wir den originalen Pfad zurück,
                # um die relative Verlinkung in der neuen M3U zu erhalten.
                f.write(f"{track['path']}\n") 
        
        print(f"\nSuccess! The new harmonic playlist has been created: '{OUTPUT_PLAYLIST}'")
        print(f"   Total unique, valid tracks: {len(sorted_tracks)}")
        
    except Exception as e:
        print(f"Error writing output file '{OUTPUT_PLAYLIST}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()