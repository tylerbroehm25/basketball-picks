import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import pytz

# Set page config
st.set_page_config(page_title="College Basketball Pick'Em", layout="wide", initial_sidebar_state="expanded")

# Initialize session state
if 'data_file' not in st.session_state:
    st.session_state.data_file = 'picks_data.json'

def load_data():
    """Load data from JSON file"""
    if os.path.exists(st.session_state.data_file):
        with open(st.session_state.data_file, 'r') as f:
            data = json.load(f)
            
            # Migrate old data structure if needed
            if 'seasons' not in data:
                # Convert old structure to new season-based structure
                data = migrate_to_seasons(data)
            
            return data
    
    # Default structure for new installations
    return {
        'seasons': {
            '2025-2026': {
                'active': True,
                'weeks': {},
                'locked': False
            }
        },
        'current_season': '2025-2026',
        'users': {},
        'pending_users': {},
        'settings': {
            'admin_password': 'admin123',
            'welcome_message': 'Welcome to College Basketball Pick\'Em! Make your picks each week and compete with friends.',
            'deadline_time': '16:30',  # 4:30 PM Pacific
            'timezone': 'America/Los_Angeles'
        }
    }

def migrate_to_seasons(old_data):
    """Migrate old data structure to new season-based structure"""
    new_data = {
        'seasons': {
            '2025-2026': {
                'active': True,
                'weeks': old_data.get('weeks', {}),
                'locked': False
            }
        },
        'current_season': '2025-2026',
        'users': {},
        'pending_users': {},
        'settings': old_data.get('settings', {
            'admin_password': 'admin123',
            'welcome_message': 'Welcome to College Basketball Pick\'Em!',
            'deadline_time': '16:30',
            'timezone': 'America/Los_Angeles'
        })
    }
    
    # Migrate participants to users
    for username, info in old_data.get('participants', {}).items():
        new_data['users'][username] = {
            'email': f"{username.lower().replace(' ', '')}@temp.com",
            'password': 'temppass123',
            'first_name': username.split()[0] if ' ' in username else username,
            'last_name': username.split()[-1] if ' ' in username and len(username.split()) > 1 else '',
            'display_name': info.get('display_name', username),
            'active': True,
            'approved': True,
            'is_admin': False,
            'picks': info.get('picks', {}),
            'seasons': ['2025-2026']
        }
    
    return new_data

def save_data(data):
    """Save data to JSON file"""
    with open(st.session_state.data_file, 'w') as f:
        json.dump(data, f, indent=2)

def check_game_locked(game_date_str, settings):
    """Check if a game is locked based on date and deadline time"""
    try:
        if not game_date_str or game_date_str == 'nan':
            return False
        
        # Parse the date
        game_date = datetime.strptime(game_date_str, '%Y-%m-%d')
        
        # Get deadline time
        deadline_time = settings.get('deadline_time', '16:30')
        hour, minute = map(int, deadline_time.split(':'))
        
        # Set deadline datetime
        tz = pytz.timezone(settings.get('timezone', 'America/Los_Angeles'))
        deadline = tz.localize(game_date.replace(hour=hour, minute=minute))
        
        # Current time in same timezone
        now = datetime.now(tz)
        
        return now >= deadline
    except:
        return False

def get_current_season_data(data):
    """Get data for current season"""
    current_season = data.get('current_season', '2025-2026')
    return data['seasons'].get(current_season, {})

def calculate_week_results(season_data, week_num, username, user_data):
    """Calculate wins and confidence points for a user for a specific week"""
    if str(week_num) not in season_data.get('weeks', {}):
        return 0, 0
    
    week_data = season_data['weeks'][str(week_num)]
    if not week_data.get('winners_set'):
        return 0, 0
    
    user_picks = user_data.get('picks', {}).get(str(week_num), {})
    if not user_picks:
        return 0, 0
    
    correct_picks = 0
    confidence_points = 0
    
    picks = user_picks.get('picks', {})
    confidence_assignments = {str(c[0]): c[1] for c in user_picks.get('confidence', [])}
    winners = week_data.get('winners', {})
    
    for game_id, pick in picks.items():
        # Try both string and int keys for backwards compatibility
        winner = winners.get(int(game_id)) or winners.get(str(game_id)) or winners.get(game_id)
        if winner and winner == pick:
            correct_picks += 1
            if str(game_id) in confidence_assignments:
                confidence_points += confidence_assignments[str(game_id)]
    
    return correct_picks, confidence_points

def get_season_standings(data, season_name):
    """Get standings for a specific season"""
    season_data = data['seasons'].get(season_name, {})
    standings = []
    
    for username, user_info in data['users'].items():
        if not user_info.get('approved') or not user_info.get('active'):
            continue
        if season_name not in user_info.get('seasons', []):
            continue
        
        total_wins = 0
        total_losses = 0
        total_confidence = 0
        
        for week in range(1, 17):
            if str(week) in season_data.get('weeks', {}) and season_data['weeks'][str(week)].get('winners_set'):
                week_wins, week_conf = calculate_week_results(season_data, week, username, user_info)
                week_games = len(user_info.get('picks', {}).get(str(week), {}).get('picks', {}))
                total_wins += week_wins
                total_losses += (week_games - week_wins) if week_games > 0 else 0
                total_confidence += week_conf
        
        standings.append({
            'Name': user_info['display_name'],
            'Wins': total_wins,
            'Losses': total_losses,
            'Confidence': total_confidence
        })
    
    standings_df = pd.DataFrame(standings)
    if not standings_df.empty:
        standings_df = standings_df.sort_values(['Wins', 'Confidence'], ascending=[False, False]).reset_index(drop=True)
        standings_df.index = standings_df.index + 1
    return standings_df

def all_picks_submitted(season_data, week_num, data):
    """Check if all active users have submitted picks for a week"""
    active_users = [u for u, info in data['users'].items() 
                   if info.get('approved') and info.get('active')]
    
    for username in active_users:
        user_picks = data['users'][username].get('picks', {}).get(str(week_num), {})
        if not user_picks or not user_picks.get('picks'):
            return False
    return True

