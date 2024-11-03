import time
import threading

class Metronome:
    def __init__(self, bpm):
        self.bpm = bpm
        self.beat_interval = 60 / bpm
        self.running = False

    def start(self):
        self.running = True
        self.track_beats()

    def stop(self):
        self.running = False

    def track_beats(self):
        if not self.running:
            return
        print("Beat!")
        threading.Timer(self.beat_interval, self.track_beats).start()
        
    def pause(self):
        self.running = False

# Usage
metronome = Metronome(bpm=128)
metronome.start()
time.sleep(5)  # Run for a few seconds
metronome.stop()
