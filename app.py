import streamlit as st
import pandas as pd
import sqlite3
import io
import csv
import math
import hashlib
import hmac
from collections import defaultdict
from datetime import datetime
import networkx as nx
import plotly.graph_objects as go

st.set_page_config(page_title="GraphColor | Examination Scheduler", page_icon="🎓", layout="wide")

DB_FILE = "graphcolor_students.db"

# ---------------- STORAGE: SUPABASE IF CONFIGURED, OTHERWISE SQLITE ----------------
def supabase_client():
    try:
        from supabase import create_client
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception:
        return None

def local_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_storage():
    client = supabase_client()
    if client:
        return "supabase"
    with local_connection() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS registrations (
            student_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            PRIMARY KEY(student_id, subject)
        )""")
    return "sqlite"

STORAGE = init_storage()

def load_students():
    result = defaultdict(set)
    if STORAGE == "supabase":
        rows = supabase_client().table("registrations").select("student_id,subject").execute().data or []
    else:
        with local_connection() as con:
            rows = con.execute("SELECT student_id, subject FROM registrations ORDER BY student_id, subject").fetchall()
        rows = [{"student_id": r[0], "subject": r[1]} for r in rows]
    for row in rows:
        result[str(row["student_id"])].add(str(row["subject"]))
    return result

def save_student(student_id, subjects):
    if STORAGE == "supabase":
        records = [{"student_id": student_id, "subject": s} for s in subjects]
        supabase_client().table("registrations").upsert(records, on_conflict="student_id,subject").execute()
    else:
        with local_connection() as con:
            con.executemany(
                "INSERT OR IGNORE INTO registrations(student_id,subject) VALUES (?,?)",
                [(student_id, s) for s in subjects]
            )

def replace_student(student_id, subjects):
    delete_student(student_id)
    save_student(student_id, subjects)

def delete_student(student_id):
    if STORAGE == "supabase":
        supabase_client().table("registrations").delete().eq("student_id", student_id).execute()
    else:
        with local_connection() as con:
            con.execute("DELETE FROM registrations WHERE student_id=?", (student_id,))

def delete_all_students():
    if STORAGE == "supabase":
        # Delete rows using a non-empty student_id filter; fetch IDs first.
        ids = supabase_client().table("registrations").select("student_id").execute().data or []
        unique_ids = sorted({r["student_id"] for r in ids})
        for sid in unique_ids:
            delete_student(sid)
    else:
        with local_connection() as con:
            con.execute("DELETE FROM registrations")

# ---------------- GRAPH AND COLOURING ----------------
def build_graph(students):
    graph = nx.Graph()
    subject_students = defaultdict(set)
    for sid, subjects in students.items():
        for subject in subjects:
            graph.add_node(subject)
            subject_students[subject].add(sid)
    conflicts = []
    nodes = sorted(graph.nodes(), key=str.casefold)
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            shared = sorted(subject_students[a] & subject_students[b])
            if shared:
                graph.add_edge(a, b, common_students=shared)
                conflicts.append((a, b, shared))
    return graph, conflicts, subject_students

def colour_graph(graph, algorithm):
    if algorithm == "Welsh-Powell":
        order = sorted(graph.nodes(), key=lambda n: (-graph.degree[n], str(n).casefold()))
    else:
        order = sorted(graph.nodes(), key=str.casefold)
    colours = {}
    for node in order:
        used = {colours[n] for n in graph.neighbors(node) if n in colours}
        colour = 0
        while colour in used:
            colour += 1
        colours[node] = colour
    return colours

def slots_from_colouring(colouring):
    slots = defaultdict(list)
    for subject, slot in colouring.items():
        slots[int(slot)].append(subject)
    return {slot: sorted(subjects, key=str.casefold) for slot, subjects in sorted(slots.items())}

def validate_slots(graph, assignments):
    problems = []
    for a, b in graph.edges():
        if assignments.get(a) == assignments.get(b):
            problems.append((a, b))
    return problems

# ---------------- AUTHENTICATION ----------------
def check_login(username, password):
    try:
        expected_user = str(st.secrets["auth"]["username"])
        expected_hash = str(st.secrets["auth"]["password_sha256"])
    except Exception:
        return False
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(digest, expected_hash)

def login_screen():
    st.title("🔐 GraphColor Admin Login")
    st.caption("Sign in to manage examination data.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        if check_login(username.strip(), password):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Invalid username or password.")
    st.info("Admin login must be configured in Streamlit secrets before publishing. See SETUP_GUIDE.txt.")

# ---------------- IMPORT AND EXPORT ----------------
def parse_import(uploaded):
    if uploaded.name.lower().endswith(".csv"):
        frame = pd.read_csv(uploaded)
    else:
        frame = pd.read_excel(uploaded)
    columns = {str(c).strip().casefold(): c for c in frame.columns}
    id_col = next((columns[k] for k in ("student_id", "student id", "id") if k in columns), None)
    subjects_col = next((columns[k] for k in ("subjects", "subject") if k in columns), None)
    if id_col is None or subjects_col is None:
        raise ValueError("File must contain columns named student_id and subjects.")
    records = []
    for _, row in frame.iterrows():
        sid = str(row[id_col]).strip().upper()
        raw = str(row[subjects_col]).strip()
        if not sid or sid == "NAN" or not raw or raw.casefold() == "nan":
            continue
        subjects = {s.strip() for s in raw.replace(";", ",").split(",") if s.strip()}
        if subjects:
            records.append((sid, subjects))
    return records

def make_timetable_csv(assignments, algorithm):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Exam Slot", "Subject", "Algorithm", "Generated On"])
    for subject, slot in sorted(assignments.items(), key=lambda x: (x[1], x[0].casefold())):
        writer.writerow([f"Slot {slot + 1}", subject, algorithm, datetime.now().strftime("%Y-%m-%d %H:%M")])
    return output.getvalue().encode("utf-8-sig")

def make_timetable_xlsx(assignments, algorithm):
    buffer = io.BytesIO()
    rows = [{"Exam Slot": f"Slot {slot + 1}", "Subject": subject,
             "Algorithm": algorithm, "Generated On": datetime.now().strftime("%Y-%m-%d %H:%M")}
            for subject, slot in sorted(assignments.items(), key=lambda x: (x[1], x[0].casefold()))]
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Timetable")
    return buffer.getvalue()

def make_timetable_pdf(assignments, algorithm):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph("GraphColor Examination Timetable", styles["Title"]),
             Paragraph(f"Algorithm: {algorithm}", styles["Normal"]),
             Paragraph(f"Generated: {datetime.now():%Y-%m-%d %H:%M}", styles["Normal"]),
             Spacer(1, 16)]
    data = [["Exam Slot", "Subject"]]
    data += [[f"Slot {slot + 1}", subject] for subject, slot in sorted(assignments.items(), key=lambda x: (x[1], x[0].casefold()))]
    table = Table(data, colWidths=[120, 350])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D3557")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("PADDING", (0, 0), (-1, -1), 8)
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()

# ---------------- APPLICATION ----------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# If no auth secrets exist, app is intentionally blocked rather than exposing student data.
try:
    _ = st.secrets["auth"]["username"]
    AUTH_CONFIGURED = True
except Exception:
    AUTH_CONFIGURED = False

if not AUTH_CONFIGURED:
    st.title("GraphColor setup required")
    st.error("Admin authentication is not configured. Add the [auth] values in Streamlit Cloud → App settings → Secrets. See SETUP_GUIDE.txt.")
    st.stop()

if not st.session_state["authenticated"]:
    login_screen()
    st.stop()

students = load_students()
graph, conflicts, subject_students = build_graph(students)
subjects = sorted(graph.nodes(), key=str.casefold)

st.title("🎓 GraphColor")
st.caption("AUTOMATED EXAMINATION TIMETABLING SYSTEM · GRAPH COLOURING")
st.sidebar.title("GraphColor")
page = st.sidebar.radio("Navigation", [
    "Dashboard", "Student Records", "Conflict Analysis", "Conflict Graph",
    "Generate Timetable", "Import Data", "Project Information"
])
st.sidebar.caption(f"Storage: {'Supabase' if STORAGE == 'supabase' else 'Local SQLite'}")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

# DASHBOARD
if page == "Dashboard":
    st.header("Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registered Students", len(students))
    c2.metric("Total Subjects", graph.number_of_nodes())
    c3.metric("Subject Conflicts", len(conflicts))
    last = st.session_state.get("assignments", {})
    c4.metric("Timetable Slots", len(set(last.values())) if last else 0)

    st.subheader("Register a student")
    with st.form("add_student", clear_on_submit=True):
        left, right = st.columns([1, 2])
        sid = left.text_input("Student ID")
        raw_subjects = right.text_input("Subjects", placeholder="Maths, Physics, Python")
        add = st.form_submit_button("Add Student", type="primary")
    if add:
        parsed = {s.strip() for s in raw_subjects.replace(";", ",").split(",") if s.strip()}
        if not sid.strip() or not parsed:
            st.error("Enter a student ID and at least one subject.")
        else:
            save_student(sid.strip().upper(), parsed)
            st.success("Student registration saved.")
            st.rerun()

    if students:
        st.subheader("Recent student registrations")
        st.dataframe(pd.DataFrame([
            {"Student ID": k, "Subjects": ", ".join(sorted(v)), "Subject Count": len(v)}
            for k, v in sorted(students.items())
        ]), use_container_width=True, hide_index=True)
    else:
        st.info("No student registrations yet. Add students or import a file.")

    with st.expander("Danger zone — delete all student records"):
        st.warning("This permanently deletes every student registration.")
        confirm_all = st.checkbox("I understand and want to delete all records.")
        if st.button("Delete all records", disabled=not confirm_all):
            delete_all_students()
            st.session_state.pop("assignments", None)
            st.success("All records deleted.")
            st.rerun()

# STUDENT RECORDS
elif page == "Student Records":
    st.header("Student Records")
    query = st.text_input("Search by Student ID or subject").strip().casefold()
    visible = {sid: subs for sid, subs in students.items()
               if not query or query in sid.casefold() or any(query in s.casefold() for s in subs)}
    st.write(f"Showing {len(visible)} of {len(students)} students.")
    if visible:
        st.dataframe(pd.DataFrame([
            {"Student ID": sid, "Registered Subjects": ", ".join(sorted(subs)), "Subject Count": len(subs)}
            for sid, subs in sorted(visible.items())
        ]), use_container_width=True, hide_index=True)
        ids = sorted(students)
        st.subheader("Edit student")
        selected = st.selectbox("Student to edit", ids, key="edit_id")
        with st.form("edit_form"):
            edited = st.text_input("Subjects (comma-separated)", ", ".join(sorted(students[selected])))
            save = st.form_submit_button("Save student changes", type="primary")
        if save:
            new_subjects = {s.strip() for s in edited.replace(";", ",").split(",") if s.strip()}
            if not new_subjects:
                st.error("A student must have at least one subject. Use Delete student to remove them.")
            else:
                replace_student(selected, new_subjects)
                st.success("Student updated.")
                st.rerun()

        st.subheader("Delete individual student")
        remove_id = st.selectbox("Student to delete", ids, key="remove_id")
        confirm = st.checkbox(f"Confirm permanent deletion of {remove_id}")
        if st.button("Delete selected student", disabled=not confirm):
            delete_student(remove_id)
            st.session_state.pop("assignments", None)
            st.success("Student deleted and conflicts recalculated.")
            st.rerun()
    else:
        st.info("No matching students.")

# CONFLICT ANALYSIS
elif page == "Conflict Analysis":
    st.header("Conflict Analysis")
    st.write("Two subjects conflict if one or more students are registered in both.")
    st.metric("Total subject conflicts", len(conflicts))
    if conflicts:
        st.dataframe(pd.DataFrame([
            {"Subject 1": a, "Subject 2": b, "Common Students": ", ".join(shared)}
            for a, b, shared in conflicts
        ]), use_container_width=True, hide_index=True)
    else:
        st.success("No subject conflicts found.")

# INTERACTIVE GRAPH
elif page == "Conflict Graph":
    st.header("Interactive Conflict Graph")
    st.caption("Hover over a node to see details. Different node colours represent Welsh–Powell examination slots.")
    if not subjects:
        st.info("Add student registrations to create the graph.")
    else:
        colouring = colour_graph(graph, "Welsh-Powell")
        palette = ["#60A5FA", "#34D399", "#F472B6", "#FBBF24", "#A78BFA", "#22D3EE", "#FB923C", "#94A3B8"]
        pos = nx.spring_layout(graph, seed=17)
        edge_x, edge_y = [], []
        for a, b in graph.edges():
            edge_x += [pos[a][0], pos[b][0], None]
            edge_y += [pos[a][1], pos[b][1], None]
        edge_trace = go.Scatter(x=edge_x, y=edge_y, mode="lines",
                                line=dict(width=1.5, color="#94A3B8"),
                                hoverinfo="none")
        node_x, node_y, labels, hover, node_colours = [], [], [], [], []
        for subject in subjects:
            node_x.append(pos[subject][0]); node_y.append(pos[subject][1])
            labels.append(subject)
            neighbours = sorted(graph.neighbors(subject))
            hover.append(
                f"<b>{subject}</b><br>Slot: {colouring[subject]+1}"
                f"<br>Registered students: {len(subject_students[subject])}"
                f"<br>Conflicting subjects: {', '.join(neighbours) if neighbours else 'None'}"
            )
            node_colours.append(palette[colouring[subject] % len(palette)])
        node_trace = go.Scatter(
            x=node_x, y=node_y, mode="markers+text", text=labels,
            textposition="bottom center", hovertext=hover, hoverinfo="text",
            marker=dict(size=34, color=node_colours, line=dict(width=2, color="#334155"))
        )
        fig = go.Figure(data=[edge_trace, node_trace])
        fig.update_layout(height=600, showlegend=False,
                          margin=dict(l=20, r=20, t=20, b=20),
                          xaxis=dict(visible=False), yaxis=dict(visible=False),
                          plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Subject details")
        chosen_subject = st.selectbox("Select a subject", subjects)
        st.write(f"**Welsh–Powell slot:** {colouring[chosen_subject] + 1}")
        st.write(f"**Registered students:** {', '.join(sorted(subject_students[chosen_subject])) or 'None'}")
        st.write(f"**Conflicting subjects:** {', '.join(sorted(graph.neighbors(chosen_subject))) or 'None'}")

# TIMETABLE
elif page == "Generate Timetable":
    st.header("Advanced Examination Timetable")
    if not subjects:
        st.info("Add or import student records first.")
    else:
        method = st.radio("Colouring algorithm", ["Welsh-Powell", "Greedy"], horizontal=True)
        if st.button("Generate timetable", type="primary"):
            st.session_state["assignments"] = colour_graph(graph, method)
            st.session_state["algorithm"] = method
            st.success("Timetable generated.")
        if st.button("Compare algorithms"):
            g = colour_graph(graph, "Greedy")
            w = colour_graph(graph, "Welsh-Powell")
            st.dataframe(pd.DataFrame([
                {"Algorithm": "Greedy", "Subjects": len(g), "Slots Required": len(set(g.values()))},
                {"Algorithm": "Welsh–Powell", "Subjects": len(w), "Slots Required": len(set(w.values()))}
            ]), use_container_width=True, hide_index=True)

        assignments = st.session_state.get("assignments", {})
        if assignments:
            st.subheader("Manual slot adjustment")
            st.caption("Change a subject's slot, then validate. Conflicting subjects cannot share a slot.")
            subject_to_edit = st.selectbox("Subject to move", sorted(assignments))
            max_slot = max(assignments.values()) + 1
            chosen_slot = st.number_input("New slot number", min_value=1, max_value=max(1, len(subjects)), value=int(assignments[subject_to_edit]) + 1, step=1)
            if st.button("Apply slot change"):
                candidate = dict(assignments)
                candidate[subject_to_edit] = int(chosen_slot) - 1
                issues = validate_slots(graph, candidate)
                if issues:
                    st.error("Change rejected: this would place conflicting subjects in the same slot.")
                    st.write(pd.DataFrame([{"Subject 1": a, "Subject 2": b} for a,b in issues]))
                else:
                    st.session_state["assignments"] = candidate
                    st.success("Slot updated successfully.")
                    st.rerun()

            assignments = st.session_state.get("assignments", assignments)
            problems = validate_slots(graph, assignments)
            if problems:
                st.error("The current timetable contains conflicts.")
            else:
                st.success("Timetable is valid: no conflicting subjects share a slot.")
            timetable = pd.DataFrame([
                {"Exam Slot": f"Slot {slot+1}", "Subject": subject}
                for subject, slot in sorted(assignments.items(), key=lambda x: (x[1], x[0].casefold()))
            ])
            st.dataframe(timetable, use_container_width=True, hide_index=True)
            algorithm = st.session_state.get("algorithm", method)
            st.download_button("Download CSV", make_timetable_csv(assignments, algorithm),
                               "graphcolor_timetable.csv", "text/csv")
            st.download_button("Download Excel", make_timetable_xlsx(assignments, algorithm),
                               "graphcolor_timetable.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download PDF", make_timetable_pdf(assignments, algorithm),
                               "graphcolor_timetable.pdf", "application/pdf")

# IMPORT
elif page == "Import Data":
    st.header("Import Student Data")
    st.write("CSV or Excel file must contain columns `student_id` and `subjects`.")
    st.code("student_id,subjects\nS001,Maths;Physics;Python\nS002,Java;Python", language="csv")
    uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])
    if uploaded and st.button("Import records", type="primary"):
        try:
            records = parse_import(uploaded)
            for sid, subs in records:
                save_student(sid, subs)
            st.success(f"Imported {len(records)} student records.")
            st.rerun()
        except Exception as error:
            st.error(f"Import failed: {error}")

# PROJECT INFORMATION
elif page == "Project Information":
    st.header("About GraphColor")
    st.subheader("Project objective")
    st.write("GraphColor automates examination timetabling by representing subjects as vertices in a conflict graph and using graph-colouring algorithms to assign examination slots.")
    st.subheader("Graph theory concepts")
    st.markdown("""
    - **Vertex:** A subject in the examination timetable.
    - **Edge:** A conflict between two subjects because at least one student is registered in both.
    - **Degree:** Number of subjects that conflict with a particular subject.
    - **Graph colouring:** Assigning colours (examination slots) so adjacent vertices receive different colours.
    - **Chromatic number:** The minimum number of colours needed for a graph.
    """)
    st.subheader("Algorithms used")
    st.markdown("""
    **Greedy colouring:** Processes subjects in a fixed order and assigns the first available slot.

    **Welsh–Powell colouring:** Processes subjects in descending order of degree before assigning the first available slot. This heuristic can often produce a compact timetable, but it does not guarantee the minimum possible number of slots.
    """)
    st.subheader("System workflow")
    st.write("Register or import students → build the conflict graph → detect conflicts → run graph colouring → review and validate the timetable → export the timetable.")
    st.subheader("Limitations")
    st.write("The algorithms are heuristics. A timetable with the fewest slots is not guaranteed to be globally optimal. Real institutions may also need room capacity, invigilator, availability, and exam-duration constraints.")
