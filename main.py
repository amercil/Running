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

# --- UI FRONTEND (The Dashboard) ---
st.title("🏃‍♂️ The Lactic Lab")
st.subheader("Varsity Pack Analyzer")
st.write("Upload your team roster to calculate course-adjusted 5k predictions and Varsity scoring metrics.")

st.divider()

# 1. The File Uploader
uploaded_file = st.file_uploader("Upload your team roster (CSV)", type=["csv"])

if uploaded_file is not None:
    # Read and display the data
    team_data = pd.read_csv(uploaded_file)
    st.success("Roster successfully loaded!")
    st.dataframe(team_data, use_container_width=True)
    
    st.divider()
    
    # 2. The Analytics Trigger
    if st.button("Run Team Analytics", type="primary", use_container_width=True):
        
        team_runners = []
        
        # Loop through the uploaded Pandas dataframe row by row
        for index, row in team_data.iterrows():
            name = row['Name']
            time_1600 = parse_time(row['1600m'])
            
            # Default to 1.0 if the column is missing or blank
            course_rating = float(row.get('Course_Rating', 1.0)) 
            
            # The Prediction Math
            if time_1600 > 0:
                predicted_track_5k = time_1600 * 3.3
                predicted_xc_5k = predicted_track_5k * course_rating
                
                team_runners.append({
                    'name': name,
                    'predicted_5k': predicted_xc_5k
                })
        
        # --- VARSITY SCORING ALGORITHM ---
        
        # Sort fastest to slowest
        team_runners.sort(key=lambda x: x['predicted_5k'])
        
        # Slice the top 5
        varsity_squad = team_runners[:5]
        
        # Display the Varsity Squad using columns for a cool UI layout
        st.subheader("🏆 Predicted Varsity Squad")
        cols = st.columns(5)
        
        for i, runner in enumerate(varsity_squad):
            with cols[i]:
                # st.metric creates large, bold numbers on the dashboard
                st.metric(label=f"#{i+1} Runner", 
                          value=runner['name'], 
                          delta=format_time(runner['predicted_5k']),
                          delta_color="off")
        
        # Calculate and Display Team Metrics
        if len(varsity_squad) >= 5:
            st.divider()
            st.subheader("📊 Team Metrics")
            
            number_1_time = varsity_squad[0]['predicted_5k']
            number_5_time = varsity_squad[4]['predicted_5k']
            pack_split = number_5_time - number_1_time
            
            st.metric(label="1-to-5 Pack Split", value=format_time(pack_split))
            
            # AI Coaching Logic
            if pack_split <= 60:
                st.success("**Analysis: ELITE.** A sub-60 second split is State-Championship caliber.")
            elif pack_split <= 120:
                st.info("**Analysis: SOLID.** The pack is strong, but the #4 and #5 need to bridge up.")
            else:
                st.warning("**Analysis: VULNERABLE.** Spread is too wide. The team will leak points in the middle.")
else:
    st.info("Awaiting roster upload. Please drop your CSV file above to begin.")