# Initialize session state for login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_type = None
    st.session_state.username = None
    st.session_state.is_admin = False

# Main app
st.title("🏀 College Basketball Pick'Em")

data = load_data()

# Login/Registration section
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            login_type = st.radio("Login as:", ["Participant", "Administrator"])
        
        with col2:
            if login_type == "Administrator":
                with st.form("admin_login_form"):
                    admin_pass = st.text_input("Admin Password:", type="password", key="admin_login_pass")
                    submit_admin = st.form_submit_button("Login as Admin", type="primary")
                    
                    if submit_admin:
                        if admin_pass == data['settings']['admin_password']:
                            st.session_state.logged_in = True
                            st.session_state.user_type = "admin"
                            st.session_state.is_admin = True
                            st.session_state.username = "Admin"
                            st.rerun()
                        else:
                            st.error("❌ Incorrect password")
            else:
                with st.form("participant_login_form"):
                    email = st.text_input("Email:", key="participant_email")
                    password = st.text_input("Password:", type="password", key="participant_pass")
                    submit_participant = st.form_submit_button("Login as Participant", type="primary")
                    
                    if submit_participant:
                        # Find user by email
                        user_found = None
                        for username, user_info in data['users'].items():
                            if user_info.get('email', '').lower() == email.lower():
                                user_found = username
                                break
                        
                        if user_found and data['users'][user_found].get('approved'):
                            if data['users'][user_found].get('password') == password:
                                st.session_state.logged_in = True
                                st.session_state.user_type = "participant"
                                st.session_state.username = user_found
                                st.session_state.is_admin = data['users'][user_found].get('is_admin', False)
                                st.rerun()
                            else:
                                st.error("❌ Incorrect password")
                        elif user_found:
                            st.error("❌ Your account is pending approval")
                        else:
                            st.error("❌ User not found")
    
    with tab2:
        st.subheader("Register New Account")
        with st.form("registration_form"):
            reg_first = st.text_input("First Name:")
            reg_last = st.text_input("Last Name:")
            reg_email = st.text_input("Email:")
            reg_pass = st.text_input("Password:", type="password")
            reg_pass_confirm = st.text_input("Confirm Password:", type="password")
            
            submitted = st.form_submit_button("Register", type="primary")
            
            if submitted:
                if not all([reg_first, reg_last, reg_email, reg_pass]):
                    st.error("All fields are required")
                elif reg_pass != reg_pass_confirm:
                    st.error("Passwords don't match")
                elif reg_email.lower() in [u['email'].lower() for u in data['users'].values()]:
                    st.error("Email already registered")
                else:
                    # Add to pending users
                    username = f"{reg_first} {reg_last}"
                    data['pending_users'][username] = {
                        'email': reg_email,
                        'password': reg_pass,
                        'first_name': reg_first,
                        'last_name': reg_last,
                        'display_name': username,
                        'timestamp': datetime.now().isoformat()
                    }
                    save_data(data)
                    st.success("✅ Registration submitted! Awaiting admin approval.")

