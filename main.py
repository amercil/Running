import streamlit as st
import pandas as pd
import os

# --- HELPER FUNCTIONS (The Brains) ---
def format_time(seconds):
    if seconds <= 0: return "N/A"
    minutes = int(seconds // 60)
    sec = seconds % 60
    return f"{minutes}:{sec:05.2f}"

def parse_time(time_str):
    try:
        time_str = str(time_str).strip()
        if time_str.lower() in ["", "0", "nan", "n/a", "none", "nt", "dns"]: return 0
        if '.' in time_str and ':' not in time_str: time_str = time_str.replace('.', ':')
        parts = time_str.split(':')
        return (int(parts[0]) * 60) + float(parts[1])
    except:
        return 0

def calculate_composite_5k(t800, t1600, t3200, t5k):
    track_implied_5ks = []
    if t3200 > 0: track_implied_5ks.append(t3200 * 1.6)
    if t1600 > 0: track_implied_5ks.append(t1600 * 3.35)
    if t800 > 0:  track_implied_5ks.append(t800 * 7.1)
    track_fitness = sum(track_implied_5ks) / len(track_implied_5ks) if track_implied_5ks else 0
    
    if t5k > 0 and track_fitness > 0: return (t5k * 0.7) + (track_fitness * 0.3)
    elif t5k > 0: return t5k
    elif track_fitness > 0: return track_fitness
    else: return 0 

def calculate_xc_splits(predicted_5k_sec, pace_offsets):
    if predicted_5k_sec == 0: return "N/A", "N/A", "N/A"
    avg_mile = predicted_5k_sec / 3.10686
    m1 = avg_mile + pace_offsets[0]
    m2 = avg_mile + pace_offsets[1]
    m3 = avg_mile + pace_offsets[2]
    return format_time(m1), format_time(m2), format_time(m3)

def calculate_training_paces(predicted_5k_sec):
    if predicted_5k_sec == 0: return "N/A", "N/A", "N/A"
    avg_mile = predicted_5k_sec / 3.10686
    easy_pace = avg_mile + 120       
    tempo_pace = avg_mile + 30       
    vo2_1000m = (predicted_5k_sec / 5) - 5  
    return format_time(easy_pace), format_time(tempo_pace), format_time(vo2_1000m)

def get_temp_penalty(temp_f):
    if temp_f > 60: return (temp_f - 60) * 1.5  
    elif temp_f < 35: return (35 - temp_f) * 1.0  
    return 0

def get_elevation_multiplier(race_elevation):
    elevation_diff = race_elevation - 4500
    percentage_change = (elevation_diff / 1000) * 0.01
    return 1.0 + percentage_change

def calculate_goal_track_times(target_xc_sec, elevation_mult, temp_penalty, course_mult):
    base_5k_needed = (target_xc_sec - temp_penalty) / (course_mult * elevation_mult)
    t3200_needed = base_5k_needed / 1.6
    t1600_needed = base_5k_needed / 3.35
    t800_needed = base_5k_needed / 7.1
    return format_time(t800_needed), format_time(t1600_needed), format_time(t3200_needed)

def standardize_roster(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    norm_df = pd.DataFrame()
    
    if 'name' in df.columns: norm_df['name'] = df['name']
    elif 'athlete' in df.columns: norm_df['name'] = df['athlete']
    elif 'first name' in df.columns and 'last name' in df.columns:
        norm_df['name'] = df['first name'] + " " + df['last name']
    else: norm_df['name'] = [f"Runner {i+1}" for i in range(len(df))]
        
    event_mappings = {
        '800m': ['800', '800m', '800 meters'],
        '1600m': ['1600', '1600m', '1600 meters', 'mile', '1 mile'],
        '3200m': ['3200', '3200m', '3200 meters', '2 mile', '2mile'],
        '5k': ['5k', '5000', '5000m', '5000 meters', 'xc']
    }
    
    for std_event, keywords in event_mappings.items():
        found = False
        for col in df.columns:
            if any(kw in col for kw in keywords) and 'relay' not in col and 'place' not in col:
                norm_df[std_event] = df[col].astype(str)
                found = True
                break
        if not found: norm_df[std_event] = '0'
            
    return norm_df

CO_COURSES = {
    "Standard Course (Average)": {"mult": 1.00, "splits": [-5, 5, 0]},
    "Liberty Bell (Blazing Fast)": {"mult": 0.98, "splits": [-10, 0, 10]}, 
    "NPEC / State Course (Hilly)": {"mult": 1.04, "splits": [-5, 15, -10]},
    "St. Vrain Invitational": {"mult": 1.01, "splits": [0, 5, -5]},
    "Standard Flat / Paved": {"mult": 0.99, "splits": [0, 0, 0]},
    "Standard Tough / Muddy": {"mult": 1.03, "splits": [5, 10, -15]}
}

def process_team_data(df, team_name, elevation_mult, temp_penalty, course_mult):
    runners = []
    for index, row in df.iterrows():
        name = row.get('name', f"Runner {index}")
        t800 = parse_time(row.get('800m', '0'))
        t1600 = parse_time(row.get('1600m', '0'))
        t3200 = parse_time(row.get('3200m', '0'))
        t5k = parse_time(row.get('5k', '0'))
        
        base_5k = calculate_composite_5k(t800, t1600, t3200, t5k)
        if base_5k > 0:
            predicted_xc_5k = (base_5k * course_mult * elevation_mult) + temp_penalty
            runners.append({'name': name, 'team': team_name, 'predicted_5k': predicted_xc_5k})
    return runners

# --- UI FRONTEND (The Dashboard) ---
st.set_page_config(page_title="The Lactic Lab | Windsor XC", page_icon="🏃‍♂️", layout="wide")

# --- BRANDED SIDEBAR ---
try:
    if os.path.exists("logo.png"):
        st.sidebar.image("logo.png", use_container_width=True)
    else:
        st.sidebar.markdown("## 🧙‍♂️ Windsor XC")
except Exception:
    # If the image file is corrupted or unreadable, fall back to text instead of crashing
    st.sidebar.markdown("## 🧙‍♂️ Windsor XC")

st.sidebar.markdown("*\"To give anything less than your best is to sacrifice the gift.\"* - Pre")
st.sidebar.divider()

st.sidebar.header("📍 Course Selection")
selected_course = st.sidebar.selectbox("Select Race Course", list(CO_COURSES.keys()))
course_multiplier = CO_COURSES[selected_course]["mult"]
course_pace_strategy = CO_COURSES[selected_course]["splits"]

st.sidebar.divider()

st.sidebar.header("⚙️ Race Day Conditions")
st.sidebar.write("Calculations are baselined for your home altitude (4,500 ft).")
race_temp = st.sidebar.slider("Race Temp (°F)", min_value=20, max_value=105, value=55, step=1)
race_elevation = st.sidebar.number_input("Race Elevation (ft)", min_value=0, max_value=12000, value=4500, step=100)

elevation_mult = get_elevation_multiplier(race_elevation)
temp_penalty_sec = get_temp_penalty(race_temp)

st.title("🏃‍♂️ The Lactic Lab")

tab1, tab2 = st.tabs(["📊 Team Analytics & Scouting", "🎯 Sub-X Goal Setter"])

with tab1:
    st.write("Upload raw CSV exports from Athletic.net or MileSplit. The app will automatically clean and map the data.")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        home_name = st.text_input("Home Team Name", "Windsor")
        home_file = st.file_uploader("Upload Home Roster", type=["csv"], key="home")
    with col2:
        away_name = st.text_input("Rival Team Name", "Rival HS")
        away_file = st.file_uploader("Upload Rival Roster", type=["csv"], key="away")

    if home_file is not None:
        raw_home_df = pd.read_csv(home_file)
        home_df = standardize_roster(raw_home_df)
        mode = "Dual Meet Simulator" if away_file is not None else "Single Team Analytics"
        
        if st.button(f"Run {mode}", type="primary", use_container_width=True):
            home_runners = process_team_data(home_df, home_name, elevation_mult, temp_penalty_sec, course_multiplier)
            
            if mode == "Single Team Analytics":
                home_runners.sort(key=lambda x: x['predicted_5k'])
                varsity_squad = home_runners[:5]
                
                st.subheader(f"🏆 {home_name} Predicted Varsity Squad")
                cols = st.columns(5)
                for i, runner in enumerate(varsity_squad):
                    with cols[i]:
                        st.metric(label=f"#{i+1} Runner", value=runner['name'], delta=format_time(runner['predicted_5k']), delta_color="off")
                
                st.divider()
                st.subheader("📊 Pack Spread Visualization")
                chart_df = pd.DataFrame({"Athlete": [r['name'] for r in varsity_squad], "Time (Seconds)": [r['predicted_5k'] for r in varsity_squad]}).set_index("Athlete")
                # Updated bar chart to match the new Windsor Maroon branding
                st.bar_chart(chart_df, color="#800000")
                
                st.divider()
                exec_col, train_col = st.columns(2)
                
                with exec_col:
                    st.subheader(f"⏱️ Varsity Race Execution: {selected_course}")
                    pacing_data = []
                    for runner in varsity_squad:
                        m1, m2, m3 = calculate_xc_splits(runner['predicted_5k'], course_pace_strategy)
                        pacing_data.append({"Athlete": runner['name'], "Target Finish": format_time(runner['predicted_5k']), "Mile 1": m1, "Mile 2": m2, "Mile 3": m3})
                    pacing_df = pd.DataFrame(pacing_data)
                    st.dataframe(pacing_df, use_container_width=True)
                    csv_export1 = pacing_df.to_csv(index=False).encode('utf-8')
                    st.download_button(label="📥 Download Race Plan", data=csv_export1, file_name="race_plan.csv", mime="text/csv", type="primary")

                with train_col:
                    st.subheader("👟 Full Roster Training Paces")
                    training_data = []
                    for runner in home_runners:
                        easy, tempo, vo2 = calculate_training_paces(runner['predicted_5k'])
                        training_data.append({"Athlete": runner['name'], "Recovery (mi)": easy, "Tempo (mi)": tempo, "VO2 Max (1000m)": vo2})
                    training_df = pd.DataFrame(training_data)
                    st.dataframe(training_df, use_container_width=True)
                    csv_export2 = training_df.to_csv(index=False).encode('utf-8')
                    st.download_button(label="📥 Download Training Paces", data=csv_export2, file_name="training_paces.csv", mime="text/csv", type="secondary")

            elif mode == "Dual Meet Simulator":
                raw_away_df = pd.read_csv(away_file)
                away_df = standardize_roster(raw_away_df)
                away_runners = process_team_data(away_df, away_name, elevation_mult, temp_penalty_sec, course_multiplier)
                
                all_runners = home_runners + away_runners
                all_runners.sort(key=lambda x: x['predicted_5k'])
                
                home_count, away_count, current_points = 0, 0, 1
                home_score, away_score = 0, 0
                scored_results = []
                
                for runner in all_runners:
                    team = runner['team']
                    if team == home_name:
                        home_count += 1
                        if home_count <= 7:
                            points = current_points
                            if home_count <= 5: home_score += points
                            scored_results.append({'Place': current_points, 'Name': runner['name'], 'Team': team, 'Time': format_time(runner['predicted_5k']), 'Points': points if home_count <= 5 else '(Displacer)'})
                            current_points += 1
                    elif team == away_name:
                        away_count += 1
                        if away_count <= 7:
                            points = current_points
                            if away_count <= 5: away_score += points
                            scored_results.append({'Place': current_points, 'Name': runner['name'], 'Team': team, 'Time': format_time(runner['predicted_5k']), 'Points': points if away_count <= 5 else '(Displacer)'})
                            current_points += 1

                st.divider()
                st.subheader("🏁 Dual Meet Simulation Results")
                st.markdown(f"### **{home_name}: {home_score}** | **{away_name}: {away_score}**")
                if home_score < away_score: st.success(f"🏆 {home_name} is projected to win!")
                elif away_score < home_score: st.error(f"⚠️ {away_name} is projected to win.")
                else: st.warning("🤝 Projected Tie! (Check 6th runner displacement).")
                st.dataframe(pd.DataFrame(scored_results), use_container_width=True)

    else:
        st.info("Awaiting roster upload. You can now drop raw Athletic.net or MileSplit CSV exports directly into the app.")

with tab2:
    st.header("🎯 The Sub-X Goal Setter")
    st.write(f"This tool calculates the track fitness required to hit a specific 5K goal. It automatically factors in your current sidebar settings (**{selected_course}**, **{race_temp}°F**, and **{race_elevation}ft** elevation).")
    
    st.divider()
    
    goal_input = st.text_input("Enter Target 5K Time (e.g., 16:30 or 20:00)", "16:30")
    goal_sec = parse_time(goal_input)
    
    if goal_sec > 0:
        t800, t1600, t3200 = calculate_goal_track_times(goal_sec, elevation_mult, temp_penalty_sec, course_multiplier)
        
        st.markdown(f"### To run **{goal_input}** under the current conditions, an athlete needs to be in shape for:")
        
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("800m Fitness Required", t800)
        with col_b:
            st.metric("1600m Fitness Required", t1600)
        with col_c:
            st.metric("3200m Fitness Required", t3200)
        
        st.info("💡 **Coach's Note:** They don't necessarily need to hit *all three* of these times, but they need an equivalent aerobic mix that averages out to these benchmarks.")