# Harmonic Playlist Sorter

This tool sorts an M3U playlist file based on harmonic mixing rules (Camelot Wheel compatibility) and strict tempo progression.

## Requirements

To run this tool, you must have the following installed:

1. **Python 3.x** (Ensure the `python` command is accessible via your system's PATH).
  
2. The **`mutagen`** library for reading MP3 tags:
  `pip install mutagen`

## Tagging Requirements

The Python script relies on the following tags being present in your MP3 files:

| Data | Tag Location | Format/Rule |
| --- | --- | --- |
| **BPM** (Tempo) | `TBPM` or `TXXX:BPM` | Must be an integer (e.g., `128`). |
| **Key** (Camelot) | `COMM` (Comment) | Must be the first word (e.g., `8A`). |

The M3U playlist file is read using the robust **`latin-1`** encoding to correctly handle most Western European characters (like German umlauts).

## Usage

### 1. Configuration

Open the **`_sort.bat`** file and verify the constant `SORT_SCRIPT_PATH` points correctly to the absolute location of your Python file (`playlist-sorter.py`):
`SET "SORT_SCRIPT_PATH=path\to\playlist-sorter.py"`

### 2. Execution

1. Double-click the **`_sort.bat`** file.
2. The script will prompt you to enter the path to your input M3U file.

### 3. Output Generation

The sorted playlist is automatically created in the same directory as the input file, using the defined suffix:
- **Input**: `MyPartyMix.m3u`
- **Output**: `MyPartyMix_sorted.m3u`
The output file preserves the **relative or absolute path format** used in the original M3U file.

## Sorting Logic

The algorithm uses a dynamic, score-based approach to ensure smooth, non-monotonous mixing.

### Hard Constraints

| Rule | Description | Penalty |
| --- | --- | --- |
| **BPM Spread** | The BPM difference between two consecutive tracks **must not exceed 20%** of the current track's BPM. | Rejection, forcing the start of a new set. |
| **Missing Tags** | Tracks missing BPM or Key information are ignored. | Rejection. |

### Scoring Priority

1. **Key Harmony (Highest Priority):** Strong bonus for harmonically compatible tracks (e.g., same key, +/- 1 on the wheel, or relative major/minor). Incompatible keys receive a heavy penalty.
  
2. **BPM Proximity:** Bonus for tracks within the defined ±5 BPM tolerance (`BPM_TOLERANCE`).
  
3. **Tempo Variation:** Small bonus for any slight BPM change within the allowed limit to prevent the mix from becoming too static.

All tracks with valid tags are guaranteed to be included in the final output, starting a new set if no harmonic transition is found.
