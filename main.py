import streamlit as st
import pandas as pd

# --- HELPER FUNCTIONS (The Brains) ---
def format_time(seconds):
    minutes = int(seconds // 60)
    sec = seconds % 60
    return f"{minutes}:{sec:05.2f}"

def parse_time(time_str):
    try:
        parts = str(time_str).split(':')
        minutes = int(parts[0])
        seconds = float(parts[1])
        return (minutes * 60) + seconds
    except:
        return 0

def calculate_xc_splits(predicted_5k_sec):
    # A 5k is exactly 3.10686 miles
    avg_mile = predicted_5k_sec / 3.10686
    
    # XC Racing Algorithm
    mile_1 = avg_mile - 5  # Get out fast to establish position
    mile_2 = avg_mile + 5  # Settle in / Handle the hills
    mile_3 = avg_mile      # Push the threshold
    
    return format_time(mile_1), format_time(mile_2), format_time(mile_3)

# --- UI FRONTEND (The Dashboard) ---
st.title("🏃‍♂️ The Lactic Lab")
st.subheader("Varsity Pack Analyzer & Pacing")
st.write("Upload your team roster to calculate course-adjusted 5k predictions and target race splits.")

st.divider()

# 1. The File Uploader
uploaded_file = st.file_uploader("Upload your team roster (CSV)", type=["csv"])

if uploaded_file is not None:
    team_data = pd.read_csv(uploaded_file)
    st.success("Roster successfully loaded!")
    st.dataframe(team_data, use_container_width=True)
    
    st.divider()
    
    # 2. The Analytics Trigger
    if st.button("Run Team Analytics", type="primary", use_container_width=True):
        
        team_runners = []
        
        for index, row in team_data.iterrows():
            name = row['Name']
            time_1600 = parse_time(row['1600m'])
            course_rating = float(row.get('Course_Rating', 1.0)) 
            
            if time_1600 > 0:
                predicted_track_5k = time_1600 * 3.3
                predicted_xc_5k = predicted_track_5k * course_rating
                
                team_runners.append({
                    'name': name,
                    'predicted_5k': predicted_xc_5k
                })
        
        # --- VARSITY SCORING ---
        team_runners.sort(key=lambda x: x['predicted_5k'])
        varsity_squad = team_runners[:5]
        
        st.subheader("🏆 Predicted Varsity Squad")
        cols = st.columns(5)
        
        for i, runner in enumerate(varsity_squad):
            with cols[i]:
                st.metric(label=f"#{i+1} Runner", 
                          value=runner['name'], 
                          delta=format_time(runner['predicted_5k']),
                          delta_color="off")
        
        # --- NEW: RACE EXECUTION PLAN ---
        st.divider()
        st.subheader("⏱️ Varsity Race Execution Plan")
        st.write("Target splits based on an aggressive Mile 1 start and settling into threshold pace.")
        
        pacing_data = []
        
        for runner in varsity_squad:
            m1, m2, m3 = calculate_xc_splits(runner['predicted_5k'])
            
            pacing_data.append({
                "Athlete": runner['name'],
                "Target Finish": format_time(runner['predicted_5k']),
                "Mile 1 (Fast Start)": m1,
                "Mile 2 (Settle)": m2,
                "Mile 3 (Kick)": m3
            })
            
        # Convert our pacing data into a sleek Pandas dataframe and display it
        pacing_df = pd.DataFrame(pacing_data)
        st.dataframe(pacing_df, use_container_width=True)
        
        # --- TEAM METRICS ---
        if len(varsity_squad) >= 5:
            st.divider()
            st.subheader("📊 Team Metrics")
            
            number_1_time = varsity_squad[0]['predicted_5k']
            number_5_time = varsity_squad[4]['predicted_5k']
            pack_split = number_5_time - number_1_time
            
            st.metric(label="1-to-5 Pack Split", value=format_time(pack_split))
            
            if pack_split <= 60:
                st.success("**Analysis: ELITE.** A sub-60 second split is State-Championship caliber.")
            elif pack_split <= 120:
                st.info("**Analysis: SOLID.** The pack is strong, but the #4 and #5 need to bridge up.")
            else:
                st.warning("**Analysis: VULNERABLE.** Spread is too wide. The team will leak points in the middle.")
else:
    st.info("Awaiting roster upload. Please drop your CSV file above to begin.")