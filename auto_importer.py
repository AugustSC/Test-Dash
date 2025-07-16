import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from importer_pg_tracked_mentions import import_messages

class JsonHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith('.json'):
            return
        print(f"New JSON detected: {event.src_path}")
        try:
            import_messages(event.src_path)
            print(f"Imported {event.src_path}")
        except Exception as e:
            print(f"Error importing {event.src_path}: {e}")

if __name__ == "__main__":
    path = "data/exports"
    observer = Observer()
    observer.schedule(JsonHandler(), path, recursive=False)
    observer.start()
    print(f"Watching {path} for new JSON files...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()