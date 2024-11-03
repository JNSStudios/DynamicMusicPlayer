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
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.song_loaded = self.metronome_running = False
        self.current_beat = 0
        self.paused_position = 0.0
        self.song_start_time = None
        self.bpm = BPM
        self.metronome_enabled = False
        self.audio_data = None
        self.sample_rate = None
        self.stream = None
        self.current_position = 0  # To track current position in the audio buffer

        self.samples_per_beat = None

        self.setup_ui()
        self.load_song(SONG_FILE)
        self.load_metronome_sounds()

    def setup_ui(self):
        self.album_art_photo = self.load_image(ALBUM_ART_FILE, (200, 200))
        self.album_art = ttk.Label(self, image=self.album_art_photo, bootstyle="secondary")
        self.album_art.grid(row=0, column=0, padx=10, pady=10, rowspan=3, sticky="nw")

        ttk.Label(self, text="Song Title", font=("Helvetica", 20, "bold")).grid(row=0, column=1, sticky="w", padx=10, pady=(10, 0))
        ttk.Label(self, text="Artist\nAlbum (Year)", font=("Helvetica", 12)).grid(row=1, column=1, sticky="nw", padx=10)

        control_frame = ttk.Frame(self)
        control_frame.grid(row=3, column=0, columnspan=3, pady=20, sticky="ew")
        control_frame.columnconfigure(1, weight=1)
        self.create_control_buttons(control_frame)

        self.time_start_label = ttk.Label(self, text="0:00")
        self.time_start_label.grid(row=4, column=0, sticky="w", padx=10)
        self.progress_bar = ttk.Scale(self, orient="horizontal", from_=0, to=100)
        self.progress_bar.bind("<B1-Motion>", lambda event: self.update_position_during_drag(event))
        self.progress_bar.bind("<ButtonRelease-1>", lambda event: self.seek_song(event))  # When dragging is released
        self.progress_bar.grid(row=4, column=1, padx=10, sticky="ew")
        self.time_end_label = ttk.Label(self, text="0:00")
        self.time_end_label.grid(row=4, column=2, sticky="e", padx=10)

        bpm_meter_frame = ttk.Frame(self)
        bpm_meter_frame.grid(row=0, column=2, padx=10, pady=10, sticky="ne")
        self.bpm_label = ttk.Label(bpm_meter_frame, text=f"BPM: {self.bpm}", font=("Helvetica", 12))
        self.bpm_label.pack()
        self.bpm_indicator = ttk.Label(bpm_meter_frame, text="1", font=("Helvetica", 16, "bold"))
        self.bpm_indicator.pack()

        self.current_sample_label = ttk.Label(bpm_meter_frame, text="Current Sample Position: 0", font=("Helvetica", 12))
        self.current_sample_label.pack()
        self.samples_until_next_beat_label = ttk.Label(bpm_meter_frame, text="Samples Until Next Beat: 0", font=("Helvetica", 12))
        self.samples_until_next_beat_label.pack()

        self.samples_progress_bar = ttk.Progressbar(bpm_meter_frame, orient="horizontal", length=200, mode="determinate")
        self.samples_progress_bar.pack(pady=5)

        self.metronome_toggle = ttk.Checkbutton(bpm_meter_frame, text="Enable Metronome", bootstyle="success-round-toggle", command=self.toggle_metronome)
        self.metronome_toggle.pack()

        self.beat_dots_frame = ttk.Frame(bpm_meter_frame)
        self.beat_dots_frame.pack(pady=10)
        self.beat_dots = []
        for i in range(4):
            dot = ttk.Label(self.beat_dots_frame, text="\u2022", font=("Helvetica", 20), bootstyle="secondary-inverse")
            dot.grid(row=0, column=i, padx=5)
            self.beat_dots.append(dot)

        self.formula_label = ttk.Label(bpm_meter_frame, text="", font=("Helvetica", 10, "italic"))
        self.formula_label.pack(pady=10)

    def create_control_buttons(self, frame):
        ttk.Button(frame, text="\u23EE", width=3, command=self.prev_song).grid(row=0, column=0, padx=10)
        self.play_pause_button = ttk.Button(frame, text="\u25B6", width=3, command=self.play_pause_song)
        self.play_pause_button.grid(row=0, column=1, padx=10, sticky="ew")
        ttk.Button(frame, text="\u23ED", width=3, command=self.next_song).grid(row=0, column=2, padx=10)

    def load_image(self, filepath, size):
        try:
            return ImageTk.PhotoImage(Image.open(filepath).resize(size))
        except Exception as e:
            print(f"Error loading image: {e}")
            return None

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

        # Here we use the same logic as in scrubbing to ensure sync
        value = self.progress_bar.get()
        total_length = self.get_total_length()
        self.paused_position = (value / 100) * total_length  # Update paused_position as in seek_song
        self.current_position = int(self.paused_position * self.sample_rate * 2)  # Update the audio buffer position
        self.update_time_labels()  # Update the time labels
        self.run_metronome()  # Restart the metronome after recalculating position




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
                self.play_pause_button.config(text="\u25B6")  # Reset play/pause button to "play" state
                self.progress_bar.set(0)  # Reset the progress bar
                self.update_time_labels()  # Reset the time labels
                return

            # Calculate how much data to play in this chunk
            start_idx = self.current_position
            end_idx = min(start_idx + frames * 2, len(self.audio_data))

            # Slice the available data and reshape it
            audio_chunk = self.audio_data[start_idx:end_idx]

            # If there's not enough data to fill the entire buffer, zero-pad the rest
            if len(audio_chunk) < frames * 2:
                audio_chunk = np.pad(audio_chunk, (0, frames * 2 - len(audio_chunk)), 'constant')

            outdata[:] = np.reshape(audio_chunk, (frames, 2)) / 32768.0
            self.current_position += frames * 2


        self.stream = sd.OutputStream(callback=callback, channels=2, samplerate=self.sample_rate)
        self.stream.start()

    def load_metronome_sounds(self):
        try:
            # Load bar sound
            with wave.open(BAR_SOUND_FILE, 'rb') as wf:
                self.bar_sound_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                self.bar_sound_rate = wf.getframerate()

            # Load beat sound
            with wave.open(BEAT_SOUND_FILE, 'rb') as wf:
                self.beat_sound_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                self.beat_sound_rate = wf.getframerate()

        except Exception as e:
            print(f"Error loading metronome sounds: {e}")


    def toggle_metronome(self):
        self.metronome_enabled = not self.metronome_enabled

    def run_metronome(self):
        if not self.metronome_running:
            return  # Don't run metronome when song is paused

        # Calculate current position and sync the metronome accordingly
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

        for i, dot in enumerate(self.beat_dots):
            dot.config(bootstyle="secondary-inverse")  # Reset dots to gray

        if beat_position != self.current_beat:
            self.current_beat = beat_position
            self.bpm_indicator.config(text=f"Bar: {bar_number} Beat: {self.current_beat}")

            for i, dot in enumerate(self.beat_dots):
                color = "warning" if i == 0 else "info"
                if i + 1 == self.current_beat:
                    dot.config(bootstyle=color)
                else:
                    dot.config(bootstyle="secondary-inverse")

            if self.metronome_enabled:
                if self.current_beat == 1:
                    sd.play(self.bar_sound_data, samplerate=self.bar_sound_rate)
                else:
                    sd.play(self.beat_sound_data, samplerate=self.beat_sound_rate)

        self.metronome_id = self.after(10, self.run_metronome)  # Schedule the next metronome beat




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
        """Update song position and sample info as the playhead is being dragged."""
        if self.song_loaded:
            value = self.progress_bar.get()
            total_length = self.get_total_length()
            self.paused_position = (value / 100) * total_length
            self.current_position = int(self.paused_position * self.sample_rate * 2)  # Move to the correct position in the buffer
            self.update_time_labels()

            # Update metronome information during drag
            current_sample = self.paused_position * self.sample_rate
            self.current_sample_label.config(text=f"Current Sample Position: {int(current_sample)}")
            samples_until_next_beat = self.samples_per_beat - (current_sample % self.samples_per_beat)
            self.samples_until_next_beat_label.config(text=f"Samples Until Next Beat: {int(samples_until_next_beat)}")
            progress = ((self.samples_per_beat - samples_until_next_beat) / self.samples_per_beat) * 100
            self.samples_progress_bar['value'] = progress

    def get_sample_rate(self, filepath):
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as f:
                return f.getframerate()
        except Exception as e:
            print(f"Error getting sample rate: {e}")
            return 44100

    def seek_song(self, event):
        if self.song_loaded:
            was_playing = self.metronome_running
            if self.stream:
                self.stream.stop()
            value = self.progress_bar.get()
            total_length = self.get_total_length()
            self.paused_position = (value / 100) * total_length
            self.current_position = int(self.paused_position * self.sample_rate * 2)  # Move to the correct position in the buffer
            self.song_start_time = None  # Reset start time
            self.update_time_labels()
            self.time_start_label.config(text=time.strftime('%M:%S', time.gmtime(self.paused_position)))

            if was_playing:
                self.play_audio()
                self.song_start_time = time.time()
                self.metronome_running = True
                self.play_pause_button.config(text="\u23F8")
                self.update_progress_bar()
                self.run_metronome()  # Restart the metronome after seek
            else:
                self.metronome_running = False
                self.play_pause_button.config(text="\u25B6")
                self.after_cancel(self.metronome_id)  # Stop the metronome until playback resumes


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
