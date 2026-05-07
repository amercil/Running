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
        # 1. Clean up the text (remove hidden spaces)
        time_str = str(time_str).strip()
        
        # 2. Check for empty cells
        if time_str.lower() in ["", "0", "nan", "n/a", "none"]:
            return 0
            
        # 3. FIX: If someone used a period instead of a colon (e.g., 16.14 -> 16:14)
        if '.' in time_str and ':' not in time_str:
            time_str = time_str.replace('.', ':')
            
        parts = time_str.split(':')
        minutes = int(parts[0])
        seconds = float(parts[1])
        return (minutes * 60) + seconds
    except:
        return 0 # Silent fallback if it's completely unreadable text

def calculate_composite_5k(t800, t1600, t3200, t5k):
    track_implied_5ks = []
    
    if t3200 > 0: track_implied_5ks.append(t3200 * 1.6)
    if t1600 > 0: track_implied_5ks.append(t1600 * 3.35)
    if t800 > 0:  track_implied_5ks.append(t800 * 7.1)
    
    track_fitness = sum(track_implied_5ks) / len(track_implied_5ks) if track_implied_5ks else 0
    
    if t5k > 0 and track_fitness > 0:
        return (t5k * 0.7) + (track_fitness * 0.3)
    elif t5k > 0:
        return t5k
    elif track_fitness > 0:
        return track_fitness
    else:
        return 0 

def calculate_xc_splits(predicted_5k_sec):
    if predicted_5k_sec == 0: return "N/A", "N/A", "N/A"
    avg_mile = predicted_5k_sec / 3.10686
    
    mile_1 = avg_mile - 5  
    mile_2 = avg_mile + 5  
    mile_3 = avg_mile      
    
    return format_time(mile_1), format_time(mile_2), format_time(mile_3)

# --- UI FRONTEND (The Dashboard) ---
st.title("🏃‍♂️ The Lactic Lab")
st.subheader("Varsity Pack Analyzer & Pacing")
st.write("Calculations powered by a composite model of 800m, 1600m, 3200m, and historic 5k PRs.")

st.divider()

uploaded_file = st.file_uploader("Upload your team roster (CSV)", type=["csv"])

if uploaded_file is not None:
    team_data = pd.read_csv(uploaded_file)
    st.success("Roster successfully loaded!")
    st.dataframe(team_data, use_container_width=True)
    
    st.divider()
    
    if st.button("Run Team Analytics", type="primary", use_container_width=True):
        team_runners = []
        
        for index, row in team_data.iterrows():
            # FIX: Create a lowercase, space-free dictionary of the row so " 5K " just becomes "5k"
            clean_row = {str(k).strip().lower(): v for k, v in row.items()}
            
            name = clean_row.get('name', f"Runner {index}")
            
            # Now it doesn't matter if your CSV says 5K, 5k, or 5 k.
            t800 = parse_time(clean_row.get('800m', '0'))
            t1600 = parse_time(clean_row.get('1600m', '0'))
            t3200 = parse_time(clean_row.get('3200m', '0'))
            t5k = parse_time(clean_row.get('5k', '0'))
            
            course_rating = float(clean_row.get('course_rating', 1.0)) 
            
            base_5k = calculate_composite_5k(t800, t1600, t3200, t5k)
            
            if base_5k > 0:
                predicted_xc_5k = base_5k * course_rating
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
        
        # --- RACE EXECUTION PLAN ---
        st.divider()
        st.subheader("⏱️ Varsity Race Execution Plan")
        
        pacing_data = []
        for runner in varsity_squad:
            m1, m2, m3 = calculate_xc_splits(runner['predicted_5k'])
            pacing_data.append({
                "Athlete": runner['name'],
                "Target Finish": format_time(runner['predicted_5k']),
                "Mile 1": m1,
                "Mile 2": m2,
                "Mile 3": m3
            })
            
        st.dataframe(pd.DataFrame(pacing_data), use_container_width=True)
        
        # --- TEAM METRICS ---
        if len(varsity_squad) >= 5:
            st.divider()
            st.subheader("📊 Team Metrics")
            
            pack_split = varsity_squad[4]['predicted_5k'] - varsity_squad[0]['predicted_5k']
            st.metric(label="1-to-5 Pack Split", value=format_time(pack_split))
else:
    st.info("Awaiting roster upload. Please drop your CSV file above to begin.")