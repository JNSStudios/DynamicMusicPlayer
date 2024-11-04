import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
import time
import sounddevice as sd
import wave
import numpy as np
from PIL import Image, ImageTk
import contextlib
import threading
import logging

# Configure logging for debugging purposes
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

# Constants
SONG_FILE = "MusicFiles/The Hand That Feeds/The Hand That Feeds (OG).wav"  # Path to the song file
ALBUM_ART_FILE = "MusicFiles/The Hand That Feeds/withteeth.jpeg"  # Path to the album art file
BPM = 128  # Beats per minute for the song
BAR_SOUND_FILE = "bar.wav"  # Path to the bar sound file for metronome
BEAT_SOUND_FILE = "beat.wav"  # Path to the beat sound file for metronome


class MusicPlayerApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Dynamic Music Player")
        self.geometry("1400x800")

        # Initialize state variables
        self.song_loaded = self.metronome_running = False  # Flags to track song and metronome status
        self.current_beat = 0  # Track the current beat
        self.paused_position = 0.0  # Position where the song was paused
        self.song_start_time = None  # Track the start time of the song
        self.bpm = BPM  # Default BPM value
        self.metronome_clicks_enabled = False  # Track if metronome clicks are enabled
        self.display_metronome_enabled = False  # Ensure metronome display is off at launch
        self.audio_data = None  # Loaded audio data
        self.sample_rate = None  # Audio sample rate
        self.stream = None  # Audio stream for playback
        self.current_position = 0  # Track current playback position
        self.samples_per_beat = None  # Number of samples per beat (calculated based on BPM)
        self.metronome_id = None  # Track metronome ID for scheduling cancellation
        self.is_scrubbing = False  # Track if user is scrubbing the progress bar
        self.stop_threads = False  # Control thread termination
        self.was_playing_before_scrub = False  # Track if song was playing before scrubbing started

        # Setup the user interface
        self.setup_ui()
        self.load_song(SONG_FILE)  # Load the song
        self.load_metronome_sounds()  # Load metronome sounds

    def setup_ui(self):
        # Create a custom style for larger buttons
        style = ttk.Style()
        style.configure("Large.TButton", font=("Helvetica", 30))  # Larger font for control buttons

        # Main Vertical Stack Layout
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Horizontal Stack: Album Art & Song Info (Vertical Stack) + Metronome Display
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=10)

        # Album Art on the left
        self.album_art_photo = self.load_image(ALBUM_ART_FILE, (400, 400))  # Load and resize album art
        album_art_label = ttk.Label(top_frame, image=self.album_art_photo)  # Display album art
        album_art_label.pack(side="left", padx=20)

        # Vertical Stack for Song Info (Song Title, Artist, Album, Year)
        info_frame = ttk.Frame(top_frame)
        info_frame.pack(side="left", padx=20, pady=10)

        # Song Title (left-aligned)
        song_title = ttk.Label(info_frame, text="The Hand That Feeds", font=("Helvetica", 24, "bold"),
                            background="#1C1C1E", foreground="white")
        song_title.pack(anchor="w")  # Left-aligned

        # Artist, Album, Year (left-aligned)
        artist_info = ttk.Label(info_frame, text="Nine Inch Nails • With Teeth (2005)",
                                font=("Helvetica", 14), background="#1C1C1E", foreground="gray")
        artist_info.pack(anchor="w")  # Left-aligned

        # Spacer to push the text higher relative to album art
        ttk.Frame(info_frame).pack(expand=True)

        # Metronome Debug Section (now placed in the top right)
        self.metronome_frame = ttk.Frame(top_frame)
        self.metronome_frame.pack(side="right", padx=20, pady=10)  # Positioned in top right of the main frame

        # BPM, Metronome data (added inside the frame)
        self.bpm_label = ttk.Label(self.metronome_frame, text=f"BPM: {self.bpm}", font=("Helvetica", 12),
                                background="#1C1C1E", foreground="white")
        self.bpm_label.pack()

        # Display bar and beat information
        self.bpm_indicator = ttk.Label(self.metronome_frame, text="Bar: 1 Beat: 1", font=("Helvetica", 16, "bold"),
                                    background="#1C1C1E", foreground="white")
        self.bpm_indicator.pack()

        # Metronome sample and progress data
        self.current_sample_label = ttk.Label(self.metronome_frame, text="Current Sample Position: 0",
                                            font=("Helvetica", 12), background="#1C1C1E", foreground="gray")
        self.current_sample_label.pack()

        # Display the number of samples until the next beat
        self.samples_until_next_beat_label = ttk.Label(self.metronome_frame, text="Samples Until Next Beat: 0",
                                                    font=("Helvetica", 12), background="#1C1C1E", foreground="gray")
        self.samples_until_next_beat_label.pack()

        # Progress bar for beat progress
        self.samples_progress_bar = ttk.Progressbar(self.metronome_frame, orient="horizontal", length=300, mode="determinate")
        self.samples_progress_bar.pack(pady=5)

        # Toggle button for metronome clicks
        self.metronome_toggle = ttk.Checkbutton(self.metronome_frame, text="Enable Clicks", bootstyle="success-round-toggle",
                                                command=self.toggle_clicks)
        self.metronome_toggle.pack()

        # Initially hide the metronome based on the toggle state
        if not self.display_metronome_enabled:
            self.metronome_frame.pack_forget()

        # Horizontal Stack: Control Buttons (Previous, Play/Pause, Next) centered
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill="x", pady=10)

        # Create an inner frame to center the buttons horizontally
        inner_controls_frame = ttk.Frame(controls_frame)
        inner_controls_frame.pack(anchor="center")  # Anchor the frame to the center of the parent

        # Previous Button
        prev_button = ttk.Button(inner_controls_frame, text="⏮", width=3, command=self.prev_song, style="Large.TButton")
        prev_button.pack(side="left", padx=20)

        # Play/Pause Button
        self.play_pause_button = ttk.Button(inner_controls_frame, text="▶", width=3, command=self.play_pause_song, style="Large.TButton")
        self.play_pause_button.pack(side="left", padx=20)

        # Next Button
        next_button = ttk.Button(inner_controls_frame, text="⏭", width=3, command=self.next_song, style="Large.TButton")
        next_button.pack(side="left", padx=20)

        # Horizontal Stack: Playbar (Elapsed Time, Progress Bar, Total Time)
        playbar_frame = ttk.Frame(main_frame)
        playbar_frame.pack(fill="x", pady=10)

        # Elapsed Time
        self.time_start_label = ttk.Label(playbar_frame, text="0:00", font=("Helvetica", 14), background="#1C1C1E", foreground="gray")
        self.time_start_label.pack(side="left", padx=10)

        # Song Scrubbing Progress Bar
        self.progress_bar = ttk.Scale(playbar_frame, orient="horizontal", from_=0, to=100, length=800, style="TScale")
        # Bind mouse events to handle scrubbing actions
        self.progress_bar.bind("<B1-Motion>", lambda event: self.update_position_during_drag(event))
        self.progress_bar.bind("<Button-1>", lambda event: self.start_scrubbing())
        self.progress_bar.bind("<ButtonRelease-1>", lambda event: self.seek_song(event))
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=10)

        # Total Time
        self.time_end_label = ttk.Label(playbar_frame, text="0:00", font=("Helvetica", 14), background="#1C1C1E", foreground="gray")
        self.time_end_label.pack(side="left", padx=10)

        # Horizontal Stack: Debug Metronome Toggle
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=10)

        # Metronome Display Toggle
        self.display_metronome_toggle = ttk.Checkbutton(bottom_frame, text="Display Metronome",
                                                        bootstyle="info-round-toggle", command=self.toggle_display_metronome)
        self.display_metronome_toggle.pack(side="left", padx=20)

    def toggle_display_metronome(self):
        # Toggle the visibility of the metronome frame
        logging.debug(f"Toggling display metronome: currently {'enabled' if self.display_metronome_enabled else 'disabled'}")
        self.display_metronome_enabled = not self.display_metronome_enabled
        if self.display_metronome_enabled:
            self.metronome_frame.pack(side="right")  # Show the metronome info using pack on the right
        else:
            self.metronome_frame.pack_forget()  # Hide the metronome info using pack_forget()

    def load_image(self, filepath, size):
        # Load and resize the image for album art
        logging.debug(f"Loading image from {filepath} with size {size}")
        try:
            return ImageTk.PhotoImage(Image.open(filepath).resize(size))
        except Exception as e:
            logging.error(f"Error loading image: {e}")
            return None

    def toggle_clicks(self):
        # Toggle the metronome click sounds
        self.metronome_clicks_enabled = not self.metronome_clicks_enabled
        logging.debug(f"Metronome clicks {'enabled' if self.metronome_clicks_enabled else 'disabled'}")

    def play_pause_song(self):
        # Play or pause the song based on current state
        logging.debug("Play/Pause button pressed")
        if not self.song_loaded:
            logging.warning("No song loaded")
            return
        if self.metronome_running:
            self.pause_song()
        else:
            self.start_song()

    def start_song(self):
        # Start playing the song
        logging.debug("Starting song")
        if self.stream is not None and self.stream.active:
            logging.debug("Stream is already active. No need to start again.")
        else:
            self.play_audio()  # Start the audio stream

        self.song_start_time = time.time()  # Set the start time to the current time
        self.metronome_running = True  # Set metronome to running
        self.stop_threads = False  # Reset thread stop flag
        self.play_pause_button.config(text="⏸")  # Update button to pause icon
        self.update_time_labels()  # Update time labels
        self.update_progress_bar()  # Start updating the progress bar

        # Ensure sync during scrubbing
        value = self.progress_bar.get()
        total_length = self.get_total_length()
        self.paused_position = (value / 100) * total_length
        self.current_position = int(self.paused_position * self.sample_rate * 2)
        self.update_time_labels()

        # Start metronome thread
        self.run_metronome()

    def pause_song(self):
        # Pause the song and stop the audio stream
        logging.debug("Pausing song")
        if self.stream and self.stream.active:
            try:
                self.stream.stop()  # Stop playback
                logging.debug("Audio stream stopped successfully")
            except Exception as e:
                logging.error(f"Failed to stop audio stream: {e}")
        self.paused_position += (time.time() - self.song_start_time)  # Update paused position
        logging.debug(f"Song paused at position: {self.paused_position}")
        self.song_start_time = None
        self.metronome_running = False
        self.stop_threads = True  # Signal threads to stop
        self.play_pause_button.config(text="▶")  # Update button to play icon

        # Cancel the metronome loop if it's running
        if self.metronome_id is not None:
            try:
                self.after_cancel(self.metronome_id)
                self.metronome_id = None  # Reset after canceling
            except ValueError:
                logging.warning("Metronome ID was invalid when trying to cancel")
                self.metronome_id = None

    def load_song(self, filepath):
        # Load song from file
        logging.debug(f"Loading song from {filepath}")
        try:
            with wave.open(filepath, 'rb') as wf:
                self.sample_rate = wf.getframerate()
                self.samples_per_beat = int((60 / self.bpm) * self.sample_rate)  # Calculate samples per beat
                self.audio_data = wf.readframes(wf.getnframes())
                self.audio_data = np.frombuffer(self.audio_data, dtype=np.int16)  # Convert audio data to numpy array
            self.song_loaded = True
            self.update_time_labels()  # Update time labels after loading the song
            logging.debug("Song loaded successfully")
        except Exception as e:
            logging.error(f"Error loading song: {e}")

    def play_audio(self):
        # Play audio through a callback function to handle chunks of audio data
        def audio_callback(outdata, frames, time, status):
            if self.current_position >= len(self.audio_data):
                # Stop the stream and reset position when the end of the song is reached
                logging.debug("End of song reached. Stopping audio stream.")
                self.stop_audio_stream()
                self.current_position = 0
                self.paused_position = 0.0
                self.song_start_time = None
                self.metronome_running = False
                self.stop_threads = True  # Signal threads to stop
                self.play_pause_button.config(text="▶")
                self.after(0, lambda: self.progress_bar.set(0))  # Reset progress bar to zero
                self.update_time_labels()
                return

            # Calculate how much data to play in this chunk
            start_idx = max(0, self.current_position)
            end_idx = min(start_idx + frames * 2, len(self.audio_data))

            # Slice the available data and reshape it
            audio_chunk = self.audio_data[start_idx:end_idx]

            # Zero-pad if needed
            if len(audio_chunk) < frames * 2:
                audio_chunk = np.pad(audio_chunk, (0, frames * 2 - len(audio_chunk)), 'constant')

            outdata[:] = np.reshape(audio_chunk, (frames, 2)) / 32768.0  # Normalize audio output
            self.current_position += frames * 2

        # Stop any existing stream before starting a new one
        logging.debug("Stopping any existing audio stream before starting a new one")
        self.stop_audio_stream()

        try:
            # Start a new audio output stream
            self.stream = sd.OutputStream(callback=audio_callback, channels=2, samplerate=self.sample_rate)
            self.stream.start()
            logging.debug("Audio stream started successfully")
        except Exception as e:
            logging.error(f"Error starting audio stream: {e}")

    def stop_audio_stream(self):
        # Stop the current audio stream
        if self.stream is not None and self.stream.active:
            try:
                self.stream.stop()
                self.stream.close()
                logging.debug("Audio stream stopped and closed successfully")
            except Exception as e:
                logging.error(f"Error stopping or closing audio stream: {e}")
            self.stream = None

    def load_metronome_sounds(self):
        # Load metronome sound files for bar and beat sounds
        logging.debug("Loading metronome sounds")
        try:
            with wave.open(BAR_SOUND_FILE, 'rb') as wf:
                self.bar_sound_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                self.bar_sound_rate = wf.getframerate()

            with wave.open(BEAT_SOUND_FILE, 'rb') as wf:
                self.beat_sound_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                self.beat_sound_rate = wf.getframerate()
            logging.debug("Metronome sounds loaded successfully")
        except Exception as e:
            logging.error(f"Error loading metronome sounds: {e}")

    def run_metronome(self):
        # Start the metronome in a separate thread
        logging.debug("Starting metronome")
        if not self.metronome_running:
            return

        def metronome_loop():
            logging.debug("Metronome loop started")
            while self.metronome_running and not self.stop_threads:
                try:
                    # Calculate the current sample position and beats
                    current_position = self.paused_position + (time.time() - self.song_start_time)
                    current_sample = current_position * self.sample_rate
                    beat_position = int((current_sample // self.samples_per_beat) % 4) + 1
                    bar_number = int((current_sample // self.samples_per_beat) // 4) + 1

                    # Safely update the metronome debug labels using self.after()
                    self.after(0, lambda: self.current_sample_label.config(text=f"Current Sample Position: {int(current_sample)}"))
                    samples_until_next_beat = self.samples_per_beat - (current_sample % self.samples_per_beat)
                    self.after(0, lambda: self.samples_until_next_beat_label.config(text=f"Samples Until Next Beat: {int(samples_until_next_beat)}"))

                    # Update the progress bar for the current beat
                    progress = ((self.samples_per_beat - samples_until_next_beat) / self.samples_per_beat) * 100
                    self.after(0, lambda: self.samples_progress_bar.config(value=progress))

                    if beat_position != self.current_beat:
                        logging.debug(f"Beat change detected: Bar {bar_number}, Beat {beat_position}")
                        self.current_beat = beat_position
                        self.after(0, lambda: self.bpm_indicator.config(text=f"Bar: {bar_number} Beat: {self.current_beat}"))

                        # Play metronome sounds if enabled
                        if self.metronome_clicks_enabled:
                            if self.current_beat == 1:
                                logging.debug("Playing bar sound")
                                sd.play(self.bar_sound_data, samplerate=self.bar_sound_rate)  # Play bar sound
                            else:
                                logging.debug("Playing beat sound")
                                sd.play(self.beat_sound_data, samplerate=self.beat_sound_rate)  # Play beat sound

                    time.sleep(0.01)  # Sleep for 10 ms to not overload the CPU
                except Exception as e:
                    logging.error(f"Exception in metronome thread: {e}")

        # Start the metronome thread
        metronome_thread = threading.Thread(target=metronome_loop, daemon=True)
        metronome_thread.start()

    def update_progress_bar(self):
        # Update the progress bar based on current playback position
        logging.debug("Updating progress bar")
        if not self.song_loaded:
            return

        current_position = self.paused_position if self.song_start_time is None else (self.paused_position + (time.time() - self.song_start_time))
        total_length = self.get_total_length()
        progress = (current_position / total_length) * 100

        # Use self.after to safely update the GUI
        self.after(0, lambda: self.progress_bar.set(progress))
        self.after(0, lambda: self.time_start_label.config(text=time.strftime('%M:%S', time.gmtime(current_position))))

        # Schedule the next call to update_progress_bar after 500 ms
        if not self.is_scrubbing and not self.stop_threads:
            self.after(500, self.update_progress_bar)

    def update_position_during_drag(self, event):
        # Update the song position while scrubbing (dragging the progress bar)
        logging.debug("Updating position during drag")
        if self.song_loaded:
            value = self.progress_bar.get()
            total_length = self.get_total_length()
            self.paused_position = max(0, (value / 100) * total_length)
            self.current_position = max(0, int(self.paused_position * self.sample_rate * 2))
            self.update_time_labels()

            # Update metronome debug labels while scrubbing
            current_sample = self.paused_position * self.sample_rate
            self.after(0, lambda: self.current_sample_label.config(text=f"Current Sample Position: {int(current_sample)}"))
            samples_until_next_beat = self.samples_per_beat - (current_sample % self.samples_per_beat)
            self.after(0, lambda: self.samples_until_next_beat_label.config(text=f"Samples Until Next Beat: {int(samples_until_next_beat)}"))
            progress = ((self.samples_per_beat - samples_until_next_beat) / self.samples_per_beat) * 100
            self.after(0, lambda: self.samples_progress_bar.config(value=progress))

    def start_scrubbing(self):
        # Start scrubbing (user starts dragging the progress bar)
        logging.debug("Started scrubbing")
        self.is_scrubbing = True
        self.was_playing_before_scrub = self.metronome_running  # Set if the song is playing or not before scrubbing
        self.pause_song()


    def seek_song(self, event):
        # Seek the song to the new position after scrubbing is complete
        logging.debug("Seeking song to new position")
        if self.song_loaded:
            self.is_scrubbing = False

            value = self.progress_bar.get()
            total_length = self.get_total_length()
            self.paused_position = max(0, (value / 100) * total_length)
            self.current_position = max(0, int(self.paused_position * self.sample_rate * 2))
            self.update_time_labels()
            self.time_start_label.config(text=time.strftime('%M:%S', time.gmtime(self.paused_position)))

            # Cancel the metronome loop if it's running and has a valid ID
            if self.metronome_id is not None:
                try:
                    self.after_cancel(self.metronome_id)
                    self.metronome_id = None  # Reset after canceling
                except ValueError:
                    logging.warning("Metronome ID was invalid when trying to cancel")
                    self.metronome_id = None

            # Only resume playback if the song was playing before scrubbing started
            if self.was_playing_before_scrub:
                logging.debug("Restarting audio stream after seek")
                self.song_start_time = time.time()  # Reset start time
                self.metronome_running = True
                self.stop_threads = False  # Reset thread stop flag
                self.play_pause_button.config(text="⏸")
                self.play_audio()  # Start playback
                self.update_progress_bar()
                self.run_metronome()  # Start metronome again
            else:
                logging.debug("Keeping the song paused after seek")
                self.metronome_running = False
                self.stop_threads = True
                self.play_pause_button.config(text="▶")


    def update_time_labels(self):
        # Update the time labels for song duration
        logging.debug("Updating time labels")
        total_length = self.get_total_length()
        self.after(0, lambda: self.time_end_label.config(text=time.strftime('%M:%S', time.gmtime(total_length))))

    def get_total_length(self):
        # Get the total length of the loaded song in seconds
        logging.debug("Getting total length of the song")
        try:
            with contextlib.closing(wave.open(SONG_FILE, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return frames / float(rate)
        except Exception as e:
            logging.error(f"Error getting total length: {e}")
            return 0

    def prev_song(self):
        # Placeholder function for the previous song button
        logging.info("Previous button pressed")

    def next_song(self):
        # Placeholder function for the next song button
        logging.info("Next button pressed")


if __name__ == "__main__":
    logging.debug("Starting Music Player App")
    app = MusicPlayerApp()
    app.mainloop()
