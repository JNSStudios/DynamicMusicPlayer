import numpy as np
import wave
import contextlib
from scipy.io import wavfile
import time
import tkinter as tk
import threading
from pygame import mixer
import pyaudio
import matplotlib

SONG_FILE = "MusicFiles\The Hand That Feeds\The Hand That Feeds (OG).wav"
BPM = 128

class FastInteractiveBeatVisualizer:
    def __init__(self, root, song_file, bpm):
        self.root = root
        self.root.title("Fast Interactive Beat Visualizer")
        self.song_file = song_file
        self.bpm = bpm
        self.sample_rate, self.audio_data = self.load_audio_file(song_file)
        self.samples_per_beat = int((60 / bpm) * self.sample_rate)
        self.zoom_level = 1.0
        self.init_pygame_mixer()

        # Set up canvas for visualization
        self.canvas = tk.Canvas(self.root, width=1000, height=400, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Draw the initial waveform
        self.root.after(100, self.draw_waveform)  # Ensure canvas has been fully rendered

        # Bind mouse and keyboard events
        self.canvas.bind("<Button-1>", self.on_click)
        self.root.bind("<Up>", self.zoom_in)
        self.root.bind("<Down>", self.zoom_out)

        # Add pause button
        self.pause_button = tk.Button(self.root, text="Pause", command=self.pause_audio)
        self.pause_button.pack(side=tk.BOTTOM, pady=10)

        # Play position indicator
        self.play_position_line = None
        self.running = False

    def init_pygame_mixer(self):
        mixer.init()
        mixer.music.load(self.song_file)

    def load_audio_file(self, filepath):
        try:
            sample_rate, data = wavfile.read(filepath)
            if len(data.shape) > 1:  # Stereo
                data = np.mean(data, axis=1)  # Convert to mono
            return sample_rate, data
        except Exception as e:
            print(f"Error loading audio file: {e}")
            return None, None

    def draw_waveform(self):
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        total_samples = len(self.audio_data)
        samples_per_pixel = max(1, int((total_samples // width) / self.zoom_level))

        # Draw waveform
        points = []
        for x in range(width):
            start = int(x * samples_per_pixel)
            end = min(start + samples_per_pixel, total_samples)
            avg = np.mean(self.audio_data[start:end]) if end > start else 0
            y = height // 2 - int(avg / 32768 * (height // 2))
            y = max(0, min(height, y))  # Ensure y is within canvas bounds
            points.append((x, y))

        for i in range(1, len(points)):
            self.canvas.create_line(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1], fill="gray")

        # Draw beats
        beats = np.arange(0, total_samples, self.samples_per_beat)
        for beat in beats:
            x = int((beat / total_samples) * width / self.zoom_level)
            self.canvas.create_line(x, 0, x, height, fill="red", dash=(2, 2))

    def on_click(self, event):
        clicked_x = event.x
        width = self.canvas.winfo_width()
        total_samples = len(self.audio_data)
        clicked_sample = int((clicked_x / width) * total_samples * self.zoom_level)
        clicked_time = clicked_sample / self.sample_rate
        mixer.music.play(start=clicked_time)
        self.start_play_position_thread(clicked_sample)
        print(f"Playing from sample {clicked_sample}, which is {clicked_time:.2f} seconds.")

    def pause_audio(self):
        if mixer.music.get_busy():
            mixer.music.pause()
            self.running = False

    def start_play_position_thread(self, start_sample):
        self.running = True
        if self.play_position_line:
            self.canvas.delete(self.play_position_line)
        self.play_position_line = self.canvas.create_line(0, 0, 0, self.canvas.winfo_height(), fill="blue")
        threading.Thread(target=self.update_play_position, args=(start_sample,), daemon=True).start()

    def update_play_position(self, start_sample):
        while self.running and mixer.music.get_busy():
            current_position = mixer.music.get_pos() / 1000 * self.sample_rate + start_sample
            width = self.canvas.winfo_width()
            total_samples = len(self.audio_data)
            x = int((current_position / total_samples) * width / self.zoom_level)
            self.canvas.coords(self.play_position_line, x, 0, x, self.canvas.winfo_height())
            # Pulsating beat indicator
            if int(current_position) % self.samples_per_beat < self.sample_rate * 0.05:
                self.canvas.itemconfig(self.play_position_line, fill="yellow")
            else:
                self.canvas.itemconfig(self.play_position_line, fill="blue")
            time.sleep(0.05)

    def zoom_in(self, event):
        self.zoom_level = min(self.zoom_level * 1.5, 10.0)  # Limit zoom in
        self.draw_waveform()

    def zoom_out(self, event):
        self.zoom_level = max(self.zoom_level / 1.5, 1.0)  # Limit zoom out
        self.draw_waveform()

if __name__ == "__main__":
    root = tk.Tk()
    visualizer = FastInteractiveBeatVisualizer(root, SONG_FILE, BPM)
    root.mainloop()
