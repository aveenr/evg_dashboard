import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# -------------------- Setup --------------------
st.set_page_config(layout="wide", page_title="Volunteer Booking Dashboard", page_icon="📋")


@st.cache_data(ttl=0)
def load_volunteers():
    try:
        df = pd.read_csv("volunteers_june.csv")
    except FileNotFoundError:
        df = pd.DataFrame(columns=["first_name", "last_name", "alias"])
    df["full_name"] = df["first_name"].fillna("").str.strip() + " " + df["last_name"].fillna("").str.strip()
    return df


@st.cache_data(ttl=0)
def load_events():
    try:
        return pd.read_csv("events_june.csv")
    except FileNotFoundError:
        cols = ["event_id", "type", "school_name", "event_name", "grade", "num_students", "date", "start_time",
                "end_time", "required"]
        return pd.DataFrame(columns=cols)


@st.cache_data(ttl=0)
def load_assignments():
    try:
        return pd.read_csv("assignments_june.csv")
    except FileNotFoundError:
        return pd.DataFrame(columns=["event_id", "volunteer"])


volunteers_df = load_volunteers()
events_df = load_events()
assignments_df = load_assignments()

name_map = pd.Series(volunteers_df.full_name.values,
                     index=volunteers_df.alias.fillna(volunteers_df.full_name)).to_dict()
assignments_df["volunteer"] = assignments_df["volunteer"].str.strip().map(name_map).fillna(assignments_df["volunteer"])
merged_df = assignments_df.merge(events_df, on="event_id", how="left")

if not merged_df.empty and {"date", "start_time", "end_time"}.issubset(merged_df.columns):
    merged_df["datetime_start"] = pd.to_datetime(
        merged_df["date"].fillna('') + " " + merged_df["start_time"].fillna(''), errors='coerce')
    merged_df["datetime_end"] = pd.to_datetime(merged_df["date"].fillna('') + " " + merged_df["end_time"].fillna(''),
                                               errors='coerce')
else:
    merged_df["datetime_start"] = pd.NaT
    merged_df["datetime_end"] = pd.NaT

page = st.sidebar.selectbox("Choose Page",
                            ["Dashboard", "Add Event", "Add Assignment", "Event Summary", "Event Details"])


def time_options(start_hour=8, end_hour=17):
    times = []
    current = datetime(2000, 1, 1, start_hour, 0)
    end = datetime(2000, 1, 1, end_hour, 0)
    while current <= end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)
    return times


type_prefix_map = {
    "grg": "GRG",
    "course": "COR",
    "guiding": "GUI",
}


def generate_event_id(events, prefix):
    existing_ids = events["event_id"].dropna().astype(str)
    filtered = [eid for eid in existing_ids if eid.startswith(prefix)]
    if not filtered:
        next_num = 1
    else:
        nums = [int(eid[len(prefix):]) for eid in filtered if eid[len(prefix):].isdigit()]
        next_num = max(nums) + 1 if nums else 1
    return f"{prefix}{next_num:03d}"


