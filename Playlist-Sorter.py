import os
import re
from typing import List, Tuple
import eyed3
from pathlib import Path
import sys

# Funktion zum Auslesen von BPM und Key aus einer MP3-Datei
def get_bpm_and_key(file_path: Path) -> Tuple[int, str]:
    try:
        audiofile = eyed3.load(file_path)
        bpm = int(re.search(r'\d+', str(audiofile.tag.bpm)).group()) if audiofile.tag.bpm else 0
        key = ""
        if audiofile.tag and audiofile.tag.comments:
            for comment in audiofile.tag.comments:
                match = re.search(r"\d+\w+", comment.text)
                if match:
                    key = match.group()
                    break
        return bpm, key
    except Exception as e:
        print(f"Fehler beim Lesen der Datei {file_path}: {e}")
        return 0, ""

# Funktion zum Einlesen von MP3-Dateipfaden aus einer M3U-Datei
def read_m3u(file_path: Path) -> List[Tuple[Path, str, int]]:
    songs = []
    base_dir = file_path.parent
    with file_path.open('r', encoding='ansi', errors='ignore') as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#"):
                mp3_path = base_dir / line
                if mp3_path.exists():
                    bpm, key = get_bpm_and_key(mp3_path)
                    songs.append((mp3_path, key, bpm))
    return songs

# Camelot Wheel Nachbarn bestimmen
def camelot_neighbors(key: str) -> List[str]:
    match = re.match(r"(\d+)([AB])", key)
    if not match:
        return []
    num, scale = int(match.group(1)), match.group(2)
    return [
        f"{num}{scale}",
        f"{(num % 12) + 1}{scale}",
        f"{(num - 2) % 12 + 1}{scale}",
        f"{num}{'A' if scale == 'B' else 'B'}"
    ]

# Songs sortieren
def sort_songs(songs: List[Tuple[Path, str, int]]) -> List[Tuple[Path, str, int]]:
    songs.sort(key=lambda x: x[2])
    sorted_list = [songs.pop(0)]
    
    while songs:
        last_song = sorted_list[-1]
        possible_songs = [song for song in songs if song[1] in camelot_neighbors(last_song[1])]
        next_song = min(possible_songs, key=lambda x: abs(x[2] - last_song[2])) if possible_songs else min(songs, key=lambda x: abs(x[2] - last_song[2]))
        sorted_list.append(next_song)
        songs.remove(next_song)
    
    # Füge verbleibende Songs ans Ende der sortierten Liste an
    sorted_list.extend(songs)
    
    return sorted_list

# Funktion zum Schreiben der sortierten Playlist in eine neue M3U-Datei
def write_m3u(file_path: Path, songs: List[Tuple[Path, str, int]]):
    with file_path.open('w', encoding='utf-8') as file:
        for song in songs:
            file.write(f"{song[0]}\n")

# Hauptfunktion
def main(input_file: Path, output_file: Path):
    print(f"Lesen der M3U-Datei: {input_file}...")
    songs = read_m3u(input_file)
    if not songs:
        print("Keine gültigen Songs in der M3U-Datei gefunden!")
        return
    print(f"{len(songs)} Songs gefunden. Sortierung wird durchgeführt...")
    sorted_songs = sort_songs(songs)
    write_m3u(output_file, sorted_songs)
    print(f"Sortierte Playlist wurde in '{output_file}' gespeichert.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Bitte geben Sie den Dateinamen als einziges Argument an.")
        sys.exit(1)
    
    #script_dir = Path(__file__).resolve().parent
    script_dir = Path(sys.executable).resolve().parent
    file_name = sys.argv[1]

    input_file = script_dir / file_name
    output_file = input_file.with_stem(input_file.stem + "_sorted")
    main(input_file, output_file)