"""
GraphColor - Examination Scheduler
A complete single-file Tkinter application.

Features:
- Add and persist student subject registrations (SQLite)
- Display registered students
- Detect subject conflicts (shared students)
- Build and draw the subject conflict graph
- Greedy and Welsh-Powell graph-colouring algorithms
- Compare algorithms
- Import CSV and (optionally) Excel files
- Export the generated examination timetable to CSV

CSV import format:
student_id,subjects
S001,Maths;Physics;Python
S002,Java;Python

Subjects can be separated by commas or semicolons in the file.
"""
from tkinter import messagebox
import csv
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import defaultdict
from datetime import datetime


APP_TITLE = "GraphColor | Examination Scheduler"
DB_NAME = "graphcolor_students.db"

# Light theme
BG = "#F4F7FB"
PANEL = "#FFFFFF"
SIDEBAR = "#172B4D"
SIDEBAR_HOVER = "#243D63"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
GREEN = "#16A36A"
ORANGE = "#E99A24"
PURPLE = "#7952B3"
TEAL = "#0F9D9A"
TEXT = "#172033"
MUTED = "#64748B"
BORDER = "#E2E8F0"
PALE_BLUE = "#EAF1FF"


class ExamScheduler:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1250x820")
        self.root.minsize(1050, 700)
        self.root.configure(bg=BG)

        self.db = sqlite3.connect(DB_NAME)
        self.create_database()

        self.students = self.load_students()
        self.conflicts = []
        self.graph = defaultdict(set)
        self.coloring_results = {}
        self.current_coloring = {}
        self.current_algorithm = ""

        self.setup_styles()
        self.create_interface()
        self.refresh_dashboard()
        self.show_welcome()

        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    # ---------------- DATABASE ----------------

    def create_database(self):
        with self.db:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS registrations (
                    student_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    PRIMARY KEY (student_id, subject)
                )
            """)

    def load_students(self):
        students = defaultdict(set)
        rows = self.db.execute(
            "SELECT student_id, subject FROM registrations ORDER BY student_id, subject"
        ).fetchall()
        for student_id, subject in rows:
            students[student_id].add(subject)
        return students

    def save_student(self, student_id, subjects):
        with self.db:
            for subject in subjects:
                self.db.execute(
                    "INSERT OR IGNORE INTO registrations(student_id, subject) VALUES (?, ?)",
                    (student_id, subject)
                )
        self.students = self.load_students()

    # ---------------- STYLES / UI ----------------

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Treeview",
            background=PANEL,
            foreground=TEXT,
            fieldbackground=PANEL,
            rowheight=30,
            bordercolor=BORDER,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background="#EEF2F7",
            foreground=TEXT,
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        style.map("Treeview", background=[("selected", "#DBEAFE")],
                  foreground=[("selected", TEXT)])
        style.configure("TCombobox", padding=6)

    def create_interface(self):
        # Header
        header = tk.Frame(self.root, bg=PANEL, height=82,
                          highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_area = tk.Frame(header, bg=PANEL)
        title_area.pack(side="left", padx=28, pady=13)

        tk.Label(title_area, text="GraphColor",
                 bg=PANEL, fg=PRIMARY,
                 font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(title_area, text="EXAMINATION SCHEDULER  •  GRAPH COLOURING",
                 bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        self.header_status = tk.Label(
            header, text="●  Ready", bg=PANEL, fg=GREEN,
            font=("Segoe UI", 10, "bold")
        )
        self.header_status.pack(side="right", padx=30)

        # Main body
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar
        sidebar = tk.Frame(body, bg=SIDEBAR, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="WORKSPACE", bg=SIDEBAR, fg="#AFC2DF",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(25, 12))

        self.nav_button(sidebar, "Dashboard", self.show_dashboard, True)
        self.nav_button(sidebar, "Student Records", self.show_students)
        self.nav_button(sidebar, "Conflict Analysis", self.detect_conflicts)
        self.nav_button(sidebar, "Conflict Graph", self.create_conflict_graph)
        self.nav_button(sidebar, "Timetable", self.show_timetable)

        tk.Frame(sidebar, bg="#365071", height=1).pack(fill="x", padx=18, pady=20)
        tk.Label(sidebar, text="DATA", bg=SIDEBAR, fg="#AFC2DF",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(0, 10))
        self.nav_button(sidebar, "Import CSV / Excel", self.upload_file)
        self.nav_button(sidebar, "Export Timetable", self.export_timetable)

        tk.Label(sidebar, text="GraphColor v1.0", bg=SIDEBAR, fg="#AFC2DF",
                 font=("Segoe UI", 8)).pack(side="bottom", pady=18)

        # Main content with scrollable canvas
        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        self.page = tk.Frame(self.content, bg=BG)
        self.page.pack(fill="both", expand=True, padx=26, pady=22)

    def nav_button(self, parent, text, command, active=False):
        btn = tk.Button(
            parent, text="  " + text, command=command,
            anchor="w", relief="flat", bd=0,
            bg=SIDEBAR_HOVER if active else SIDEBAR,
            fg="white", activebackground=SIDEBAR_HOVER,
            activeforeground="white",
            font=("Segoe UI", 10, "bold" if active else "normal"),
            padx=12, pady=11, cursor="hand2"
        )
        btn.pack(fill="x", padx=10, pady=2)
        btn.bind("<Enter>", lambda e: btn.configure(bg=SIDEBAR_HOVER))
        btn.bind("<Leave>", lambda e: btn.configure(
            bg=SIDEBAR_HOVER if active else SIDEBAR
        ))

    def clear_page(self):
        for widget in self.page.winfo_children():
            widget.destroy()

    def page_heading(self, heading, subtitle=""):
        tk.Label(self.page, text=heading, bg=BG, fg=TEXT,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(self.page, text=subtitle, bg=BG, fg=MUTED,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 16))

    def make_card(self, parent, title, value, accent=PRIMARY, note=""):
        card = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                        highlightthickness=1)
        tk.Frame(card, bg=accent, width=5).pack(side="left", fill="y")
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=14)
        tk.Label(inner, text=title.upper(), bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(inner, text=str(value), bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=3)
        if note:
            tk.Label(inner, text=note, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")
        return card

    def action_button(self, parent, text, command, color=PRIMARY):
        return tk.Button(
            parent, text=text, command=command,
            bg=color, fg="white", activebackground=color,
            activeforeground="white", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), padx=15, pady=9,
            cursor="hand2"
        )

    def show_welcome(self):
        if not self.students:
            self.header_status.config(text="●  Add student records to begin", fg=ORANGE)

    # ---------------- DASHBOARD ----------------

    def refresh_dashboard(self):
        self.students = self.load_students()
        total_students = len(self.students)
        all_subjects = set()
        for subjects in self.students.values():
            all_subjects.update(subjects)
        total_subjects = len(all_subjects)

        if total_subjects:
            self.build_graph_data()
            total_conflicts = len(self.conflicts)
        else:
            total_conflicts = 0

        self.clear_page()
        self.page_heading(
            "Dashboard",
            "Overview of student registrations and examination scheduling."
        )

        cards = tk.Frame(self.page, bg=BG)
        cards.pack(fill="x", pady=(0, 18))
        stats = [
            ("Registered Students", total_students, PRIMARY, "Unique student IDs"),
            ("Total Subjects", total_subjects, TEAL, "Unique subjects"),
            ("Subject Conflicts", total_conflicts, ORANGE, "Conflicting subject pairs"),
            ("Timetable Slots", len(set(self.current_coloring.values())),
             PURPLE, "Based on latest colouring")
        ]
        for title, value, color, note in stats:
            card = self.make_card(cards, title, value, color, note)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12))

        # Registration form
        form_card = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                             highlightthickness=1)
        form_card.pack(fill="x", pady=(0, 16))
        tk.Label(form_card, text="Register a student", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(15, 3))
        tk.Label(form_card, text="Enter a student ID and subjects separated by commas.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=18)

        fields = tk.Frame(form_card, bg=PANEL)
        fields.pack(fill="x", padx=18, pady=14)

        tk.Label(fields, text="Student ID", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(fields, text="Subjects", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.student_entry = ttk.Entry(fields, width=24, font=("Segoe UI", 10))
        self.student_entry.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.subject_entry = ttk.Entry(fields, font=("Segoe UI", 10))
        self.subject_entry.grid(row=1, column=1, sticky="ew", padx=(12, 12), pady=(5, 0))
        fields.columnconfigure(1, weight=1)

        self.action_button(fields, "＋ Add Student", self.add_student, GREEN).grid(
            row=1, column=2, sticky="e"
        )

        # Quick actions
        quick = tk.Frame(self.page, bg=BG)
        quick.pack(fill="x", pady=(0, 16))
        for label, command, color in [
            ("Detect Conflicts", self.detect_conflicts, GREEN),
            ("Create Conflict Graph", self.create_conflict_graph, PURPLE),
            ("Run Greedy", self.run_greedy, ORANGE),
            ("Run Welsh-Powell", self.run_welsh_powell, "#D97706"),
            ("Compare Algorithms", self.compare_algorithms, TEAL),
            ("Export Timetable", self.export_timetable, PRIMARY),
        ]:
            self.action_button(quick, label, command, color).pack(
                side="left", padx=(0, 8), pady=4
            )

        # Recent registrations
        recent = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                          highlightthickness=1)
        recent.pack(fill="both", expand=True)
        tk.Label(recent, text="Recent student registrations", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=13)

        tree_frame = tk.Frame(recent, bg=PANEL)
        tree_frame.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        tree = ttk.Treeview(tree_frame, columns=("student", "subjects"),
                            show="headings", height=6)
        tree.heading("student", text="Student ID")
        tree.heading("subjects", text="Registered Subjects")
        tree.column("student", width=150, anchor="center")
        tree.column("subjects", width=600)
        tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)

        for student_id in sorted(self.students.keys())[-10:]:
            tree.insert("", "end", values=(
                student_id, ", ".join(sorted(self.students[student_id]))
            ))

        self.header_status.config(
            text=f"●  {total_students} students loaded", fg=GREEN
        )

    def show_dashboard(self):
        self.refresh_dashboard()

    # ---------------- STUDENTS ----------------

    def add_student(self):
        student_id = self.student_entry.get().strip().upper()
        raw_subjects = self.subject_entry.get().strip()

        subjects = {
            item.strip() for item in raw_subjects.replace(";", ",").split(",")
            if item.strip()
        }

        if not student_id or not subjects:
            messagebox.showwarning(
                "Missing information",
                "Please enter both a student ID and at least one subject."
            )
            return

        self.save_student(student_id, subjects)
        self.student_entry.delete(0, tk.END)
        self.subject_entry.delete(0, tk.END)
        self.header_status.config(text=f"●  Saved {student_id}", fg=GREEN)
        self.refresh_dashboard()
        messagebox.showinfo("Success", f"Student {student_id} saved successfully.")

    def show_students(self):
        self.clear_page()
        self.page_heading("Student Records", "All registered students and their subjects.")

        panel = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        panel.pack(fill="both", expand=True)

        top = tk.Frame(panel, bg=PANEL)
        top.pack(fill="x", padx=18, pady=15)
        tk.Label(top, text=f"{len(self.students)} students",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(side="left")
        self.action_button(top, "Refresh", self.show_students).pack(side="right")

        tree = ttk.Treeview(panel, columns=("id", "subjects", "count"),
                            show="headings")
        for col, title, width in [
            ("id", "Student ID", 170),
            ("subjects", "Registered Subjects", 650),
            ("count", "Subject Count", 130)
        ]:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w" if col == "subjects" else "center")
        tree.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        for student_id in sorted(self.students):
            subjects = sorted(self.students[student_id])
            tree.insert("", "end", values=(
                student_id, ", ".join(subjects), len(subjects)
            ))

    # ---------------- CONFLICT GRAPH ----------------

    def build_graph_data(self):
        self.students = self.load_students()
        graph = defaultdict(set)
        subject_students = defaultdict(set)

        for student_id, subjects in self.students.items():
            for subject in subjects:
                graph[subject]  # ensure every subject is a vertex
                subject_students[subject].add(student_id)

        conflicts = []
        subject_list = sorted(graph.keys())
        for i, subject_a in enumerate(subject_list):
            for subject_b in subject_list[i + 1:]:
                common = subject_students[subject_a] & subject_students[subject_b]
                if common:
                    graph[subject_a].add(subject_b)
                    graph[subject_b].add(subject_a)
                    conflicts.append((subject_a, subject_b, sorted(common)))

        self.graph = graph
        self.conflicts = conflicts
        return graph, conflicts

    def detect_conflicts(self):
        self.build_graph_data()
        self.clear_page()
        self.page_heading("Conflict Analysis", "Two subjects conflict when at least one student is registered in both.")

        summary = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                           highlightthickness=1)
        summary.pack(fill="x", pady=(0, 14))
        tk.Label(summary, text=f"Total subject conflicts: {len(self.conflicts)}",
                 bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(
                     anchor="w", padx=18, pady=15
                 )

        panel = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        panel.pack(fill="both", expand=True)
        tree = ttk.Treeview(panel, columns=("a", "b", "students"),
                            show="headings")
        tree.heading("a", text="Subject 1")
        tree.heading("b", text="Subject 2")
        tree.heading("students", text="Common Students")
        tree.column("a", width=180, anchor="center")
        tree.column("b", width=180, anchor="center")
        tree.column("students", width=500)
        tree.pack(fill="both", expand=True, padx=18, pady=18)

        for a, b, common in self.conflicts:
            tree.insert("", "end", values=(a, b, ", ".join(common)))

        if not self.conflicts:
            tk.Label(panel, text="No subject conflicts found.",
                     bg=PANEL, fg=GREEN, font=("Segoe UI", 11, "bold")).pack(pady=10)

    def create_conflict_graph(self):
        self.build_graph_data()
        self.clear_page()
        self.page_heading("Conflict Graph", "Each node represents a subject. An edge connects two subjects with common students.")

        toolbar = tk.Frame(self.page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 10))
        tk.Label(toolbar, text=f"{len(self.graph)} vertices   •   {len(self.conflicts)} edges",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10, "bold")).pack(side="left")

        canvas_frame = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                                highlightthickness=1)
        canvas_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(canvas_frame, bg=PANEL, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.draw_graph(canvas)


    def draw_graph(self, canvas):
        """Draw the subject conflict graph using Welsh-Powell slot colours."""
        import math

        canvas.delete("all")
        nodes = sorted(
            self.graph.keys(),
            key=lambda subject: (-len(self.graph[subject]), str(subject).casefold())
        )

        if not nodes:
            canvas.create_text(
                350, 180,
                text="No subjects available. Add students first.",
                fill=MUTED,
                font=("Segoe UI", 12)
            )
            return

        # Calculate Welsh-Powell colouring for the graph.
        coloring = {}
        for node in nodes:
            unavailable = {
                coloring[neighbor]
                for neighbor in self.graph[node]
                if neighbor in coloring
            }
            slot = 0
            while slot in unavailable:
                slot += 1
            coloring[node] = slot

        # Keep the latest timetable in sync with the graph being displayed.
        self.current_coloring = dict(coloring)
        self.current_algorithm = "Welsh-Powell Algorithm"

        palette = [
            "#DBEAFE", "#DCFCE7", "#FCE7F3",
            "#FEF3C7", "#EDE9FE", "#CFFAFE",
            "#FFEDD5", "#F1F5F9"
        ]
        outlines = [
            "#2563EB", "#16A34A", "#DB2777",
            "#D97706", "#7C3AED", "#0891B2",
            "#EA580C", "#475569"
        ]

        canvas.update_idletasks()
        width = max(canvas.winfo_width(), 650)
        height = max(canvas.winfo_height(), 460)

        canvas.create_text(
            20, 16,
            text="WELSH-POWELL COLOURED CONFLICT GRAPH",
            anchor="nw",
            fill=TEXT,
            font=("Segoe UI", 13, "bold")
        )
        canvas.create_text(
            20, 41,
            text="Subjects in the same slot do not share registered students. Click a subject for details.",
            anchor="nw",
            fill=MUTED,
            font=("Segoe UI", 9)
        )

        # Reserve space for the heading and slot legend.
        top_space = 82
        legend_space = 48
        cx = width / 2
        cy = top_space + max(130, (height - top_space - legend_space) / 2)
        radius = max(75, min(width * 0.34, (height - top_space - legend_space) * 0.38))
        positions = {}

        for index, node in enumerate(nodes):
            angle = (2 * math.pi * index / len(nodes)) - math.pi / 2
            positions[node] = (
                cx + radius * math.cos(angle),
                cy + radius * math.sin(angle)
            )

        # Draw edges before nodes so that lines stay behind the subject shapes.
        edge_items = {}
        for subject in nodes:
            for neighbor in sorted(self.graph[subject], key=lambda item: str(item).casefold()):
                if str(subject).casefold() < str(neighbor).casefold():
                    x1, y1 = positions[subject]
                    x2, y2 = positions[neighbor]
                    edge_id = canvas.create_line(
                        x1, y1, x2, y2,
                        fill="#94A3B8",
                        width=2
                    )
                    edge_items[(subject, neighbor)] = edge_id

        node_items = {}
        subject_students = defaultdict(list)
        for student_id, subjects in self.students.items():
            for subject in subjects:
                subject_students[subject].append(student_id)

        for node in nodes:
            x, y = positions[node]
            slot_index = coloring[node]
            palette_index = slot_index % len(palette)
            tag = f"subject_node_{nodes.index(node)}"

            oval_id = canvas.create_oval(
                x - 58, y - 34, x + 58, y + 34,
                fill=palette[palette_index],
                outline=outlines[palette_index],
                width=3,
                tags=(tag,)
            )
            text_id = canvas.create_text(
                x, y,
                text=f"{str(node)[:16]}\\nSlot {slot_index + 1}",
                fill="#172554",
                font=("Segoe UI", 9, "bold"),
                justify="center",
                tags=(tag,)
            )
            node_items[node] = (oval_id, text_id)

            def show_details(event, selected=node):
                connected = sorted(
                    self.graph[selected],
                    key=lambda item: str(item).casefold()
                )
                common_students = []
                for neighbor in connected:
                    shared = sorted(
                        set(subject_students[selected]) & set(subject_students[neighbor])
                    )
                    if shared:
                        common_students.append(f"{neighbor}: {', '.join(shared)}")

                conflict_details = (
                    "\\n".join(common_students)
                    if common_students else "No conflicting subjects"
                )
                registered = sorted(subject_students[selected])
                messagebox.showinfo(
                    "Subject Information",
                    f"Subject: {selected}\\n"
                    f"Examination Slot: {coloring[selected] + 1}\\n"
                    f"Registered Students: {len(registered)}\\n"
                    f"Student IDs: {', '.join(registered) if registered else 'None'}\\n"
                    f"Number of Conflicts: {len(connected)}\\n"
                    f"Conflicting Subjects and Common Students:\\n{conflict_details}"
                )

            canvas.tag_bind(tag, "<Button-1>", show_details)
            canvas.tag_bind(
                tag, "<Enter>",
                lambda event, item=oval_id: canvas.itemconfig(item, width=4)
            )
            canvas.tag_bind(
                tag, "<Leave>",
                lambda event, item=oval_id: canvas.itemconfig(item, width=3)
            )

        # Draw a colour legend for the examination slots.
        slot_count = max(coloring.values()) + 1
        legend_y = height - 24
        legend_x = 20
        for slot in range(slot_count):
            palette_index = slot % len(palette)
            canvas.create_rectangle(
                legend_x, legend_y - 8, legend_x + 15, legend_y + 7,
                fill=palette[palette_index],
                outline=outlines[palette_index],
                width=2
            )
            canvas.create_text(
                legend_x + 22, legend_y,
                text=f"Slot {slot + 1}",
                anchor="w",
                fill=TEXT,
                font=("Segoe UI", 9, "bold")
            )
            legend_x += 105

    # ---------------- GRAPH COLOURING ----------------

    def greedy_coloring(self):
        graph, _ = self.build_graph_data()
        coloring = {}
        for node in sorted(graph.keys()):
            unavailable = {coloring[n] for n in graph[node] if n in coloring}
            color = 0
            while color in unavailable:
                color += 1
            coloring[node] = color
        return coloring

    def welsh_powell_coloring(self):
        graph, _ = self.build_graph_data()
        order = sorted(graph.keys(), key=lambda node: len(graph[node]), reverse=True)
        coloring = {}
        for node in order:
            unavailable = {coloring[n] for n in graph[node] if n in coloring}
            color = 0
            while color in unavailable:
                color += 1
            coloring[node] = color
        return coloring

    def display_coloring(self, algorithm, coloring):
        self.current_algorithm = algorithm
        self.current_coloring = coloring
        self.coloring_results[algorithm] = coloring

        self.clear_page()
        self.page_heading(
            f"{algorithm} Result",
            "Subjects assigned to the same slot do not share registered students."
        )

        slots = defaultdict(list)
        for subject, color in coloring.items():
            slots[color].append(subject)

        top = tk.Frame(self.page, bg=BG)
        top.pack(fill="x", pady=(0, 14))
        self.make_card(top, "Subjects Scheduled", len(coloring), PRIMARY).pack(
            side="left", fill="both", expand=True, padx=(0, 10)
        )
        self.make_card(top, "Slots Required", len(slots), GREEN).pack(
            side="left", fill="both", expand=True, padx=(0, 10)
        )
        self.make_card(top, "Conflicts", len(self.conflicts), ORANGE).pack(
            side="left", fill="both", expand=True
        )

        panel = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="Generated examination timetable",
                 bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(
                     anchor="w", padx=18, pady=14
                 )
        tree = ttk.Treeview(panel, columns=("slot", "subjects"),
                            show="headings", height=12)
        tree.heading("slot", text="Exam Slot")
        tree.heading("subjects", text="Subjects in this slot")
        tree.column("slot", width=160, anchor="center")
        tree.column("subjects", width=650)
        tree.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        for color in sorted(slots):
            tree.insert("", "end", values=(
                f"Slot {color + 1}", ", ".join(sorted(slots[color]))
            ))

        self.header_status.config(
            text=f"●  {algorithm}: {len(slots)} slots", fg=GREEN
        )

    def run_greedy(self):
        if not self.students:
            messagebox.showwarning("No data", "Add or import student records first.")
            return
        coloring = self.greedy_coloring()
        self.display_coloring("Greedy Algorithm", coloring)

    def run_welsh_powell(self):
        if not self.students:
            messagebox.showwarning("No data", "Add or import student records first.")
            return
        coloring = self.welsh_powell_coloring()
        self.display_coloring("Welsh-Powell Algorithm", coloring)

    def compare_algorithms(self):
        if not self.students:
            messagebox.showwarning("No data", "Add or import student records first.")
            return
        greedy = self.greedy_coloring()
        welsh = self.welsh_powell_coloring()
        self.coloring_results["Greedy Algorithm"] = greedy
        self.coloring_results["Welsh-Powell Algorithm"] = welsh

        greedy_slots = len(set(greedy.values())) if greedy else 0
        welsh_slots = len(set(welsh.values())) if welsh else 0

        self.clear_page()
        self.page_heading("Algorithm Comparison", "Comparison of the two graph-colouring methods.")

        panel = tk.Frame(self.page, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1)
        panel.pack(fill="x", pady=10)
        tree = ttk.Treeview(panel, columns=("algorithm", "vertices", "slots"),
                            show="headings", height=4)
        tree.heading("algorithm", text="Algorithm")
        tree.heading("vertices", text="Subjects")
        tree.heading("slots", text="Slots Required")
        tree.column("algorithm", width=300)
        tree.column("vertices", width=150, anchor="center")
        tree.column("slots", width=180, anchor="center")
        tree.pack(fill="x", padx=18, pady=18)
        tree.insert("", "end", values=("Greedy Algorithm", len(greedy), greedy_slots))
        tree.insert("", "end", values=("Welsh-Powell Algorithm", len(welsh), welsh_slots))

        best = "Greedy Algorithm" if greedy_slots <= welsh_slots else "Welsh-Powell Algorithm"
        tk.Label(self.page, text=f"Result: {best} uses fewer or equal slots for this dataset.",
                 bg=BG, fg=GREEN, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=12)

        row = tk.Frame(self.page, bg=BG)
        row.pack(anchor="w")
        self.action_button(row, "View Greedy Timetable",
                           lambda: self.display_coloring("Greedy Algorithm", greedy),
                           ORANGE).pack(side="left", padx=(0, 10))
        self.action_button(row, "View Welsh-Powell Timetable",
                           lambda: self.display_coloring("Welsh-Powell Algorithm", welsh),
                           PURPLE).pack(side="left")

    # ---------------- TIMETABLE / EXPORT ----------------

    def show_timetable(self):
        if not self.current_coloring:
            self.run_welsh_powell()
            return
        self.display_coloring(self.current_algorithm or "Current Algorithm",
                              self.current_coloring)

    def export_timetable(self):
        if not self.current_coloring:
            if not self.students:
                messagebox.showwarning("No data", "Add students and generate a timetable first.")
                return
            self.current_coloring = self.welsh_powell_coloring()
            self.current_algorithm = "Welsh-Powell Algorithm"

        path = filedialog.asksaveasfilename(
            title="Export examination timetable",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return

        slots = defaultdict(list)
        for subject, color in self.current_coloring.items():
            slots[color].append(subject)

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Exam Slot", "Subjects", "Algorithm", "Generated On"])
                for color in sorted(slots):
                    writer.writerow([
                        f"Slot {color + 1}",
                        ", ".join(sorted(slots[color])),
                        self.current_algorithm,
                        datetime.now().strftime("%Y-%m-%d %H:%M")
                    ])
            messagebox.showinfo("Export complete", f"Timetable saved to:\n{path}")
        except OSError as error:
            messagebox.showerror("Export error", str(error))

    # ---------------- IMPORT ----------------

    def upload_file(self):
        path = filedialog.askopenfilename(
            title="Select student dataset",
            filetypes=[
                ("Supported files", "*.csv *.xlsx"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx")
            ]
        )
        if not path:
            return

        try:
            if path.lower().endswith(".csv"):
                records = self.read_csv(path)
            elif path.lower().endswith(".xlsx"):
                records = self.read_excel(path)
            else:
                raise ValueError("Please select a CSV or XLSX file.")

            if not records:
                raise ValueError("No valid student records were found.")

            for student_id, subjects in records:
                self.save_student(student_id, subjects)

            self.refresh_dashboard()
            messagebox.showinfo(
                "Import successful",
                f"Imported {len(records)} student record(s)."
            )
        except Exception as error:
            messagebox.showerror("Import error", str(error))

    def read_csv(self, path):
        records = []
        with open(path, "r", newline="", encoding="utf-8-sig") as file:
            sample = file.read(2048)
            file.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(file, dialect=dialect)
            if not reader.fieldnames:
                raise ValueError("CSV file must have a header row.")

            normalized = {name.strip().lower(): name for name in reader.fieldnames}
            id_key = next((normalized[k] for k in ("student_id", "student id", "id")
                           if k in normalized), None)
            subjects_key = next((normalized[k] for k in ("subjects", "subject")
                                 if k in normalized), None)
            if not id_key or not subjects_key:
                raise ValueError("CSV headers must include student_id and subjects.")

            for row in reader:
                student_id = (row.get(id_key) or "").strip().upper()
                raw = (row.get(subjects_key) or "").strip()
                subjects = {s.strip() for s in raw.replace(";", ",").split(",") if s.strip()}
                if student_id and subjects:
                    records.append((student_id, subjects))
        return records

    def read_excel(self, path):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ValueError(
                "Excel import needs openpyxl. Install it with:\npy -m pip install openpyxl"
            )

        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers:
            raise ValueError("Excel sheet is empty.")

        normalized = {
            str(value).strip().lower(): index
            for index, value in enumerate(headers) if value is not None
        }
        id_index = next((normalized[k] for k in ("student_id", "student id", "id")
                         if k in normalized), None)
        subjects_index = next((normalized[k] for k in ("subjects", "subject")
                               if k in normalized), None)
        if id_index is None or subjects_index is None:
            raise ValueError("Excel headers must include student_id and subjects.")

        records = []
        for row in rows:
            student_id = str(row[id_index] or "").strip().upper()
            raw = str(row[subjects_index] or "").strip()
            subjects = {s.strip() for s in raw.replace(";", ",").split(",") if s.strip()}
            if student_id and subjects:
                records.append((student_id, subjects))
        workbook.close()
        return records

    # ---------------- CLOSE ----------------

    def close_app(self):
        try:
            self.db.close()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = ExamScheduler(root)
    root.mainloop()


if __name__ == "__main__":
    main()