def show_dashboard():
    st.title("📋 Volunteer Booking Dashboard")
    st.markdown("Shows all events, courses, guidings, and GRGs with volunteer assignments.")

    filtered_df = merged_df.copy()

    # Volunteer filter
    volunteer_options = sorted(filtered_df["volunteer"].dropna().unique()) if not filtered_df.empty else []
    selected_volunteer = st.sidebar.selectbox("Volunteer Filter", ["All"] + volunteer_options)

    # Type filter
    type_options = sorted(events_df["type"].dropna().unique()) if not events_df.empty else []
    selected_type = st.sidebar.multiselect("Type Filter", type_options, default=type_options)

    # Date range filter with two separate pickers
    if not filtered_df.empty and filtered_df["datetime_start"].notnull().any():
        min_date = filtered_df["datetime_start"].min().date()
        max_date = filtered_df["datetime_start"].max().date()
    else:
        min_date, max_date = datetime.today().date(), datetime.today().date()

    start_date = st.sidebar.date_input("Start Date Filter", value=min_date)
    end_date = st.sidebar.date_input("End Date Filter", value=max_date)

    if start_date > end_date:
        st.sidebar.error("Start date must be before or equal to end date.")
        return

        # Columns filter
    all_columns = ["event_id", "type", "school_name", "event_name", "grade", "num_students", "volunteer"]
    selected_columns = st.sidebar.multiselect("Select columns to display (Date, Start, End always shown):", all_columns,
                                              default=all_columns)
    fixed_columns = ["date", "start_time", "end_time"]
    display_columns = fixed_columns + selected_columns

    # Apply filters
    if selected_volunteer != "All":
        filtered_df = filtered_df[filtered_df["volunteer"] == selected_volunteer]
    if selected_type:
        filtered_df = filtered_df[filtered_df["type"].isin(selected_type)]
    else:
        filtered_df = filtered_df.iloc[0:0]

    filtered_df = filtered_df[
        (filtered_df["datetime_start"].dt.date >= start_date) &
        (filtered_df["datetime_start"].dt.date <= end_date)
        ]

    if filtered_df.empty:
        st.info("No assignments found for selected filters.")
    else:
        st.dataframe(filtered_df.sort_values(by=["datetime_start", "volunteer"])[display_columns],
                     use_container_width=True)

    st.subheader("⚠️ Conflict Checker")
    conflicts = []

    for name in filtered_df["volunteer"].unique():
        sub = filtered_df[filtered_df["volunteer"] == name].sort_values(by="datetime_start")
        for i in range(1, len(sub)):
            prev = sub.iloc[i - 1]
            curr = sub.iloc[i]
            if prev["datetime_end"] > curr["datetime_start"]:
                conflicts.append(
                    f"{name} has overlapping bookings on {prev['date']} from {prev['start_time']} to {curr['start_time']} ({prev['type']} → {curr['type']})")

    grg_df = filtered_df[filtered_df["type"].str.lower() == "grg"]
    grg_counts = grg_df.groupby(["event_id", "date"]).volunteer.nunique().reset_index(name="volunteer_count")
    overbooked = grg_counts[grg_counts["volunteer_count"] > 2]
    for _, row in overbooked.iterrows():
        conflicts.append(
            f"GRG slot {row['event_id']} on {row['date']} is overbooked with {row['volunteer_count']} volunteers (max 2 allowed)")

    if conflicts:
        for msg in conflicts:
            st.warning(msg)
    else:
        st.success("✅ No conflicts found!")


def show_add_event():
    global events_df
    st.title("➕ Add New Event")

    type_labels = {"course": "Course", "grg": "GRG", "guiding": "Guiding"}
    event_type_display = st.selectbox("Select Event Type", options=list(type_labels.values()))
    event_type = [k for k, v in type_labels.items() if v == event_type_display][0]

    if event_type != "grg":
        school_name = st.text_input("School Name")
        event_name = st.text_input("Event Name")
        grade = st.text_input("Grade")
        num_students = st.number_input("Number of Students", min_value=0, step=1)
    else:
        school_name = ""
        event_name = "GRG Session"
        grade = ""
        num_students = 0

    date = st.date_input("Date")
    start_time = st.selectbox("Start Time", options=time_options(), index=0)
    end_times_filtered = [t for t in time_options() if t > start_time]
    end_time = st.selectbox("End Time", options=end_times_filtered, index=0)

    required = st.number_input("Required Volunteers", min_value=1, step=1, value=1)

    if st.button("Add Event"):
        if not event_name.strip():
            st.error("Event Name is required.")
        else:
            prefix = type_prefix_map.get(event_type, "EVT")
            new_event_id = generate_event_id(events_df, prefix)
            new_event = {
                "event_id": new_event_id,
                "type": event_type,
                "school_name": school_name,
                "event_name": event_name,
                "grade": grade,
                "num_students": num_students,
                "date": date.strftime("%Y-%m-%d"),
                "start_time": start_time,
                "end_time": end_time,
                "required": required
            }
            events_df = pd.concat([events_df, pd.DataFrame([new_event])], ignore_index=True)
            events_df.to_csv("events_june.csv", index=False)
            st.success(f"Event {new_event_id} added!")


