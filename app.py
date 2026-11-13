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
