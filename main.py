import streamlit as st
import pandas as pd

# --- HELPER FUNCTIONS (The Brains) ---
def format_time(seconds):
    if seconds <= 0: return "N/A"
    minutes = int(seconds // 60)
    sec = seconds % 60
    return f"{minutes}:{sec:05.2f}"

def parse_time(time_str):
    try:
        time_str = str(time_str).strip()
        if time_str.lower() in ["", "0", "nan", "n/a", "none"]: return 0
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

def calculate_xc_splits(predicted_5k_sec):
    if predicted_5k_sec == 0: return "N/A", "N/A", "N/A"
    avg_mile = predicted_5k_sec / 3.10686
    return format_time(avg_mile - 5), format_time(avg_mile + 5), format_time(avg_mile)

def get_temp_penalty(temp_f):
    if temp_f > 60: return (temp_f - 60) * 1.5  
    elif temp_f < 35: return (35 - temp_f) * 1.0  
    return 0

def get_elevation_multiplier(race_elevation):
    elevation_diff = race_elevation - 4500
    percentage_change = (elevation_diff / 1000) * 0.01
    return 1.0 + percentage_change

# --- NEW: TEAM PROCESSING ENGINE ---
def process_team_data(df, team_name, elevation_mult, temp_penalty):
    runners = []
    for index, row in df.iterrows():
        clean_row = {str(k).strip().lower(): v for k, v in row.items()}
        name = clean_row.get('name', f"Runner {index}")
        t800 = parse_time(clean_row.get('800m', '0'))
        t1600 = parse_time(clean_row.get('1600m', '0'))
        t3200 = parse_time(clean_row.get('3200m', '0'))
        t5k = parse_time(clean_row.get('5k', '0'))
        course_rating = float(clean_row.get('course_rating', 1.0)) 
        
        base_5k = calculate_composite_5k(t800, t1600, t3200, t5k)
        if base_5k > 0:
            predicted_xc_5k = (base_5k * course_rating * elevation_mult) + temp_penalty
            runners.append({'name': name, 'team': team_name, 'predicted_5k': predicted_xc_5k})
    return runners

# --- UI FRONTEND (The Dashboard) ---
st.set_page_config(page_title="The Lactic Lab", layout="wide")
st.title("🏃‍♂️ The Lactic Lab")

st.sidebar.header("⚙️ Race Day Conditions")
st.sidebar.write("Calculations are baselined for your home altitude (4,500 ft).")
race_temp = st.sidebar.slider("Race Temp (°F)", min_value=20, max_value=105, value=55, step=1)
race_elevation = st.sidebar.number_input("Race Elevation (ft)", min_value=0, max_value=12000, value=4500, step=100)

st.write("Upload just your team for standard analytics, or upload a rival team to simulate a dual meet.")
st.divider()

# --- DUAL UPLOAD COLUMNS ---
col1, col2 = st.columns(2)
with col1:
    home_name = st.text_input("Home Team Name", "Windsor")
    home_file = st.file_uploader("Upload Home Roster", type=["csv"], key="home")
with col2:
    away_name = st.text_input("Rival Team Name", "Rival HS")
    away_file = st.file_uploader("Upload Rival Roster", type=["csv"], key="away")

if home_file is not None:
    home_df = pd.read_csv(home_file)
    mode = "Dual Meet Simulator" if away_file is not None else "Single Team Analytics"
    
    if st.button(f"Run {mode}", type="primary", use_container_width=True):
        elevation_mult = get_elevation_multiplier(race_elevation)
        temp_penalty_sec = get_temp_penalty(race_temp)
        
        home_runners = process_team_data(home_df, home_name, elevation_mult, temp_penalty_sec)
        
        # ==========================================
        # SCENARIO A: SINGLE TEAM MODE
        # ==========================================
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
            st.subheader("⏱️ Varsity Race Execution Plan")
            pacing_data = []
            for runner in varsity_squad:
                m1, m2, m3 = calculate_xc_splits(runner['predicted_5k'])
                pacing_data.append({"Athlete": runner['name'], "Target Finish": format_time(runner['predicted_5k']), "Mile 1": m1, "Mile 2": m2, "Mile 3": m3})
            pacing_df = pd.DataFrame(pacing_data)
            st.dataframe(pacing_df, use_container_width=True)
            
            csv_export = pacing_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download Split Cards (CSV)", data=csv_export, file_name="varsity_race_plan.csv", mime="text/csv", type="primary")

        # ==========================================
        # SCENARIO B: DUAL MEET SCORING MODE
        # ==========================================
        elif mode == "Dual Meet Simulator":
            away_df = pd.read_csv(away_file)
            away_runners = process_team_data(away_df, away_name, elevation_mult, temp_penalty_sec)
            
            # Combine both teams and sort by time
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
            
            # Display Scoreboard
            st.markdown(f"### **{home_name}: {home_score}** | **{away_name}: {away_score}**")
            if home_score < away_score:
                st.success(f"🏆 {home_name} is projected to win!")
            elif away_score < home_score:
                st.error(f"⚠️ {away_name} is projected to win.")
            else:
                st.warning("🤝 Projected Tie! (Check 6th runner displacement).")

            # Display Head-to-Head Table
            st.dataframe(pd.DataFrame(scored_results), use_container_width=True)

else:
    st.info("Awaiting roster upload. Please drop at least your home CSV file above to begin.")