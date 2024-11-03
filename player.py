import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
import time
import sounddevice as sd
import wave
import numpy as np
from PIL import Image, ImageTk
import contextlib

# Constants
SONG_FILE = "MusicFiles/The Hand That Feeds/The Hand That Feeds (OG).wav"
ALBUM_ART_FILE = "MusicFiles/The Hand That Feeds/withteeth.jpeg"
BPM = 128
BAR_SOUND_FILE = "bar.wav"
BEAT_SOUND_FILE = "beat.wav"


class MusicPlayerApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Dynamic Music Player")
        self.geometry("1400x800")

        self.song_loaded = self.metronome_running = False
        self.current_beat = 0
        self.paused_position = 0.0
        self.song_start_time = None
        self.bpm = BPM
        self.metronome_clicks_enabled = False
        self.display_metronome_enabled = False
        self.audio_data = None
        self.sample_rate = None
        self.stream = None
        self.current_position = 0

        self.samples_per_beat = None

        # Configure layout
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.setup_ui()
        self.load_song(SONG_FILE)
        self.load_metronome_sounds()

    def setup_ui(self):
        # Create a custom style for larger buttons
        style = ttk.Style()
        style.configure("Large.TButton", font=("Helvetica", 30))  # Larger font for control buttons

        # Set up grid layout and weights
        self.grid_rowconfigure(0, weight=1)  # Album art
        self.grid_rowconfigure(1, weight=1)  # Song title
        self.grid_rowconfigure(2, weight=1)  # Artist info
        self.grid_rowconfigure(3, weight=1)  # Control buttons
        self.grid_rowconfigure(4, weight=1)  # Progress bar (playbar)
        self.grid_rowconfigure(5, weight=1)  # Separator
        self.grid_rowconfigure(6, weight=1)  # Display Metronome Toggle
        self.grid_rowconfigure(7, weight=1)  # BPM/Metronome section
        self.grid_columnconfigure(1, weight=1)  # Ensure center column expands

        # Album Art
        self.album_art_photo = self.load_image(ALBUM_ART_FILE, (400, 400))
        self.album_art = ttk.Label(self, image=self.album_art_photo, bootstyle="secondary")
        self.album_art.grid(row=0, column=0, columnspan=3, padx=20, pady=(50, 20), sticky="n")

        # Song Title and Artist Info
        ttk.Label(self, text="The Hand That Feeds", font=("Helvetica", 24, "bold"),
                background="#1C1C1E", foreground="white").grid(row=1, column=0, columnspan=3, pady=(10, 5), sticky="n")
        ttk.Label(self, text="Nine Inch Nails • With Teeth (2005)", font=("Helvetica", 14),
                background="#1C1C1E", foreground="gray").grid(row=2, column=0, columnspan=3, pady=(0, 50), sticky="n")

        # Control Buttons Frame (row 3)
        control_frame = ttk.Frame(self, style="TFrame")
        control_frame.grid(row=3, column=0, columnspan=3, pady=20, padx=30, sticky="ew")
        self.create_control_buttons(control_frame)

        # Time Labels and Progress Bar (playbar) - row 4
        self.time_start_label = ttk.Label(self, text="0:00", font=("Helvetica", 12),
                                        background="#1C1C1E", foreground="gray")
        self.time_start_label.grid(row=4, column=0, sticky="w", padx=10, pady=10)

        self.progress_bar = ttk.Scale(self, orient="horizontal", from_=0, to=100, length=800, style="TScale")
        self.progress_bar.bind("<B1-Motion>", lambda event: self.update_position_during_drag(event))
        self.progress_bar.bind("<ButtonRelease-1>", lambda event: self.seek_song(event))
        self.progress_bar.grid(row=4, column=1, padx=10, pady=10, sticky="ew")

        self.time_end_label = ttk.Label(self, text="0:00", font=("Helvetica", 12),
                                        background="#1C1C1E", foreground="gray")
        self.time_end_label.grid(row=4, column=2, sticky="e", padx=10, pady=10)

        # Optional Separator (row 5)
        separator = ttk.Separator(self, orient="horizontal")
        separator.grid(row=5, column=0, columnspan=3, sticky="ew", pady=10)

        # Display Metronome Toggle (row 6)
        self.display_metronome_toggle = ttk.Checkbutton(self, text="Display Metronome",
                                                        bootstyle="info-round-toggle", command=self.toggle_display_metronome)
        self.display_metronome_toggle.grid(row=6, column=0, columnspan=3, padx=10, pady=10, sticky="n")

        # BPM and Metronome Section (row 7)
        self.metronome_frame = ttk.Frame(self)  # Wrap in a frame so we can hide/show easily
        self.metronome_frame.grid(row=7, column=0, columnspan=3, padx=10, pady=10, sticky="n")

        self.bpm_label = ttk.Label(self.metronome_frame, text=f"BPM: {self.bpm}", font=("Helvetica", 12),
                                background="#1C1C1E", foreground="white")
        self.bpm_label.pack()

        self.bpm_indicator = ttk.Label(self.metronome_frame, text="Bar: 1 Beat: 1", font=("Helvetica", 16, "bold"),
                                    background="#1C1C1E", foreground="white")
        self.bpm_indicator.pack()

        self.current_sample_label = ttk.Label(self.metronome_frame, text="Current Sample Position: 0", font=("Helvetica", 12),
                                            background="#1C1C1E", foreground="gray")
        self.current_sample_label.pack()

        self.samples_until_next_beat_label = ttk.Label(self.metronome_frame, text="Samples Until Next Beat: 0",
                                                    font=("Helvetica", 12), background="#1C1C1E", foreground="gray")
        self.samples_until_next_beat_label.pack()

        self.samples_progress_bar = ttk.Progressbar(self.metronome_frame, orient="horizontal", length=300, mode="determinate")
        self.samples_progress_bar.pack(pady=5)

        self.metronome_toggle = ttk.Checkbutton(self.metronome_frame, text="Enable Clicks",
                                                bootstyle="success-round-toggle", command=self.toggle_clicks)
        self.metronome_toggle.pack()

        self.formula_label = ttk.Label(self.metronome_frame, text="", font=("Helvetica", 10, "italic"),
                                    background="#1C1C1E", foreground="gray")
        self.formula_label.pack(pady=10)

        self.metronome_frame.grid_remove()  # Initially hide the metronome info

    def create_control_buttons(self, frame):
        prev_button = ttk.Button(frame, text="\u23EE", width=3, command=self.prev_song, style="Large.TButton")
        prev_button.grid(row=0, column=0, padx=20, pady=10)

        self.play_pause_button = ttk.Button(frame, text="\u25B6", width=3, command=self.play_pause_song, style="Large.TButton")
        self.play_pause_button.grid(row=0, column=1, padx=20, pady=10, sticky="ew")

        next_button = ttk.Button(frame, text="\u23ED", width=3, command=self.next_song, style="Large.TButton")
        next_button.grid(row=0, column=2, padx=20, pady=10)

        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=1)

    def toggle_display_metronome(self):
        self.display_metronome_enabled = not self.display_metronome_enabled
        if self.display_metronome_enabled:
            self.metronome_frame.grid()  # Show metronome info
        else:
            self.metronome_frame.grid_remove()  # Hide metronome info

    def load_image(self, filepath, size):
        try:
            return ImageTk.PhotoImage(Image.open(filepath).resize(size))
        except Exception as e:
            print(f"Error loading image: {e}")
            return None

    def toggle_clicks(self):
        self.metronome_clicks_enabled = not self.metronome_clicks_enabled

    def play_pause_song(self):
        if not self.song_loaded:
            print("No song loaded")
            return
        if self.metronome_running:
            self.pause_song()
        else:
            self.start_song()

    def start_song(self):
        if self.stream:
            self.stream.start()  # Resume playback
        else:
            self.play_audio()

        self.song_start_time = time.time()  # Reset the start time to the current time
        self.metronome_running = True
        self.play_pause_button.config(text="\u23F8")
        self.update_time_labels()
        self.update_progress_bar()

        # Ensure sync during scrubbing
        value = self.progress_bar.get()
        total_length = self.get_total_length()
        self.paused_position = (value / 100) * total_length
        self.current_position = int(self.paused_position * self.sample_rate * 2)
        self.update_time_labels()
        self.run_metronome()

    def pause_song(self):
        if self.stream:
            self.stream.stop()  # Stop playback
        self.paused_position += (time.time() - self.song_start_time)
        self.song_start_time = None
        self.metronome_running = False
        self.play_pause_button.config(text="\u25B6")
        self.after_cancel(self.metronome_id)  # Cancel the metronome loop to avoid desync

    def load_song(self, filepath):
        try:
            with wave.open(filepath, 'rb') as wf:
                self.sample_rate = wf.getframerate()
                self.samples_per_beat = int((60 / self.bpm) * self.sample_rate)
                self.audio_data = wf.readframes(wf.getnframes())
                self.audio_data = np.frombuffer(self.audio_data, dtype=np.int16)
            self.song_loaded = True
            self.update_time_labels()
        except Exception as e:
            print(f"Error loading song: {e}")

    def play_audio(self):
        def callback(outdata, frames, time, status):
            if self.current_position >= len(self.audio_data):
                # Stop the stream and reset position when the end of the song is reached
                self.stream.stop()
                self.current_position = 0
                self.paused_position = 0.0
                self.song_start_time = None
                self.metronome_running = False
                self.play_pause_button.config(text="\u25B6")
                self.progress_bar.set(0)
                self.update_time_labels()
                return

            # Calculate how much data to play in this chunk
            start_idx = self.current_position
            end_idx = min(start_idx + frames * 2, len(self.audio_data))

            # Slice the available data and reshape it
            audio_chunk = self.audio_data[start_idx:end_idx]

            # Zero-pad if needed
            if len(audio_chunk) < frames * 2:
                audio_chunk = np.pad(audio_chunk, (0, frames * 2 - len(audio_chunk)), 'constant')

            outdata[:] = np.reshape(audio_chunk, (frames, 2)) / 32768.0
            self.current_position += frames * 2

        self.stream = sd.OutputStream(callback=callback, channels=2, samplerate=self.sample_rate)
        self.stream.start()

    def load_metronome_sounds(self):
        try:
            with wave.open(BAR_SOUND_FILE, 'rb') as wf:
                self.bar_sound_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                self.bar_sound_rate = wf.getframerate()

            with wave.open(BEAT_SOUND_FILE, 'rb') as wf:
                self.beat_sound_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                self.beat_sound_rate = wf.getframerate()

        except Exception as e:
            print(f"Error loading metronome sounds: {e}")

    def run_metronome(self):
        if not self.metronome_running:
            return

        current_position = self.paused_position + (time.time() - self.song_start_time)
        current_sample = current_position * self.sample_rate
        beat_position = int((current_sample // self.samples_per_beat) % 4) + 1
        bar_number = int((current_sample // self.samples_per_beat) // 4) + 1

        self.current_sample_label.config(text=f"Current Sample Position: {int(current_sample)}")
        samples_until_next_beat = self.samples_per_beat - (current_sample % self.samples_per_beat)
        self.samples_until_next_beat_label.config(text=f"Samples Until Next Beat: {int(samples_until_next_beat)}")

        progress = ((self.samples_per_beat - samples_until_next_beat) / self.samples_per_beat) * 100
        self.samples_progress_bar['value'] = progress

        self.formula_label.config(text=f"Beat Number = int(({int(current_sample)} // {self.samples_per_beat}) % 4) + 1 = {beat_position}\n"
                                       f"Bar Number = int(({int(current_sample)} // {self.samples_per_beat}) // 4) + 1 = {bar_number}")

        if beat_position != self.current_beat:
            self.current_beat = beat_position
            self.bpm_indicator.config(text=f"Bar: {bar_number} Beat: {self.current_beat}")

            if self.metronome_clicks_enabled:
                if self.current_beat == 1:
                    sd.play(self.bar_sound_data, samplerate=self.bar_sound_rate)
                else:
                    sd.play(self.beat_sound_data, samplerate=self.beat_sound_rate)

        self.metronome_id = self.after(10, self.run_metronome)

    def update_progress_bar(self):
        if not self.song_loaded:
            return

        current_position = self.paused_position if self.song_start_time is None else (self.paused_position + (time.time() - self.song_start_time))
        total_length = self.get_total_length()
        progress = (current_position / total_length) * 100
        self.progress_bar.set(progress)
        self.time_start_label.config(text=time.strftime('%M:%S', time.gmtime(current_position)))

        self.after(500, self.update_progress_bar)

    def update_position_during_drag(self, event):
        if self.song_loaded:
            value = self.progress_bar.get()
            total_length = self.get_total_length()
            self.paused_position = (value / 100) * total_length
            self.current_position = int(self.paused_position * self.sample_rate * 2)
            self.update_time_labels()

            current_sample = self.paused_position * self.sample_rate
            self.current_sample_label.config(text=f"Current Sample Position: {int(current_sample)}")
            samples_until_next_beat = self.samples_per_beat - (current_sample % self.samples_per_beat)
            self.samples_until_next_beat_label.config(text=f"Samples Until Next Beat: {int(samples_until_next_beat)}")
            progress = ((self.samples_per_beat - samples_until_next_beat) / self.samples_per_beat) * 100
            self.samples_progress_bar['value'] = progress

    def seek_song(self, event):
        if self.song_loaded:
            was_playing = self.metronome_running
            if self.stream:
                self.stream.stop()
            value = self.progress_bar.get()
            total_length = self.get_total_length()
            self.paused_position = (value / 100) * total_length
            self.current_position = int(self.paused_position * self.sample_rate * 2)
            self.song_start_time = None
            self.update_time_labels()
            self.time_start_label.config(text=time.strftime('%M:%S', time.gmtime(self.paused_position)))

            if was_playing:
                self.play_audio()
                self.song_start_time = time.time()
                self.metronome_running = True
                self.play_pause_button.config(text="\u23F8")
                self.update_progress_bar()
                self.run_metronome()
            else:
                self.metronome_running = False
                self.play_pause_button.config(text="\u25B6")
                self.after_cancel(self.metronome_id)

    def update_time_labels(self):
        total_length = self.get_total_length()
        self.time_end_label.config(text=time.strftime('%M:%S', time.gmtime(total_length)))

    def get_total_length(self):
        try:
            with contextlib.closing(wave.open(SONG_FILE, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return frames / float(rate)
        except Exception as e:
            print(f"Error getting total length: {e}")
            return 0

    def prev_song(self):
        print("Previous button pressed")

    def next_song(self):
        print("Next button pressed")


if __name__ == "__main__":
    app = MusicPlayerApp()
    app.mainloop()
