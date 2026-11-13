import streamlit as st
import sqlite3, io, csv
from collections import defaultdict
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx

st.set_page_config(page_title="GraphColor", page_icon="🎓", layout="wide")
DB = "graphcolor_students.db"

def connect():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS registrations(
            student_id TEXT NOT NULL, subject TEXT NOT NULL,
            PRIMARY KEY(student_id, subject))""")

def load_students():
    data = defaultdict(set)
    with connect() as con:
        rows = con.execute("SELECT student_id, subject FROM registrations ORDER BY student_id, subject").fetchall()
    for sid, subject in rows:
        data[sid].add(subject)
    return data

def save_student(sid, subjects):
    with connect() as con:
        for subject in subjects:
            con.execute("INSERT OR IGNORE INTO registrations VALUES (?, ?)", (sid, subject))

def make_graph(data):
    graph = nx.Graph()
    subject_students = defaultdict(set)
    for sid, subjects in data.items():
        for subject in subjects:
            graph.add_node(subject)
            subject_students[subject].add(sid)
    conflicts = []
    nodes = sorted(graph.nodes())
    for i, a in enumerate(nodes):
        for b in nodes[i+1:]:
            shared = sorted(subject_students[a] & subject_students[b])
            if shared:
                graph.add_edge(a, b)
                conflicts.append((a, b, shared))
    return graph, conflicts

def greedy(graph, degree_order=False):
    order = sorted(graph.nodes(), key=lambda n: (-graph.degree[n], str(n).casefold())) if degree_order else sorted(graph.nodes())
    result = {}
    for node in order:
        used = {result[n] for n in graph.neighbors(node) if n in result}
        color = 0
        while color in used:
            color += 1
        result[node] = color
    return result

def get_slots(coloring):
    slots = defaultdict(list)
    for subject, slot in coloring.items():
        slots[slot].append(subject)
    return slots

init_db()
students = load_students()
graph, conflicts = make_graph(students)
st.title("🎓 GraphColor")
st.caption("AUTOMATED EXAMINATION TIMETABLING SYSTEM · GRAPH COLOURING")
page = st.sidebar.radio("Navigation", ["Dashboard", "Student Records", "Conflict Analysis", "Conflict Graph", "Generate Timetable", "Import Data"])

if page == "Dashboard":
    st.header("Dashboard")
    a,b,c,d = st.columns(4)
    a.metric("Registered Students", len(students))
    b.metric("Total Subjects", graph.number_of_nodes())
    c.metric("Subject Conflicts", len(conflicts))
    saved = st.session_state.get("coloring", {})
    d.metric("Timetable Slots", len(set(saved.values())) if saved else 0)
    st.subheader("Register a student")
    with st.form("register", clear_on_submit=True):
        x,y = st.columns([1,2])
        sid = x.text_input("Student ID")
        raw = y.text_input("Subjects (separate with commas)", placeholder="Maths, Physics, Python")
        submit = st.form_submit_button("Add Student", type="primary")
    if submit:
        subjects = {s.strip() for s in raw.replace(";", ",").split(",") if s.strip()}
        if not sid.strip() or not subjects:
            st.error("Enter a student ID and at least one subject.")
        else:
            save_student(sid.strip().upper(), subjects)
            st.success("Student registration saved.")
            st.rerun()
    st.subheader("Recent registrations")
    if students:
        st.dataframe(pd.DataFrame([{"Student ID": k, "Subjects": ", ".join(sorted(v)), "Subject Count": len(v)} for k,v in sorted(students.items())]), use_container_width=True, hide_index=True)
    else:
        st.info("No registrations yet. Add a student or import a file.")
    with st.expander("Clear all student registrations"):
        st.warning("This permanently deletes every student registration.")
        confirm = st.checkbox("I understand")
        if st.button("Delete all records", disabled=not confirm):
            with connect() as con:
                con.execute("DELETE FROM registrations")
            st.session_state.pop("coloring", None)
            st.rerun()

elif page == "Student Records":
    st.header("Student Records")
    if students:
        st.dataframe(pd.DataFrame([{"Student ID": k, "Registered Subjects": ", ".join(sorted(v)), "Subject Count": len(v)} for k,v in sorted(students.items())]), use_container_width=True, hide_index=True)
    else:
        st.info("No student records available.")

elif page == "Conflict Analysis":
    st.header("Conflict Analysis")
    st.write("Two subjects conflict when at least one student is registered in both.")
    st.metric("Total subject conflicts", len(conflicts))
    if conflicts:
        st.dataframe(pd.DataFrame([{"Subject 1":a,"Subject 2":b,"Common Students":", ".join(shared)} for a,b,shared in conflicts]), use_container_width=True, hide_index=True)
    else:
        st.success("No subject conflicts found.")

elif page == "Conflict Graph":
    st.header("Subject Conflict Graph")
    st.caption("Each node represents a subject. An edge connects subjects with common students.")
    st.write(f"{graph.number_of_nodes()} vertices · {graph.number_of_edges()} edges")
    if not graph.nodes:
        st.info("Add student records first.")
    else:
        coloring = greedy(graph, degree_order=True)
        palette = ["#93C5FD","#86EFAC","#F9A8D4","#FDE68A","#C4B5FD","#67E8F9","#FDBA74","#CBD5E1"]
        fig, ax = plt.subplots(figsize=(10,6))
        pos = nx.spring_layout(graph, seed=42)
        nx.draw_networkx_edges(graph, pos, ax=ax, edge_color="#94A3B8", width=2)
        nx.draw_networkx_nodes(graph, pos, ax=ax, node_color=[palette[coloring[n] % len(palette)] for n in graph.nodes()], node_size=2500, edgecolors="#334155")
        nx.draw_networkx_labels(graph, pos, ax=ax, font_size=9, font_weight="bold")
        ax.axis("off")
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
        st.markdown("**Welsh–Powell slot grouping**")
        for slot, subjects in sorted(get_slots(coloring).items()):
            st.write(f"Slot {slot+1}: {', '.join(sorted(subjects))}")

elif page == "Generate Timetable":
    st.header("Generate Examination Timetable")
    if not students:
        st.info("Add or import student records first.")
    else:
        method = st.radio("Algorithm", ["Welsh–Powell", "Greedy"], horizontal=True)
        if st.button("Generate timetable", type="primary"):
            st.session_state.coloring = greedy(graph, degree_order=(method == "Welsh–Powell"))
            st.session_state.algorithm = method
        if st.button("Compare algorithms"):
            g = greedy(graph)
            w = greedy(graph, degree_order=True)
            st.dataframe(pd.DataFrame([{"Algorithm":"Greedy","Slots Required":len(set(g.values()))},{"Algorithm":"Welsh–Powell","Slots Required":len(set(w.values()))}]), hide_index=True)
        coloring = st.session_state.get("coloring", {})
        if coloring:
            slots = get_slots(coloring)
            st.success(f"{st.session_state.get('algorithm','')} generated {len(slots)} slots.")
            table = pd.DataFrame([{"Exam Slot":f"Slot {i+1}","Subjects":", ".join(sorted(v))} for i,v in sorted(slots.items())])
            st.dataframe(table, use_container_width=True, hide_index=True)
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["Exam Slot","Subjects","Algorithm","Generated On"])
            for i, subs in sorted(slots.items()):
                writer.writerow([f"Slot {i+1}",", ".join(sorted(subs)),st.session_state.get("algorithm",""),datetime.now().strftime("%Y-%m-%d %H:%M")])
            st.download_button("Download timetable CSV", buffer.getvalue(), "graphcolor_timetable.csv", "text/csv")

elif page == "Import Data":
    st.header("Import Student Data")
    st.write("Upload a CSV or Excel file with columns named `student_id` and `subjects`.")
    st.code("student_id,subjects\nS001,Maths;Physics;Python\nS002,Java;Python", language="csv")
    file = st.file_uploader("Choose CSV or XLSX", type=["csv","xlsx"])
    if file and st.button("Import records", type="primary"):
        try:
            df = pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
            cols = {str(c).strip().lower(): c for c in df.columns}
            id_col = next((cols[k] for k in ["student_id","student id","id"] if k in cols), None)
            sub_col = next((cols[k] for k in ["subjects","subject"] if k in cols), None)
            if id_col is None or sub_col is None:
                st.error("Required columns: student_id and subjects.")
            else:
                count = 0
                for _, row in df.iterrows():
                    sid = str(row[id_col]).strip().upper()
                    raw = str(row[sub_col]).strip()
                    if sid and sid != "NAN" and raw and raw.lower() != "nan":
                        subs = {s.strip() for s in raw.replace(";",",").split(",") if s.strip()}
                        if subs:
                            save_student(sid, subs)
                            count += 1
                st.success(f"Imported {count} student records.")
                st.rerun()
        except Exception as e:
            st.error(f"Import failed: {e}")

st.sidebar.divider()
st.sidebar.caption("GraphColor Web Edition")