else:
    # User is logged in
    current_season = data.get('current_season', '2025-2026')
    season_data = get_current_season_data(data)
    
    # Sidebar
    with st.sidebar:
        st.write(f"**Logged in as:**")
        if st.session_state.user_type == "admin":
            st.write("🔑 Administrator")
        else:
            user_info = data['users'].get(st.session_state.username, {})
            st.write(f"👤 {user_info.get('display_name', st.session_state.username)}")
            if st.session_state.is_admin:
                st.write("🔑 (Admin Access)")
        
        st.write(f"**Season:** {current_season}")
        st.write("")
        
        if st.button("Logout", type="secondary"):
            st.session_state.logged_in = False
            st.session_state.user_type = None
            st.session_state.username = None
            st.session_state.is_admin = False
            st.rerun()
    
    # Admin or admin-access participant
    if st.session_state.user_type == "admin" or st.session_state.is_admin:
        st.subheader("⚙️ Administrator Dashboard")
        
        tabs = st.tabs([
            "📝 Set Games", 
            "✅ Mark Winners", 
            "✏️ Edit Picks",
            "📊 All Picks",
            "👁️ View Picks", 
            "🏆 Standings",
            "📈 Statistics",
            "👥 Users",
            "🗂️ Seasons",
            "📋 Rules",
            "⚙️ Settings"
        ])
        
        # Set Games Tab
        with tabs[0]:
            st.header("Set Games for Week")
            week_num = st.selectbox("Select Week:", range(1, 17), key="set_games_week")
            
            if str(week_num) not in season_data.get('weeks', {}):
                season_data['weeks'][str(week_num)] = {
                    'games': [],
                    'picks': {},
                    'winners_set': False,
                    'created_date': datetime.now().isoformat()
                }
            
            existing_games = season_data['weeks'][str(week_num)].get('games', [])
            if existing_games:
                st.info(f"Currently {len(existing_games)} games set for this week")
            
            st.write("**Enter Games:**")
            games = []
            
            for i in range(20):
                col1, col2, col3 = st.columns([2, 2, 1.5])
                with col1:
                    default_away = existing_games[i]['away'] if i < len(existing_games) else ""
                    away = st.text_input(f"Game {i+1} - Away:", 
                                       key=f"away_{week_num}_{i}",
                                       value=default_away,
                                       placeholder="e.g., Duke")
                with col2:
                    default_home = existing_games[i]['home'] if i < len(existing_games) else ""
                    home = st.text_input(f"Game {i+1} - Home:", 
                                       key=f"home_{week_num}_{i}",
                                       value=default_home,
                                       placeholder="e.g., UNC")
                with col3:
                    default_date = None
                    if i < len(existing_games) and existing_games[i].get('date'):
                        try:
                            default_date = datetime.strptime(existing_games[i]['date'], '%Y-%m-%d').date()
                        except:
                            pass
                    
                    game_date = st.date_input(f"Date:", 
                                            key=f"date_{week_num}_{i}",
                                            value=default_date,
                                            format="MM/DD/YYYY")
                
                if away and home:
                    games.append({
                        'away': away,
                        'home': home,
                        'date': game_date.strftime('%Y-%m-%d') if game_date else '',
                        'id': i
                    })
            
            st.write("---")
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("💾 Save Games", key="save_games", type="primary"):
                    if len(games) == 20:
                        season_data['weeks'][str(week_num)]['games'] = games
                        data['seasons'][current_season] = season_data
                        save_data(data)
                        st.success(f"✅ Saved 20 games for Week {week_num}!")
                        st.rerun()
                    else:
                        st.error(f"⚠️ You must enter all 20 games. Currently: {len(games)}/20")
            with col2:
                st.info(f"Games entered: {len(games)}/20")
        
        # Mark Winners Tab
        with tabs[1]:
            st.header("Mark Game Winners")
            week_num = st.selectbox("Select Week:", range(1, 17), key="mark_winners_week")
            
            if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)]['games']:
                week_data = season_data['weeks'][str(week_num)]
                winners = week_data.get('winners', {})
                
                st.write(f"### Week {week_num} Winners")
                
                new_winners = {}
                for game in week_data['games']:
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.write(f"**{game['away']}** @ **{game['home']}**")
                        if game.get('date'):
                            st.caption(game['date'])
                    with col2:
                        # Check both int and str keys for backwards compatibility
                        game_id = game['id']
                        existing_winner = winners.get(game_id) or winners.get(str(game_id))
                        
                        default_index = 0
                        if existing_winner == game['home']:
                            default_index = 1
                        elif existing_winner == game['away']:
                            default_index = 0
                        
                        winner = st.radio(
                            f"Winner:",
                            [game['away'], game['home']],
                            key=f"winner_{week_num}_{game['id']}",
                            horizontal=True,
                            index=default_index
                        )
                        new_winners[game['id']] = winner
                
                st.write("---")
                if st.button("💾 Save Winners", key="save_winners", type="primary"):
                    week_data['winners'] = new_winners
                    week_data['winners_set'] = True
                    
                    # Calculate results for all users
                    for username, user_info in data['users'].items():
                        if str(week_num) in user_info.get('picks', {}):
                            wins, conf = calculate_week_results(season_data, week_num, username, user_info)
                            user_info['picks'][str(week_num)]['correct_picks'] = wins
                            user_info['picks'][str(week_num)]['confidence_points'] = conf
                    
                    data['seasons'][current_season]['weeks'][str(week_num)] = week_data
                    save_data(data)
                    st.success(f"✅ Winners saved for Week {week_num}!")
                    st.rerun()
            else:
                st.info("No games set for this week yet.")
        
        # Edit Picks Tab
        with tabs[2]:
            st.header("Edit User Picks")
            week_num = st.selectbox("Select Week:", range(1, 17), key="edit_picks_week")
            
            active_users = [(u, info['display_name']) for u, info in data['users'].items() 
                          if info.get('approved') and info.get('active')]
            
            if active_users:
                user_options = {display: username for username, display in active_users}
                selected_display = st.selectbox("Select User:", list(user_options.keys()))
                selected_user = user_options[selected_display]
                
                if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)]['games']:
                    week_data = season_data['weeks'][str(week_num)]
                    user_picks = data['users'][selected_user].get('picks', {}).get(str(week_num), {})
                    
                    st.write(f"### Editing picks for {selected_display} - Week {week_num}")
                    
                    picks = {}
                    confidence_picks = []
                    
                    for i, game in enumerate(week_data['games']):
                        col1, col2, col3 = st.columns([3, 1.5, 1])
                        
                        with col1:
                            st.write(f"**Game {i+1}:** {game['away']} @ {game['home']}")
                        
                        with col2:
                            default_pick = None
                            if user_picks and str(game['id']) in user_picks.get('picks', {}):
                                existing_pick = user_picks['picks'][str(game['id'])]
                                default_pick = 0 if existing_pick == game['away'] else 1
                            
                            pick = st.radio(
                                f"Pick:",
                                [game['away'], game['home']],
                                key=f"edit_pick_{week_num}_{game['id']}",
                                horizontal=True,
                                index=default_pick
                            )
                            picks[game['id']] = pick
                        
                        with col3:
                            default_conf = "None"
                            if user_picks:
                                for conf_game_id, conf_val in user_picks.get('confidence', []):
                                    if conf_game_id == game['id']:
                                        default_conf = str(conf_val)
                            
                            confidence = st.selectbox(
                                f"Conf:",
                                ["None", "1", "2", "3"],
                                key=f"edit_conf_{week_num}_{game['id']}",
                                index=["None", "1", "2", "3"].index(default_conf)
                            )
                            if confidence != "None":
                                confidence_picks.append((game['id'], int(confidence)))
                    
                    st.write("---")
                    if st.button("💾 Save Picks", key="save_edited_picks", type="primary"):
                        conf_values = [c[1] for c in confidence_picks]
                        if len(confidence_picks) == 3 and len(set(conf_values)) == 3:
                            if 'picks' not in data['users'][selected_user]:
                                data['users'][selected_user]['picks'] = {}
                            
                            data['users'][selected_user]['picks'][str(week_num)] = {
                                'picks': picks,
                                'confidence': confidence_picks,
                                'submitted': datetime.now().isoformat()
                            }
                            save_data(data)
                            st.success(f"✅ Picks saved for {selected_display}!")
                            st.rerun()
                        else:
                            st.error("❌ Must assign exactly one each of 1, 2, and 3")
                else:
                    st.info("No games set for this week yet.")
            else:
                st.info("No active users found.")
        
        # All Picks Table Tab
        with tabs[3]:
            st.header("All Participant Picks")
            week_num = st.selectbox("Select Week:", range(1, 17), key="all_picks_week")
            
            if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)]['games']:
                week_data = season_data['weeks'][str(week_num)]
                games = week_data['games']
                winners = week_data.get('winners', {})
                winners_set = week_data.get('winners_set', False)
                
                # Build table
                table_data = []
                
                for game in games:
                    row = {
                        'Game': f"{game['away']} @ {game['home']}",
                        'Date': game.get('date', '')
                    }
                    
                    # Get the winner for this game
                    game_winner = winners.get(game['id']) or winners.get(str(game['id']))
                    
                    # Add each user's pick
                    for username, user_info in data['users'].items():
                        if not user_info.get('approved') or not user_info.get('active'):
                            continue
                        
                        user_picks = user_info.get('picks', {}).get(str(week_num), {})
                        if user_picks and str(game['id']) in user_picks.get('picks', {}):
                            pick = user_picks['picks'][str(game['id'])]
                            
                            # Check if confidence pick
                            conf_val = ""
                            for conf_id, conf in user_picks.get('confidence', []):
                                if conf_id == game['id']:
                                    conf_val = f" ({conf})"
                            
                            # Add color indicator if winners are set
                            if winners_set and game_winner:
                                if pick == game_winner:
                                    row[user_info['display_name']] = f"✓ {pick}{conf_val}"
                                else:
                                    row[user_info['display_name']] = f"✗ {pick}{conf_val}"
                            else:
                                row[user_info['display_name']] = pick + conf_val
                        else:
                            row[user_info['display_name']] = "-"
                    
                    table_data.append(row)
                
                if table_data:
                    df = pd.DataFrame(table_data)
                    
                    # Apply color styling if winners are set
                    if winners_set:
                        def color_picks(val):
                            if isinstance(val, str):
                                if val.startswith('✓'):
                                    return 'background-color: #90EE90'  # Light green
                                elif val.startswith('✗'):
                                    return 'background-color: #FFB6C1'  # Light red
                            return ''
                        
                        styled_df = df.style.applymap(color_picks)
                        st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Summary row
                    st.write("---")
                    st.write("### Summary")
                    summary = {}
                    summary_vertical = []
                    
                    for username, user_info in data['users'].items():
                        if not user_info.get('approved') or not user_info.get('active'):
                            continue
                        
                        user_picks = user_info.get('picks', {}).get(str(week_num), {})
                        if week_data.get('winners_set'):
                            wins, conf = calculate_week_results(season_data, week_num, username, user_info)
                            losses = 20 - wins
                            summary[user_info['display_name']] = f"{wins}-{losses} ({conf} Confidence Points)"
                            summary_vertical.append({
                                'Participant': user_info['display_name'],
                                'Record': f"{wins}-{losses}",
                                'Confidence Points': conf
                            })
                        else:
                            picks_count = len(user_picks.get('picks', {}))
                            summary[user_info['display_name']] = f"{picks_count}/20 picked"
                            summary_vertical.append({
                                'Participant': user_info['display_name'],
                                'Picks Submitted': f"{picks_count}/20"
                            })
                    
                    # Horizontal summary
                    summary_df = pd.DataFrame([summary])
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    
                    # Vertical summary for easier reading
                    if summary_vertical:
                        st.write("### Summary (Vertical View)")
                        vertical_df = pd.DataFrame(summary_vertical)
                        if week_data.get('winners_set'):
                            # Sort by wins, then confidence
                            vertical_df = vertical_df.sort_values(['Record', 'Confidence Points'], 
                                                                  ascending=[False, False],
                                                                  key=lambda x: x.map(lambda v: int(str(v).split('-')[0]) if '-' in str(v) else 0))
                        st.dataframe(vertical_df, use_container_width=True, hide_index=True)
            else:
                st.info("No games set for this week yet.")
        
        # View Picks Tab
        with tabs[4]:
            st.header("View Individual Picks")
            week_num = st.selectbox("Select Week:", range(1, 17), key="view_picks_week")
            
            if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)]['games']:
                week_data = season_data['weeks'][str(week_num)]
                
                participants_with_picks = [(u, data['users'][u]) for u in data['users'] 
                                          if str(week_num) in data['users'][u].get('picks', {})
                                          and data['users'][u].get('approved') and data['users'][u].get('active')]
                
                if not participants_with_picks:
                    st.info("No picks submitted yet.")
                else:
                    for username, user_info in participants_with_picks:
                        picks_data = user_info['picks'][str(week_num)]
                        
                        with st.expander(f"**{user_info['display_name']}**"):
                            picks = picks_data.get('picks', {})
                            confidence = {str(c[0]): c[1] for c in picks_data.get('confidence', [])}
                            
                            for game in week_data['games']:
                                game_id = str(game['id'])
                                if game_id in picks:
                                    pick = picks[game_id]
                                    conf_value = confidence.get(game_id, '')
                                    conf_str = f" ⭐ {conf_value}" if conf_value else ""
                                    
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.write(f"{game['away']} @ {game['home']}")
                                    with col2:
                                        st.write(f"**{pick}**{conf_str}")
            else:
                st.info("No games set for this week yet.")
        
        # Standings Tab
        with tabs[5]:
            st.header("Standings")
            
            view_type = st.radio("View:", ["Season Total", "Weekly", "Weekly Winners"], horizontal=True)
            
            if view_type == "Season Total":
                standings_df = get_season_standings(data, current_season)
                if not standings_df.empty:
                    # Don't show confidence for season total
                    display_df = standings_df[['Name', 'Wins', 'Losses']]
                    st.dataframe(display_df, use_container_width=True, hide_index=False)
                else:
                    st.info("No data available yet.")
            
            elif view_type == "Weekly Winners":
                st.subheader("Weekly Winners")
                
                weekly_winners_data = []
                
                for week in range(1, 17):
                    if str(week) in season_data.get('weeks', {}) and season_data['weeks'][str(week)].get('winners_set'):
                        week_results = []
                        
                        for username, user_info in data['users'].items():
                            if not user_info.get('approved') or not user_info.get('active'):
                                continue
                            if str(week) in user_info.get('picks', {}):
                                wins, conf = calculate_week_results(season_data, week, username, user_info)
                                week_results.append({
                                    'name': user_info['display_name'],
                                    'wins': wins,
                                    'conf': conf
                                })
                        
                        if week_results:
                            # Sort by wins, then confidence
                            week_results.sort(key=lambda x: (x['wins'], x['conf']), reverse=True)
                            
                            # Find all tied winners
                            top_wins = week_results[0]['wins']
                            top_conf = week_results[0]['conf']
                            
                            winners = [r for r in week_results if r['wins'] == top_wins and r['conf'] == top_conf]
                            
                            # Create winner names string
                            if len(winners) == 1:
                                winner_names = winners[0]['name']
                            else:
                                winner_names = ", ".join([w['name'] for w in winners])
                            
                            weekly_winners_data.append({
                                'Week': week,
                                'Winner(s)': winner_names,
                                'Record': f"{top_wins}-{20-top_wins}",
                                'Confidence Points': top_conf
                            })
                
                if weekly_winners_data:
                    winners_df = pd.DataFrame(weekly_winners_data)
                    st.dataframe(winners_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No completed weeks yet.")
            
            else:
                week_num = st.selectbox("Select Week:", range(1, 17), key="standings_week")
                
                if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)].get('winners_set'):
                    week_standings = []
                    
                    for username, user_info in data['users'].items():
                        if not user_info.get('approved') or not user_info.get('active'):
                            continue
                        if str(week_num) in user_info.get('picks', {}):
                            wins, conf = calculate_week_results(season_data, week_num, username, user_info)
                            losses = 20 - wins
                            week_standings.append({
                                'Name': user_info['display_name'],
                                'Wins': wins,
                                'Losses': losses,
                                'Confidence': conf
                            })
                    
                    if week_standings:
                        week_df = pd.DataFrame(week_standings)
                        week_df = week_df.sort_values(['Wins', 'Confidence'], ascending=[False, False]).reset_index(drop=True)
                        week_df.index = week_df.index + 1
                        st.dataframe(week_df, use_container_width=True, hide_index=False)
                    else:
                        st.info("No picks for this week yet.")
                else:
                    st.info("Week not completed yet.")
        
        # Statistics Tab
        with tabs[6]:
            st.header("📈 Season Statistics")
            
            stat_view = st.radio("View:", ["Personal Stats", "Team Performance"], horizontal=True)
            
            if stat_view == "Personal Stats":
                st.subheader("Individual Performance Metrics")
                
                stats_data = []
                
                for username, user_info in data['users'].items():
                    if not user_info.get('approved') or not user_info.get('active'):
                        continue
                    
                    weekly_wins = []
                    total_conf_earned = 0
                    total_conf_possible = 0
                    
                    for week in range(1, 17):
                        if str(week) in season_data.get('weeks', {}) and season_data['weeks'][str(week)].get('winners_set'):
                            if str(week) in user_info.get('picks', {}):
                                wins, conf = calculate_week_results(season_data, week, username, user_info)
                                weekly_wins.append(wins)
                                total_conf_earned += conf
                                total_conf_possible += 6  # Max 6 points per week
                    
                    if weekly_wins:
                        total_wins = sum(weekly_wins)
                        total_games = len(weekly_wins) * 20
                        win_pct = (total_wins / total_games * 100) if total_games > 0 else 0
                        
                        best_week = max(weekly_wins) if weekly_wins else 0
                        worst_week = min(weekly_wins) if weekly_wins else 0
                        
                        # Consistency score (lower standard deviation = more consistent)
                        if len(weekly_wins) > 1:
                            mean_wins = sum(weekly_wins) / len(weekly_wins)
                            variance = sum((w - mean_wins) ** 2 for w in weekly_wins) / len(weekly_wins)
                            std_dev = variance ** 0.5
                            consistency = round(std_dev, 2)
                        else:
                            consistency = 0.0
                        
                        # Confidence efficiency
                        conf_efficiency = (total_conf_earned / total_conf_possible * 100) if total_conf_possible > 0 else 0
                        
                        stats_data.append({
                            'Participant': user_info['display_name'],
                            'Win %': f"{win_pct:.1f}%",
                            'Best Week': best_week,
                            'Worst Week': worst_week,
                            'Consistency': consistency,
                            'Confidence Eff.': f"{conf_efficiency:.1f}%"
                        })
                
                if stats_data:
                    stats_df = pd.DataFrame(stats_data)
                    st.dataframe(stats_df, use_container_width=True, hide_index=True)
                    
                    st.write("---")
                    st.caption("**Consistency**: Lower number = more consistent (standard deviation of weekly wins)")
                    st.caption("**Confidence Efficiency**: % of possible confidence points earned")
                else:
                    st.info("No completed weeks yet.")
            
            else:  # Team Performance
                st.subheader("Performance by Team")
                
                # Normalize team names function
                def normalize_team_name(name):
                    if not name:
                        return ""
                    # Remove ** markers
                    name = name.replace('**', '').strip()
                    
                    # Preserve important qualifiers like (OH), (FL) before removing numbered duplicates
                    import re
                    
                    # First, handle Miami specifically - convert "Miami" alone to "Miami (FL)"
                    if name == "Miami" or (name.startswith("Miami") and not re.search(r'\((?:OH|FL)\)', name)):
                        # Check if it already has (1), (2), etc - remove those but default to (FL)
                        base_name = re.sub(r'\s*\(\d+\)\s*$', '', name)
                        if base_name == "Miami":
                            name = "Miami (FL)"
                    
                    # Remove ONLY numbered duplicates like (1), (2), but keep (OH), (FL), etc.
                    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
                    
                    # Normalize common variations
                    replacements = {
                        'Michigan St.': 'Michigan State',
                        'Michigan St': 'Michigan State',
                        'Miss. State': 'Mississippi State',
                        'Miss State': 'Mississippi State',
                        'Mississippi St.': 'Mississippi State',
                        'Mississippi St': 'Mississippi State',
                        'N. Carolina': 'North Carolina',
                        'NC State': 'NC State',
                    }
                    
                    for old, new in replacements.items():
                        if old in name:
                            name = name.replace(old, new)
                    
                    return name.strip()
                
                # Track team performance
                team_stats = {}
                
                for week in range(1, 17):
                    if str(week) not in season_data.get('weeks', {}):
                        continue
                    
                    week_data = season_data['weeks'][str(week)]
                    if not week_data.get('winners_set'):
                        continue
                    
                    winners = week_data.get('winners', {})
                    
                    for game in week_data.get('games', []):
                        away = normalize_team_name(game.get('away', ''))
                        home = normalize_team_name(game.get('home', ''))
                        game_id = game.get('id')
                        
                        winner = winners.get(game_id) or winners.get(str(game_id))
                        if not winner:
                            continue
                        
                        winner_norm = normalize_team_name(winner)
                        
                        # Initialize both teams if needed
                        for team in [away, home]:
                            if not team:
                                continue
                            if team not in team_stats:
                                team_stats[team] = {
                                    'games': 0,
                                    'wins': 0,
                                    'times_picked': 0,
                                    'correct_picks': 0
                                }
                            
                            # Track team's actual record
                            team_stats[team]['games'] += 1
                            if team == winner_norm:
                                team_stats[team]['wins'] += 1
                        
                        # Count picks for this game
                        for username, user_info in data['users'].items():
                            if not user_info.get('approved') or not user_info.get('active'):
                                continue
                            
                            user_picks = user_info.get('picks', {}).get(str(week), {}).get('picks', {})
                            pick = user_picks.get(str(game_id)) or user_picks.get(game_id)
                            
                            if not pick:
                                continue
                            
                            pick_norm = normalize_team_name(pick)
                            
                            # Track if they picked this team
                            if pick_norm == away:
                                team_stats[away]['times_picked'] += 1
                                if winner_norm == away:
                                    team_stats[away]['correct_picks'] += 1
                            elif pick_norm == home:
                                team_stats[home]['times_picked'] += 1
                                if winner_norm == home:
                                    team_stats[home]['correct_picks'] += 1
                
                # Build display table
                team_display = []
                for team, stats in team_stats.items():
                    games = stats['games']
                    wins = stats['wins']
                    losses = games - wins
                    
                    if games > 0:
                        team_win_pct = (wins / games * 100)
                        
                        times_picked = stats['times_picked']
                        pick_success = (stats['correct_picks'] / times_picked * 100) if times_picked > 0 else 0
                        
                        team_display.append({
                            'Team': team,
                            'Record': f"{wins}-{losses}",
                            'Team Win %': f"{team_win_pct:.1f}%",
                            'Times Picked': times_picked,
                            'Pick Success %': f"{pick_success:.1f}%"
                        })
                
                if team_display:
                    team_df = pd.DataFrame(team_display)
                    team_df = team_df.sort_values('Times Picked', ascending=False)
                    st.dataframe(team_df, use_container_width=True, hide_index=True)
                    
                    st.write("---")
                    st.caption("**Team Win %**: The team's actual win percentage")
                    st.caption("**Pick Success %**: When people picked this team, what % of the time did they win?")
                    st.caption("💡 **Insight**: If Pick Success % is much higher than Team Win %, people are picking this team in their best games!")
                else:
                    st.info("No team data available yet.")
        
        # Users Tab
        with tabs[7]:
            st.header("User Management")
            
            # Pending approvals
            if data.get('pending_users'):
                st.subheader("Pending Approvals")
                for username, pending_info in list(data['pending_users'].items()):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**{pending_info['display_name']}** ({pending_info['email']})")
                    with col2:
                        if st.button("✅ Approve", key=f"approve_{username}"):
                            data['users'][username] = {
                                **pending_info,
                                'active': True,
                                'approved': True,
                                'is_admin': False,
                                'picks': {},
                                'seasons': [current_season]
                            }
                            del data['pending_users'][username]
                            save_data(data)
                            st.success(f"Approved {username}")
                            st.rerun()
                    with col3:
                        if st.button("❌ Reject", key=f"reject_{username}"):
                            del data['pending_users'][username]
                            save_data(data)
                            st.success(f"Rejected {username}")
                            st.rerun()
                st.write("---")
            
            # Active users
            st.subheader("Active Users")
            for username, user_info in data['users'].items():
                if user_info.get('active'):
                    with st.expander(f"**{user_info['display_name']}** ({user_info['email']})"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Seasons:** {', '.join(user_info.get('seasons', []))}")
                            st.write(f"**Admin:** {'Yes' if user_info.get('is_admin') else 'No'}")
                        
                        with col2:
                            if st.button("🔄 Reset Password", key=f"reset_{username}"):
                                temp_pass = f"temp{datetime.now().strftime('%m%d')}"
                                data['users'][username]['password'] = temp_pass
                                save_data(data)
                                st.success(f"Password reset to: {temp_pass}")
                            
                            col2a, col2b = st.columns(2)
                            with col2a:
                                if st.button("📦 Archive", key=f"archive_{username}"):
                                    data['users'][username]['active'] = False
                                    save_data(data)
                                    st.success(f"Archived {username}")
                                    st.rerun()
                            with col2b:
                                if st.button("🗑️ Delete", key=f"delete_{username}", type="secondary"):
                                    del data['users'][username]
                                    save_data(data)
                                    st.success(f"Deleted {username}")
                                    st.rerun()
            
            # Archived users
            archived = [(u, info) for u, info in data['users'].items() if not info.get('active')]
            if archived:
                st.write("---")
                st.subheader("Archived Users")
                for username, user_info in archived:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**{user_info['display_name']}** ({user_info['email']})")
                    with col2:
                        if st.button("♻️ Reactivate", key=f"reactivate_{username}"):
                            data['users'][username]['active'] = True
                            save_data(data)
                            st.success(f"Reactivated {username}")
                            st.rerun()
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_archived_{username}", type="secondary"):
                            del data['users'][username]
                            save_data(data)
                            st.success(f"Deleted {username}")
                            st.rerun()
        
        # Seasons Tab
        with tabs[8]:
            st.header("Season Management")
            
            st.write(f"**Current Season:** {current_season}")
            
            # Create new season
            st.subheader("Create New Season")
            new_season_name = st.text_input("Season Name (e.g., 2026-2027):")
            if st.button("Create Season"):
                if new_season_name and new_season_name not in data['seasons']:
                    data['seasons'][new_season_name] = {
                        'active': False,
                        'weeks': {},
                        'locked': False
                    }
                    save_data(data)
                    st.success(f"Created season: {new_season_name}")
                    st.rerun()
            
            st.write("---")
            
            # Manage seasons
            st.subheader("All Seasons")
            for season_name, season_info in data['seasons'].items():
                with st.expander(f"**{season_name}** {'(Active)' if season_info.get('active') else ''}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if not season_info.get('active'):
                            if st.button("✅ Set Active", key=f"activate_{season_name}"):
                                # Deactivate all others
                                for s in data['seasons']:
                                    data['seasons'][s]['active'] = False
                                data['seasons'][season_name]['active'] = True
                                data['current_season'] = season_name
                                save_data(data)
                                st.rerun()
                    
                    with col2:
                        lock_text = "🔓 Unlock" if season_info.get('locked') else "🔒 Lock"
                        if st.button(lock_text, key=f"lock_{season_name}"):
                            data['seasons'][season_name]['locked'] = not season_info.get('locked')
                            save_data(data)
                            st.rerun()
                    
                    with col3:
                        weeks_completed = sum(1 for w in season_info.get('weeks', {}).values() if w.get('winners_set'))
                        st.write(f"Weeks: {weeks_completed}/16")
        
        # Rules Tab
        with tabs[9]:
            st.header("Rules & Information")
            
            st.markdown("""
            ### How to Play
            
            **Weekly Picks**
            - Each week features 20 college basketball games
            - Pick the winner for all 20 games
            - Assign confidence points (3, 2, 1) to your three most confident picks
            - You must use each value exactly once
            
            **Deadlines**
            - Picks lock at 4:30 PM Pacific / 7:30 PM Eastern on game day
            - If you miss the deadline for some games, you can still submit picks for remaining games
            - Once you submit your picks, they are locked for the week
            
            **Scoring**
            - 1 point for each correct pick
            - Confidence points awarded for correct confidence picks
            - Tiebreakers: Total wins, then confidence points for that week
            
            **Season**
            - 16 weeks per season
            - Season standings based on total wins (confidence points don't carry over)
            - Weekly winners determined by wins + confidence points
            
            **Viewing Other Picks**
            - You can see other participants' picks ONLY after everyone has submitted for that week
            - This keeps the competition fair and exciting!
            """)
        
        # Settings Tab
        with tabs[10]:
            st.header("Settings")
            
            st.subheader("Admin Password")
            new_pass = st.text_input("New Password:", type="password", key="new_admin_pass")
            confirm_pass = st.text_input("Confirm:", type="password", key="confirm_admin_pass")
            if st.button("Update Password"):
                if new_pass and new_pass == confirm_pass:
                    data['settings']['admin_password'] = new_pass
                    save_data(data)
                    st.success("✅ Password updated!")
                else:
                    st.error("Passwords don't match")
            
            st.write("---")
            
            st.subheader("Welcome Message")
            welcome_msg = st.text_area("Welcome message for participants:",
                                      value=data['settings'].get('welcome_message', ''),
                                      height=100)
            if st.button("Save Welcome Message"):
                data['settings']['welcome_message'] = welcome_msg
                save_data(data)
                st.success("✅ Welcome message updated!")
    
    # Participant view
    else:
        user_info = data['users'][st.session_state.username]
        
        # Welcome message
        st.info(data['settings'].get('welcome_message', 'Welcome!'))
        
        tabs = st.tabs(["📋 Make Picks", "🏆 Standings", "📊 My Results", "👁️ View Picks", "📋 Rules"])
        
        # Make Picks
        with tabs[0]:
            st.header("Make Your Picks")
            week_num = st.selectbox("Select Week:", range(1, 17), key="participant_week")
            
            if str(week_num) not in season_data.get('weeks', {}):
                st.info("Games not set for this week yet.")
            else:
                week_data = season_data['weeks'][str(week_num)]
                
                if not week_data.get('games'):
                    st.info("No games set for this week yet.")
                else:
                    existing_picks = user_info.get('picks', {}).get(str(week_num), {})
                    
                    if existing_picks:
                        st.success("✅ You've submitted picks for this week.")
                        st.info("Contact the admin if you need to make changes.")
                    
                    picks = {}
                    confidence_picks = []
                    
                    st.write("---")
                    for i, game in enumerate(week_data['games']):
                        # Check if game is locked
                        is_locked = check_game_locked(game.get('date'), data['settings'])
                        
                        col1, col2, col3 = st.columns([3, 1.5, 1])
                        
                        with col1:
                            game_text = f"**Game {i+1}:** {game['away']} @ {game['home']}"
                            if is_locked:
                                game_text += " 🔒"
                            st.write(game_text)
                            if game.get('date'):
                                st.caption(game['date'])
                        
                        if not is_locked:
                            with col2:
                                default_pick = None
                                if existing_picks and str(game['id']) in existing_picks.get('picks', {}):
                                    existing_pick = existing_picks['picks'][str(game['id'])]
                                    default_pick = 0 if existing_pick == game['away'] else 1
                                
                                pick = st.radio(
                                    f"Pick:",
                                    [game['away'], game['home']],
                                    key=f"pick_{week_num}_{game['id']}",
                                    horizontal=True,
                                    index=default_pick
                                )
                                picks[game['id']] = pick
                            
                            with col3:
                                default_conf = "None"
                                if existing_picks:
                                    for conf_game_id, conf_val in existing_picks.get('confidence', []):
                                        if conf_game_id == game['id']:
                                            default_conf = str(conf_val)
                                
                                confidence = st.selectbox(
                                    f"Conf:",
                                    ["None", "1", "2", "3"],
                                    key=f"conf_{week_num}_{game['id']}",
                                    index=["None", "1", "2", "3"].index(default_conf)
                                )
                                if confidence != "None":
                                    confidence_picks.append((game['id'], int(confidence)))
                        else:
                            with col2:
                                st.write("*Locked*")
                    
                    st.write("---")
                    
                    # Show status
                    conf_values = [c[1] for c in confidence_picks]
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        st.metric("Confidence", f"{len(confidence_picks)}/3")
                    with col2:
                        if len(confidence_picks) == 3 and len(set(conf_values)) == 3:
                            st.success("✅ Ready!")
                        else:
                            st.info(f"Assign {3 - len(confidence_picks)} more")
                    
                    if st.button("🏀 Submit Picks", type="primary"):
                        conf_values = [c[1] for c in confidence_picks]
                        if len(confidence_picks) != 3:
                            st.error("❌ Assign exactly 3 confidence values")
                        elif len(set(conf_values)) != 3:
                            st.error("❌ Use 1, 2, and 3 once each")
                        else:
                            if 'picks' not in user_info:
                                user_info['picks'] = {}
                            
                            user_info['picks'][str(week_num)] = {
                                'picks': picks,
                                'confidence': confidence_picks,
                                'submitted': datetime.now().isoformat()
                            }
                            data['users'][st.session_state.username] = user_info
                            save_data(data)
                            st.success("✅ Picks submitted!")
                            st.balloons()
                            st.rerun()
        
        # Standings
        with tabs[1]:
            st.header("Standings")
            
            view_type = st.radio("View:", ["Season Total", "Weekly"], horizontal=True, key="participant_standings")
            
            if view_type == "Season Total":
                standings_df = get_season_standings(data, current_season)
                if not standings_df.empty:
                    display_df = standings_df[['Name', 'Wins', 'Losses']]
                    st.dataframe(display_df, use_container_width=True, hide_index=False)
            else:
                week_num = st.selectbox("Week:", range(1, 17), key="participant_week_standings")
                
                if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)].get('winners_set'):
                    week_standings = []
                    
                    for username, u_info in data['users'].items():
                        if not u_info.get('approved') or not u_info.get('active'):
                            continue
                        if str(week_num) in u_info.get('picks', {}):
                            wins, conf = calculate_week_results(season_data, week_num, username, u_info)
                            week_standings.append({
                                'Name': u_info['display_name'],
                                'Wins': wins,
                                'Losses': 20 - wins,
                                'Confidence': conf
                            })
                    
                    if week_standings:
                        week_df = pd.DataFrame(week_standings)
                        week_df = week_df.sort_values(['Wins', 'Confidence'], ascending=[False, False]).reset_index(drop=True)
                        week_df.index = week_df.index + 1
                        st.dataframe(week_df, use_container_width=True, hide_index=False)
        
        # My Results
        with tabs[2]:
            st.header("My Results")
            
            results_data = []
            for week in range(1, 17):
                if str(week) in season_data.get('weeks', {}) and season_data['weeks'][str(week)].get('winners_set'):
                    if str(week) in user_info.get('picks', {}):
                        wins, conf = calculate_week_results(season_data, week, st.session_state.username, user_info)
                        results_data.append({
                            'Week': week,
                            'Wins': wins,
                            'Losses': 20 - wins,
                            'Confidence': conf
                        })
            
            if results_data:
                results_df = pd.DataFrame(results_data)
                st.dataframe(results_df, use_container_width=True, hide_index=True)
                
                st.write("---")
                st.write("### Season Summary")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Wins", results_df['Wins'].sum())
                with col2:
                    st.metric("Total Losses", results_df['Losses'].sum())
                with col3:
                    st.metric("Total Confidence", results_df['Confidence'].sum())
            else:
                st.info("No completed weeks yet.")
        
        # View Picks
        with tabs[3]:
            st.header("View Other Picks")
            week_num = st.selectbox("Week:", range(1, 17), key="view_other_picks_week")
            
            # Check if all picks submitted
            if all_picks_submitted(season_data, week_num, data):
                if str(week_num) in season_data.get('weeks', {}) and season_data['weeks'][str(week_num)]['games']:
                    week_data = season_data['weeks'][str(week_num)]
                    
                    for username, u_info in data['users'].items():
                        if not u_info.get('approved') or not u_info.get('active'):
                            continue
                        if str(week_num) in u_info.get('picks', {}):
                            picks_data = u_info['picks'][str(week_num)]
                            
                            with st.expander(f"**{u_info['display_name']}**"):
                                picks = picks_data.get('picks', {})
                                confidence = {str(c[0]): c[1] for c in picks_data.get('confidence', [])}
                                
                                for game in week_data['games']:
                                    game_id = str(game['id'])
                                    if game_id in picks:
                                        pick = picks[game_id]
                                        conf_value = confidence.get(game_id, '')
                                        conf_str = f" ⭐ {conf_value}" if conf_value else ""
                                        
                                        col1, col2 = st.columns([3, 1])
                                        with col1:
                                            st.write(f"{game['away']} @ {game['home']}")
                                        with col2:
                                            st.write(f"**{pick}**{conf_str}")
            else:
                st.info("Other picks will be visible once all participants have submitted for this week.")
        
        # Rules
        with tabs[4]:
            st.header("Rules & Information")
            
            st.markdown("""
            ### How to Play
            
            **Weekly Picks**
            - Pick winners for all 20 games each week
            - Assign confidence points (3, 2, 1) to three picks
            - Must use each value exactly once
            
            **Deadlines**
            - Picks lock at 4:30 PM Pacific / 7:30 PM Eastern on game day
            - Once submitted, picks are locked (contact admin for changes)
            
            **Scoring**
            - 1 point per correct pick
            - Confidence points awarded for correct confidence picks
            - Tiebreaker: Total wins, then confidence points
            
            **Season**
            - 16 weeks per season
            - Season standings based on total wins
            
            **Viewing Picks**
            - See others' picks after everyone submits for that week
            """)
