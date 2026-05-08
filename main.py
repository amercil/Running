import streamlit as st
import pandas as pd
import requests

# --- HELPER FUNCTIONS (The Brains) ---
def get_live_conditions():
    """Fetches real-time Temp and AQI for Windsor, CO using Open-Meteo."""
    try:
        lat, lon = 40.4775, -104.9047 # Windsor, CO coordinates
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m&temperature_unit=fahrenheit"
        aqi_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi"
        
        temp_data = requests.get(weather_url, timeout=5).json()
        aqi_data = requests.get(aqi_url, timeout=5).json()
        
        current_temp = temp_data['current']['temperature_2m']
        current_aqi = aqi_data['current']['us_aqi']
        return current_temp, current_aqi
    except Exception:
        return None, None

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

# --- DUMMY LEADERBOARD DATA (Edit these later!) ---
TOP_10_RECORDS = {
    "Boys 5K XC": [
        {"Rank": 1, "Name": "Justin W.", "Time": "16:12", "Year": 2012},
        {"Rank": 2, "Name": "Aiden M.", "Time": "16:14", "Year": 2025},
        {"Rank": 3, "Name": "Nic C.", "Time": "16:18", "Year": 1996},
        {"Rank": 4, "Name": "Cale E.", "Time": "16:34", "Year": 2016},
        {"Rank": 5, "Name": "Ben L.", "Time": "16:47", "Year": 2013},
        {"Rank": 6, "Name": "Alex M.", "Time": "16:51", "Year": 2012},
        {"Rank": 7, "Name": "Ryan K.", "Time": "17:01", "Year": 2012},
        {"Rank": 8, "Name": "Ryan S.", "Time": "17:12", "Year": 2017},
        {"Rank": 9, "Name": "Dillon S.", "Time": "17:26", "Year": 2013},
        {"Rank": 10, "Name": "Detcho W.", "Time": "17:26", "Year": 2020}
    ],
    "Girls 5K XC": [
        {"Rank": 1, "Name": "Morgan H", "Time": "18:20", "Year": 2018},
        {"Rank": 2, "Name": "Kyndel A.", "Time": "19:08", "Year": 2017},
        {"Rank": 3, "Name": "Evelyn M.", "Time": "19:46", "Year": 2018},
        {"Rank": 4, "Name": "Ally B.", "Time": "19:51", "Year": 2013},
        {"Rank": 5, "Name": "Brooke S.", "Time": "20:02", "Year": 2016},
        {"Rank": 6, "Name": "Shallene R.", "Time": "20:03", "Year": 2012},
        {"Rank": 7, "Name": "Tori T.", "Time": "20:04", "Year": 2013},
        {"Rank": 8, "Name": "Maggie B.", "Time": "20:09", "Year": 2021},
        {"Rank": 9, "Name": "Eden B.", "Time": "20:22", "Year": 2022},
        {"Rank": 10, "Name": "Stephanie W.", "Time": "20:28", "Year": 2010}
    ]
}

# General Recruiting Baselines
RECRUITING_STANDARDS = {
    "Boys 1600m": {"NCAA D1 (Top Tier)": "4:12", "NCAA D1 (Mid-Major)": "4:20", "NCAA D2 / NAIA Elite": "4:28", "NCAA D3 / NAIA": "4:40"},
    "Boys 3200m": {"NCAA D1 (Top Tier)": "9:05", "NCAA D1 (Mid-Major)": "9:25", "NCAA D2 / NAIA Elite": "9:40", "NCAA D3 / NAIA": "10:10"},
    "Boys 5K (XC)": {"NCAA D1 (Top Tier)": "15:15", "NCAA D1 (Mid-Major)": "15:45", "NCAA D2 / NAIA Elite": "16:15", "NCAA D3 / NAIA": "17:00"},
    "Girls 1600m": {"NCAA D1 (Top Tier)": "4:55", "NCAA D1 (Mid-Major)": "5:10", "NCAA D2 / NAIA Elite": "5:20", "NCAA D3 / NAIA": "5:40"},
    "Girls 3200m": {"NCAA D1 (Top Tier)": "10:40", "NCAA D1 (Mid-Major)": "11:15", "NCAA D2 / NAIA Elite": "11:40", "NCAA D3 / NAIA": "12:30"},
    "Girls 5K (XC)": {"NCAA D1 (Top Tier)": "17:45", "NCAA D1 (Mid-Major)": "18:45", "NCAA D2 / NAIA Elite": "19:30", "NCAA D3 / NAIA": "20:30"}
}

