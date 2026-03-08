import os
import hashlib
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def hash_file_sha256(path, chunk_size=1024 * 1024):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            sha.update(data)
    return sha.hexdigest()


def scan_directory(root_path, min_size, extensions, progress_callback=None):
    hash_map = {}

    total_files = 0
    for _, _, files in os.walk(root_path):
        total_files += len(files)

    processed = 0

    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            processed += 1
            full_path = os.path.join(dirpath, filename)

            if progress_callback:
                progress_callback(processed, total_files)

            try:
                if not os.path.isfile(full_path):
                    continue

                size = os.path.getsize(full_path)
                if size < min_size:
                    continue

                if extensions:
                    if not any(filename.lower().endswith(ext) for ext in extensions):
                        continue

                file_hash = hash_file_sha256(full_path)
                hash_map.setdefault(file_hash, []).append((full_path, size))

            except:
                continue

    return hash_map


def build_duplicate_groups(hash_map):
    return [entries for entries in hash_map.values() if len(entries) > 1]


# ------------------------------------------------------------
# GUI Klasse
# ------------------------------------------------------------

class DuplicateFileFinderGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Duplicate File Finder (DFF)")
        self.master.geometry("1100x750")

        self.selected_folder = tk.StringVar()
        self.base_folder = None

        self.duplicate_groups = []
        self.group_states = {}
        self.listbox_index_map = {}

        # Spinner
        self.spinner_running = False
        self.spinner_frames = ["|", "/", "-", "\\"]
        self.spinner_index = 0

        self.create_widgets()

    # --------------------------------------------------------
    # GUI Aufbau
    # --------------------------------------------------------
    def create_widgets(self):
        frame_top = tk.Frame(self.master)
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(frame_top, text="Startordner:", font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        tk.Entry(frame_top, textvariable=self.selected_folder, width=60).pack(side=tk.LEFT, padx=5)

        self.btn_choose = ttk.Button(frame_top, text="📂 Ordner wählen", command=self.choose_folder)
        self.btn_choose.pack(side=tk.LEFT, padx=5)

        self.btn_scan = ttk.Button(frame_top, text="🔍 Scannen", command=self.start_scan_thread)
        self.btn_scan.pack(side=tk.LEFT, padx=5)

        # Filter
        frame_filter = tk.Frame(self.master)
        frame_filter.pack(fill=tk.X, padx=10)

        tk.Label(frame_filter, text="Mindestgröße (MB):").pack(side=tk.LEFT)
        self.min_size_entry = tk.Entry(frame_filter, width=6)
        self.min_size_entry.insert(0, "0")
        self.min_size_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(frame_filter, text="Dateitypen (z.B. .jpg,.png):").pack(side=tk.LEFT)
        self.ext_entry = tk.Entry(frame_filter, width=25)
        self.ext_entry.pack(side=tk.LEFT, padx=5)

        # Fortschritt + Spinner
        frame_progress = tk.Frame(self.master)
        frame_progress.pack(fill=tk.X, padx=10, pady=5)

        self.progress = ttk.Progressbar(frame_progress, length=400)
        self.progress.pack(side=tk.LEFT, padx=5)

        self.progress_label = tk.Label(frame_progress, text="0%")
        self.progress_label.pack(side=tk.LEFT, padx=10)

        self.spinner_label = tk.Label(frame_progress, text="", font=("Consolas", 14))
        self.spinner_label.pack(side=tk.LEFT, padx=10)

        # Ergebnisliste
        frame_middle = tk.Frame(self.master)
        frame_middle.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(frame_middle, text="Gefundene Dubletten:", font=("Arial", 11, "bold")).pack(anchor="w")

        self.listbox = tk.Listbox(frame_middle, selectmode=tk.EXTENDED, font=("Consolas", 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind("<Double-Button-1>", self.toggle_group)

        scrollbar = tk.Scrollbar(frame_middle, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        # Aktionen
        frame_bottom = tk.Frame(self.master)
        frame_bottom.pack(fill=tk.X, padx=10, pady=10)

        self.summary_var = tk.StringVar(value="Noch keine Analyse durchgeführt.")
        tk.Label(frame_bottom, textvariable=self.summary_var, font=("Arial", 10)).pack(anchor="w")

        self.btn_select_all = ttk.Button(
            frame_bottom,
            text="🧹 Pro Gruppe: alle bis auf eine markieren",
            command=self.select_all_but_one
        )
        self.btn_select_all.pack(side=tk.LEFT, padx=5)

        self.btn_delete = ttk.Button(
            frame_bottom,
            text="🗑 Ausgewählte löschen",
            command=self.delete_selected
        )
        self.btn_delete.pack(side=tk.LEFT, padx=5)

    # --------------------------------------------------------
    # Spinner Animation
    # --------------------------------------------------------
    def start_spinner(self):
        self.spinner_running = True
        self.animate_spinner()

    def stop_spinner(self):
        self.spinner_running = False
        self.spinner_label.config(text="")

    def animate_spinner(self):
        if not self.spinner_running:
            return
        self.spinner_label.config(text=self.spinner_frames[self.spinner_index])
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.master.after(120, self.animate_spinner)

    # --------------------------------------------------------
    # Ordnerwahl
    # --------------------------------------------------------
    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.selected_folder.set(folder)

    # --------------------------------------------------------
    # Scan starten (Thread)
    # --------------------------------------------------------
    def start_scan_thread(self):
        self.disable_buttons()
        self.progress["value"] = 0
        self.progress_label.config(text="0%")
        self.start_spinner()

        thread = threading.Thread(target=self.scan, daemon=True)
        thread.start()

    def disable_buttons(self):
        self.btn_scan.config(state="disabled")
        self.btn_choose.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_delete.config(state="disabled")

    def enable_buttons(self):
        self.btn_scan.config(state="normal")
        self.btn_choose.config(state="normal")
        self.btn_select_all.config(state="normal")
        self.btn_delete.config(state="normal")

    # --------------------------------------------------------
    # Scan Logik
    # --------------------------------------------------------
    def scan(self):
        folder = self.selected_folder.get().strip()
        if not folder:
            self.master.after(0, lambda: messagebox.showwarning("Hinweis", "Bitte zuerst einen Startordner wählen."))
            self.master.after(0, self.enable_buttons)
            self.master.after(0, self.stop_spinner)
            return

        self.base_folder = folder

        try:
            min_size = int(float(self.min_size_entry.get()) * 1024 * 1024)
        except:
            min_size = 0

        extensions = [e.strip().lower() for e in self.ext_entry.get().split(",") if e.strip()]

        def update_progress(done, total):
            percent = int((done / total) * 100) if total else 0

            def gui_update():
                self.progress["value"] = percent
                self.progress_label.config(text=f"{percent}%")

            self.master.after(0, gui_update)

        hash_map = scan_directory(folder, min_size, extensions, update_progress)
        groups = build_duplicate_groups(hash_map)
        self.duplicate_groups = groups

        self.master.after(0, lambda: self.display_results(groups))
        self.master.after(0, self.enable_buttons)
        self.master.after(0, self.stop_spinner)

    # --------------------------------------------------------
    # Ergebnisse anzeigen
    # --------------------------------------------------------
    def display_results(self, groups):
        self.listbox.delete(0, tk.END)
        self.listbox_index_map.clear()
        self.group_states.clear()

        total_wasted = 0
        total_duplicates = 0
        index = 0

        for g_index, group in enumerate(groups):
            self.group_states[g_index] = False  # ausgeklappt

            header = f"[–] Gruppe {g_index+1} ({len(group)} Dateien)"
            self.listbox.insert(tk.END, header)
            self.listbox.itemconfig(tk.END, foreground="blue")
            self.listbox_index_map[index] = (g_index, None)
            index += 1

            wasted = group[0][1] * (len(group) - 1)
            total_wasted += wasted
            total_duplicates += len(group) - 1

            for f_index, (path, size) in enumerate(group):
                rel = os.path.relpath(path, self.base_folder)
                text = f"    {rel} ({size/1024/1024:.2f} MB)"
                self.listbox.insert(tk.END, text)
                self.listbox_index_map[index] = (g_index, f_index)
                index += 1

            self.listbox.insert(tk.END, "")
            index += 1

        if not groups:
            self.summary_var.set("Keine Dubletten gefunden.")
        else:
            mb = total_wasted / 1024 / 1024
            gb = mb / 1024
            self.summary_var.set(
                f"Dubletten: {total_duplicates} | Verschwendet: {mb:.2f} MB ({gb:.2f} GB)"
            )

    # --------------------------------------------------------
    # Gruppe ein/ausklappen
    # --------------------------------------------------------
    def toggle_group(self, event):
        index = self.listbox.curselection()
        if not index:
            return
        index = index[0]

        if index not in self.listbox_index_map:
            return

        g_index, f_index = self.listbox_index_map[index]
        if f_index is not None:
            return  # kein Header

        # Zustand umschalten
        self.group_states[g_index] = not self.group_states[g_index]

        self.render_groups()

    def render_groups(self):
        self.listbox.delete(0, tk.END)
        self.listbox_index_map.clear()

        index = 0

        for g_index, group in enumerate(self.duplicate_groups):
            collapsed = self.group_states[g_index]

            header = f"[+] Gruppe {g_index+1} ({len(group)} Dateien)" if collapsed else \
                     f"[–] Gruppe {g_index+1} ({len(group)} Dateien)"

            self.listbox.insert(tk.END, header)
            self.listbox.itemconfig(tk.END, foreground="blue")
            self.listbox_index_map[index] = (g_index, None)
            index += 1

            if not collapsed:
                for f_index, (path, size) in enumerate(group):
                    rel = os.path.relpath(path, self.base_folder)
                    text = f"    {rel} ({size/1024/1024:.2f} MB)"
                    self.listbox.insert(tk.END, text)
                    self.listbox_index_map[index] = (g_index, f_index)
                    index += 1

                self.listbox.insert(tk.END, "")
                index += 1

    # --------------------------------------------------------
    # Automatische Vorauswahl
    # --------------------------------------------------------
    def select_all_but_one(self):
        self.listbox.selection_clear(0, tk.END)

        for g_index, group in enumerate(self.duplicate_groups):
            for f_index in range(1, len(group)):
                for lb_index, (gi, fi) in self.listbox_index_map.items():
                    if gi == g_index and fi == f_index:
                        self.listbox.selection_set(lb_index)

    # --------------------------------------------------------
    # Löschen + Fortschritt
    # --------------------------------------------------------
    def delete_selected(self):
        selected = self.listbox.curselection()
        files = []

        for idx in selected:
            if idx in self.listbox_index_map:
                g_index, f_index = self.listbox_index_map[idx]
                if f_index is not None:
                    files.append(self.duplicate_groups[g_index][f_index])

        if not files:
            messagebox.showinfo("Info", "Keine Dateien ausgewählt.")
            return

        total = sum(size for _, size in files)
        preview = "\n".join(os.path.relpath(path, self.base_folder) for path, _ in files[:10])

        msg = f"{len(files)} Dateien löschen?\nGesamt: {total/1024/1024:.2f} MB\n\nBeispiele:\n{preview}"

        if not messagebox.askyesno("Bestätigen", msg):
            return

        # Fortschritt zurücksetzen
        self.progress["value"] = 0
        self.progress_label.config(text="0%")

        deleted = []
        total_files = len(files)

        for i, (path, size) in enumerate(files, start=1):
            try:
                os.remove(path)
                deleted.append({"path": path, "size": size})
            except:
                pass

            percent = int((i / total_files) * 100)
            self.progress["value"] = percent
            self.progress_label.config(text=f"{percent}%")
            self.master.update_idletasks()

        self.write_log(deleted)
        messagebox.showinfo("Fertig", f"{len(deleted)} Dateien gelöscht. Log erstellt.")

        self.start_scan_thread()

    # --------------------------------------------------------
    # Log schreiben
    # --------------------------------------------------------
    def write_log(self, deleted_entries):
        os.makedirs("logs", exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"logs/dff_report_{timestamp}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write("Duplicate File Finder – Löschprotokoll\n")
            f.write("=======================================\n\n")
            f.write(f"Zeitpunkt: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Anzahl gelöschter Dateien: {len(deleted_entries)}\n\n")

            total_size = sum(entry["size"] for entry in deleted_entries)
            f.write(f"Freigegebener Speicherplatz: {total_size/1024/1024:.2f} MB\n\n")

            f.write("Gelöschte Dateien:\n")
            f.write("------------------\n")
            for entry in deleted_entries:
                f.write(f"{entry['path']} ({entry['size']/1024/1024:.2f} MB)\n")


# ------------------------------------------------------------
# Start
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = DuplicateFileFinderGUI(root)
    root.mainloop()
