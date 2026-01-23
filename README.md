# Harmonic Playlist Optimizer

This tool optimizes the order of an M3U playlist based on harmonic mixing rules (Camelot Wheel compatibility) and strict tempo progression. Unlike simple sorting algorithms, this tool uses Simulated Annealing to find a global optimum for the entire playlist flow.

## Requirements

To run this tool, you must have the following installed:

1. **Python 3.x** (Ensure the `python` command is accessible via your system's PATH).

2. The **`mutagen`** library for reading MP3 tags: `pip install mutagen`

## Tagging Requirements

The Python script relies on the following tags being present in your MP3 files:

| Data              | Tag Location         | Format/Rule                          |
| ----------------- | -------------------- | ------------------------------------ |
| **BPM** (Tempo)   | `TBPM` or `TXXX:BPM` | Must be an integer (e.g., `128`).    |
| **Key** (Camelot) | `COMM` (Comment)     | Must be the first word (e.g., `8A`). |

The M3U playlist file is read using the robust **`latin-1`** encoding to correctly handle most Western European characters.

## Usage

### 1. Setup

Open the **`_sort.bat`** file and verify the constant `SORT_SCRIPT_PATH` points correctly to the absolute location of your Python file (`playlist-sorter.py`): `SET "SORT_SCRIPT_PATH=path\to\playlist-sorter.py"`

### 2. Execution

1. Double-click the **`_sort.bat`** file.

2. The script will prompt you to enter the path to your input M3U file.

### 3. Output Generation

The optimized playlist is automatically created in the same directory as the input file, using the defined suffix:

- **Input**: `MyPartyMix.m3u`

- **Output**: `MyPartyMix_sorted.m3u`

The output file preserves the **relative or absolute path format** used in the original M3U file.

## Optimization Logic

The algorithm uses **Simulated Annealing**, a probabilistic technique for approximating the global optimum of a given function. Instead of just picking the next best track (which can lead to dead ends), this approach evaluates the total quality of the entire playlist.

1. **Initialization:** The playlist is shuffled randomly.

2. **Iteration:** The algorithm performs thousands (or millions) of operations, each swapping two random tracks.

3. **Evaluation:** If a swap results in a better harmonic flow (higher total score), it is kept. If it is worse, it might still be kept based on a "temperature" probability to prevent getting stuck in local optima.

4. **Cooling:** Over time, the algorithm becomes stricter, settling into the final optimized order.

### Scoring Criteria

The optimizer tries to maximize the total score based on these rules:

| Rule                 | Description                                                                             | Effect                                                          |
| -------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Key Harmony**      | Checks for Camelot Wheel compatibility (Same Key, +/- 1 Hour, or Relative Major/Minor). | High positive score for matches; negative score for mismatches. |
| **BPM Proximity**    | Checks if the BPM difference is within tolerance (default ±5).                          | Positive score for close matches.                               |
| **BPM Spread Limit** | Checks if the BPM difference exceeds 20%.                                               | Massive penalty to discourage such transitions.                 |

## Performance Tuning

You can adjust the quality and duration of the optimization by editing the `playlist-sorter.py` file directly in the "Configuration" section:

- **SA_ITERATIONS**: Controls the number of swap attempts.
  
  - Default: `150000` (Fast, good for small lists).
  
  - High Quality: Set to `1000000` or `5000000` for significantly better results (will take longer to run).

- **SA_COOLING_RATE**: Controls how fast the algorithm settles.
  
  - Default: `0.9995`.
  
  - High Quality: Set to `0.99995` (Requires increasing iterations).