# --- UI FRONTEND (The Dashboard) ---
st.set_page_config(page_title="The Lactic Lab", layout="wide")
st.title("🏃‍♂️ The Lactic Lab")

# --- LIVE WEATHER SIDEBAR WIDGET ---
st.sidebar.header("🌤️ Live Windsor Conditions")
live_temp, live_aqi = get_live_conditions()

if live_temp is not None and live_aqi is not None:
    w_col1, w_col2 = st.sidebar.columns(2)
    w_col1.metric("Temp", f"{round(live_temp)}°F")
    w_col2.metric("AQI", f"{round(live_aqi)}")
    
    if live_aqi > 150:
        st.sidebar.error("🚨 AQI is Unhealthy. Move practice indoors.")
    elif live_aqi > 100:
        st.sidebar.warning("⚠️ AQI is High. Unhealthy for sensitive groups.")
    elif live_temp > 90:
        st.sidebar.warning("🔥 High heat. Hydrate and adjust pace targets.")
    else:
        st.sidebar.success("✅ Good training conditions!")
else:
    st.sidebar.info("Live data currently unavailable.")

st.sidebar.divider()

# --- SIDEBAR CONTROLS (Global) ---
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

# --- APP TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Team Analytics", "🎯 Goal Setter", "📅 Summer Training", "⏱️ Interval Math", "🏆 Record Board", "🎓 College Matcher"])

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
                st.bar_chart(chart_df, color="#ff4b4b")
                
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

                with train_col:
                    st.subheader("👟 Full Roster Training Paces")
                    training_data = []
                    for runner in home_runners:
                        easy, tempo, vo2 = calculate_training_paces(runner['predicted_5k'])
                        training_data.append({"Athlete": runner['name'], "Recovery (mi)": easy, "Tempo (mi)": tempo, "VO2 Max (1000m)": vo2})
                    training_df = pd.DataFrame(training_data)
                    st.dataframe(training_df, use_container_width=True)

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
        col_a.metric("800m Fitness Required", t800)
        col_b.metric("1600m Fitness Required", t1600)
        col_c.metric("3200m Fitness Required", t3200)

with tab3:
    st.header("📅 Summer Base Phase Calendar")
    st.write("Upload your coach's master CSV training plan to generate an interactive digital calendar and track your team's weekly mileage volume.")
    st.divider()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("1. Download the Template")
        st.write("If you don't have a plan set up yet, download this CSV template.")
    with col2:
        st.subheader("2. Upload Your Plan")
        plan_file = st.file_uploader("Upload Training Plan (CSV)", type=["csv"], key="training_plan")

    if plan_file is not None:
        st.divider()
        plan_df = pd.read_csv(plan_file)
        plan_df.columns = [str(c).strip().title() for c in plan_df.columns]
        
        if 'Date' in plan_df.columns and 'Miles' in plan_df.columns:
            try:
                plan_df['Date Object'] = pd.to_datetime(plan_df['Date'])
                plan_df = plan_df.sort_values(by="Date Object")
                plan_df['Date'] = plan_df['Date Object'].dt.strftime('%a, %b %d')
                plan_df['Week Number'] = plan_df['Date Object'].dt.isocalendar().week
                
                display_df = plan_df.drop(columns=['Date Object', 'Week Number'])
                st.subheader("🗓️ Daily Training Schedule")
                st.dataframe(display_df, use_container_width=True)
                
                st.divider()
                st.subheader("📈 Weekly Mileage Progression")
                weekly_miles = plan_df.groupby('Week Number')['Miles'].sum().reset_index()
                weekly_miles['Week'] = ["Week " + str(i+1) for i in range(len(weekly_miles))]
                st.bar_chart(weekly_miles.set_index('Week')['Miles'], color="#3366cc")
            except Exception:
                st.error("⚠️ There was an issue reading the dates.")