def show_add_assignment():
    global assignments_df
    st.title("➕ Assign Volunteer to Event")

    # Load event and volunteer options
    if events_df.empty:
        st.warning("No events available. Add an event first.")
        return
    if volunteers_df.empty:
        st.warning("No volunteers available.")
        return

    # event_id_options = events_df["event_id"].tolist()
    #
    # selected_event_id = st.selectbox("Select Event ID", event_id_options)

    # Create event display options: "event_id - event_name - date"
    events_df["display"] = events_df.apply(
        lambda row: f"{row['event_id']} - {row['event_name']} - {row['date']}", axis=1
    )
    display_to_id = dict(zip(events_df["display"], events_df["event_id"]))
    event_display_options = events_df["display"].tolist()

    selected_display = st.selectbox("Select Event", event_display_options)
    if not selected_display:
        return

    selected_event_id = display_to_id[selected_display]

    # Show event details
    event_info = events_df[events_df["event_id"] == selected_event_id].iloc[0]
    st.markdown("**Event Details**")
    st.markdown(f"- 📚 **Type**: {event_info['type']}")
    # st.markdown(f"- 🏫 **School**: {event_info['school_name']}")    st.markdown(f"- 🏫 **School**: {event_info['school_name'] if pd.notna(event_info['school_name']) else 'NA'}")

    st.markdown(f"- 🎯 **Event Name**: {event_info['event_name']}")
    # st.markdown(f"- 🎒 **Grade**: {event_info['grade']}")    st.markdown(f"- 🏫 **School**: {event_info['grade'] if pd.notna(event_info['grade']) else 'NA'}")

    st.markdown(f"- 👥 **Students**: {event_info['num_students']}")
    st.markdown(f"- 📅 **Date**: {event_info['date']}")
    st.markdown(f"- 🕒 **Time**: {event_info['start_time']} - {event_info['end_time']}")
    st.markdown(f"- 🙋‍♂️ **Volunteers Needed**: {event_info['required']}")

    # Show currently assigned volunteers
    current_assigned = assignments_df[assignments_df["event_id"] == selected_event_id]["volunteer"].tolist()
    st.markdown("### Booked Volunteers")
    if current_assigned:
        st.write(", ".join(current_assigned))
    else:
        st.write("No volunteers assigned yet.")

    # Get volunteer selection
    volunteer_options = volunteers_df["full_name"].tolist()
    selected_volunteer = st.selectbox("Select Volunteer", volunteer_options)

    if st.button("Assign Volunteer"):
        # Check for duplicates
        if not assignments_df[(assignments_df["event_id"] == selected_event_id) &
                              (assignments_df["volunteer"] == selected_volunteer)].empty:
            st.warning("This volunteer is already assigned to the selected event.")
        else:
            new_assignment = {
                "event_id": selected_event_id,
                "volunteer": selected_volunteer
            }
            assignments_df = pd.concat([assignments_df, pd.DataFrame([new_assignment])], ignore_index=True)
            assignments_df.to_csv("assignments_june.csv", index=False)
            st.success(f"{selected_volunteer} assigned to {selected_event_id}.")

            #
    # volunteer = st.selectbox("Select Volunteer", options=sorted(volunteers_df["full_name"].dropna().unique()))
    #
    # event_display = (events_df["event_id"].astype(str) + " - " + events_df["event_name"]).tolist()
    # event_selected = st.selectbox("Select Event", options=event_display)
    # event_id_selected = event_selected.split(" - ")[0]
    #
    # if st.button("Assign Volunteer"):
    #     already_assigned = assignments_df[
    #         (assignments_df["event_id"] == event_id_selected) & (assignments_df["volunteer"] == volunteer)
    #         ]
    #     if not already_assigned.empty:
    #         st.warning("Volunteer already assigned to this event.")
    #     else:
    #         new_assign = {"event_id": event_id_selected, "volunteer": volunteer}
    #         assignments_df = pd.concat([assignments_df, pd.DataFrame([new_assign])], ignore_index=True)
    #         assignments_df.to_csv("assignments_june.csv", index=False)
    #         st.success(f"{volunteer} assigned to event {event_id_selected}")