with tab4:
    st.header("⏱️ Interval Math Engine")
    st.write("Enter an athlete's target 5K time to automatically calculate standard workout splits and active recovery times based on cross-country physiology.")
    st.divider()

    int_col1, int_col2 = st.columns(2)
    with int_col1:
        interval_5k_input = st.text_input("Athlete's Target 5K Time (e.g., 18:00)", "18:00", key="int_5k")
        
        workout_type = st.selectbox("Select Track Workout", [
            "200m Repeats (Speed/Turnover)",
            "400m Repeats (Mile Race Pace)",
            "400m Repeats (VO2 Max)", 
            "400m Repeats (Threshold / Short Rest)",
            "800m Repeats (Race Pace)", 
            "1000m Repeats (Cruise Intervals)", 
            "1200m Repeats (VO2 Max)",
            "1 Mile Repeats (Threshold)"
        ])
    
    int_5k_sec = parse_time(interval_5k_input)

    if int_5k_sec > 0:
        base_400_pace = (int_5k_sec / 5000) * 400
        
        if workout_type == "200m Repeats (Speed/Turnover)":
            rep_time = (base_400_pace / 2) - 4
            recovery = 90
            reps_suggested = "8-12 reps"
            
        elif workout_type == "400m Repeats (Mile Race Pace)":
            rep_time = base_400_pace - 8
            recovery = 120
            reps_suggested = "8-10 reps"
            
        elif workout_type == "400m Repeats (VO2 Max)":
            rep_time = base_400_pace - 4 
            recovery = rep_time           
            reps_suggested = "10-12 reps"
            
        elif workout_type == "400m Repeats (Threshold / Short Rest)":
            rep_time = base_400_pace + 2
            recovery = 30
            reps_suggested = "12-16 reps"
            
        elif workout_type == "800m Repeats (Race Pace)":
            rep_time = (int_5k_sec / 5000) * 800  
            recovery = 120                        
            reps_suggested = "5-6 reps"
            
        elif workout_type == "1000m Repeats (Cruise Intervals)":
            rep_time = (int_5k_sec / 5000) * 1000 + 5 
            recovery = 60                             
            reps_suggested = "4-5 reps"
            
        elif workout_type == "1200m Repeats (VO2 Max)":
            rep_time = (int_5k_sec / 5000) * 1200 - 5
            recovery = 180
            reps_suggested = "3-4 reps"
            
        elif workout_type == "1 Mile Repeats (Threshold)":
            rep_time = (int_5k_sec / 5000) * 1609.34 + 20 
            recovery = 60                                 
            reps_suggested = "3-4 reps"
        
        with int_col2:
            st.info(f"**Suggested Volume:** {reps_suggested}")
            st.metric("🎯 Target Split (per rep)", format_time(rep_time))
            st.metric("⏱️ Suggested Recovery Time", format_time(recovery))

with tab5:
    st.header("🏆 Windsor All-Time Record Board")
    st.divider()
    rb_col1, rb_col2 = st.columns([2, 1])

    with rb_col1:
        event_choice = st.selectbox("Select Event List", list(TOP_10_RECORDS.keys()))
        record_df = pd.DataFrame(TOP_10_RECORDS[event_choice])
        st.dataframe(record_df, hide_index=True, use_container_width=True)

    with rb_col2:
        st.subheader("🎯 Chasing Greatness")
        user_pr = st.text_input("Your PR (e.g., 17:30)", key="pr_input")
        pr_sec = parse_time(user_pr)

        if pr_sec > 0:
            tenth_place_sec = parse_time(record_df.iloc[9]['Time'])
            if pr_sec <= tenth_place_sec:
                st.success("🔥 **Incredible!** You are officially fast enough to be on the All-Time Board!")
                st.balloons()
            else:
                st.info(f"Keep grinding! You need to drop **{format_time(pr_sec - tenth_place_sec)}** to bump the #10 spot.")

with tab6:
    st.header("🎓 College Recruiting Matcher")
    st.write("Enter an athlete's personal bests to see where they currently align with NCAA and NAIA program standards. *Note: These are general baseline standards for walk-on or roster consideration. Actual requirements vary heavily by school.*")
    st.divider()

    col_rec1, col_rec2 = st.columns([1, 2])

    with col_rec1:
        st.subheader("Athlete Profile")
        rec_event = st.selectbox("Select Event", list(RECRUITING_STANDARDS.keys()))
        rec_pr = st.text_input("Current PR (e.g., 16:30 or 4:45)", "16:30")
        pr_sec = parse_time(rec_pr)

    with col_rec2:
        st.subheader(f"📊 Standard Breakdown: {rec_event}")
        if pr_sec > 0:
            standards = RECRUITING_STANDARDS[rec_event]
            table_data = []
            for tier, time_str in standards.items():
                tier_sec = parse_time(time_str)
                gap = pr_sec - tier_sec
                if gap <= 0:
                    status = "✅ Achieved"
                    gap_text = "--"
                else:
                    status = "⏳ Keep Grinding"
                    gap_text = f"Need to drop {format_time(gap)}"
                table_data.append({"Division Tier": tier, "Target Standard": time_str, "Status": status, "Next Steps": gap_text})
                
            st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)
            st.info("💡 **Coach's Tip:** Hitting a time standard is just the first step! College coaches also look at grades, character, and consistency across multiple events. Be sure to fill out recruiting questionnaires on college athletic websites early.")