def show_event_summary():
    global events_df, assignments_df

    st.title("📅 Event Summary")

    # Sidebar filters
    st.sidebar.header("Filters for Event Summary")

    type_filter = st.sidebar.multiselect("Filter by Type", options=sorted(events_df["type"].unique()),
                                         default=sorted(events_df["type"].unique()))

    # Two separate date pickers for range
    min_date = events_df["date"].min() if not events_df.empty else datetime.today().strftime("%Y-%m-%d")
    max_date = events_df["date"].max() if not events_df.empty else datetime.today().strftime("%Y-%m-%d")
    min_date_dt = datetime.strptime(min_date, "%Y-%m-%d") if isinstance(min_date, str) else min_date
    max_date_dt = datetime.strptime(max_date, "%Y-%m-%d") if isinstance(max_date, str) else max_date

    start_date = st.sidebar.date_input("Start Date", value=min_date_dt)
    end_date = st.sidebar.date_input("End Date", value=max_date_dt)

    if start_date > end_date:
        st.sidebar.error("Start date must be before or equal to end date.")
        return

    filtered_events = events_df[
        (events_df["type"].isin(type_filter)) &
        (pd.to_datetime(events_df["date"]) >= pd.to_datetime(start_date)) &
        (pd.to_datetime(events_df["date"]) <= pd.to_datetime(end_date))
        ].copy()

    # Calculate assigned volunteers per event
    assigned_counts = assignments_df.groupby("event_id").size().to_dict()
    filtered_events["assigned"] = filtered_events["event_id"].map(assigned_counts).fillna(0).astype(int)

    # Calculate required - assigned = still needed
    filtered_events["still_required"] = filtered_events["required"].astype(int) - filtered_events["assigned"]
    filtered_events["still_required"] = filtered_events["still_required"].apply(lambda x: x if x > 0 else 0)

    # Show table with details including still required
    display_cols = ["event_id", "type", "date", "start_time", "end_time", "event_name", "required", "assigned",
                    "still_required"]
    st.dataframe(filtered_events[display_cols].sort_values(by=["date", "type"]), use_container_width=True)


def show_event_details():
    global events_df, assignments_df, volunteers_df

    st.title("📋 Event Details")

    # Choose single event
    event_options = (events_df["event_id"].astype(str) + " - "
                     + events_df["event_name"] + " - "
                     + events_df["date"]).tolist()
    selected_event = st.selectbox("Select Event to View Details", options=event_options)
    if not selected_event:
        st.info("No events found.")
        return
    event_id = selected_event.split(" - ")[0]

    event = events_df[events_df["event_id"] == event_id]
    if event.empty:
        st.error("Selected event not found.")
        return

    event = event.iloc[0]

    # Event general info + required volunteers
    st.subheader(f" {event['event_id']} - {event['event_name']} - {event['date']}")
    st.markdown(f"""  
    **Type:** {event['type']}    
    **Date:** {event['date']}    
    **Start Time:** {event['start_time']}    
    **End Time:** {event['end_time']}    
    **School Name:** {event.get('school_name', '')}    
    **Grade:** {event.get('grade', '')}  
    **Number of Students:** {event.get('num_students', '')}    
    **Required Volunteers:** {event['required']}    
    """)

    # Assigned volunteers
    assigned_vols = assignments_df[assignments_df["event_id"] == event_id]["volunteer"].tolist()
    assigned_count = len(assigned_vols)
    required_count = int(event["required"])
    still_required = max(required_count - assigned_count, 0)

    # Booked names joined in the text block
    st.markdown("### Booked Volunteers")
    if assigned_vols:
        st.write(", ".join(assigned_vols))
    else:
        st.write("No volunteers booked yet.")

        # Big numbers side by side using st.success and st.error (no extra HTML)
    col1, col2 = st.columns(2)

    with col1:
        st.success(f"**Assigned:**\n\n# {assigned_count}")

    with col2:
        st.error(f"**Still Required:**\n\n# {still_required}")

    # -------------- Main app ------------------


if page == "Dashboard":
    show_dashboard()
elif page == "Add Event":
    show_add_event()
elif page == "Add Assignment":
    show_add_assignment()
elif page == "Event Summary":
    show_event_summary()
elif page == "Event Details":
    show_event_details()
