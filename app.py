import streamlit as st
import pandas as pd
import requests
import re
import base64
from datetime import datetime
import time
import gspread
from google.oauth2 import service_account
from google.oauth2.service_account import Credentials

# Oldal beállítások
st.set_page_config(
    page_title="Warcraft Logs Részvételi Nyilvántartó",
    page_icon=":dragon:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Konfiguráció
st.session_state.setdefault('players', [])
st.session_state.setdefault('attendance_records', [])
st.session_state.setdefault('google_sheets_connected', False)

# Titkos kulcsok kezelése
def get_secrets():
    """Beolvassa a titkos kulcsokat a Streamlit secrets-ből"""
    try:
        return {
            "WCL_API_KEY": st.secrets["WCL_API_KEY"],
            "GOOGLE_CREDS": st.secrets["google_credentials"]
        }
    except:
        st.warning("Nem találhatóak titkos kulcsok. Kérlek állítsd be a Streamlit Secrets-t!")
        return {}

SECRETS = get_secrets()

# Helper függvények
def extract_report_id(url):
    """Kinyeri a report ID-t a Warcraft Logs URL-ből"""
    match = re.search(r'reports\/([a-zA-Z0-9]+)', url)
    return match.group(1) if match else None

def get_participants_from_log(report_id):
    """Lekéri a résztvevőket a Warcraft Logs API-ról"""
    if not SECRETS.get("WCL_API_KEY"):
        st.error("Warcraft Logs API kulcs nincs beállítva!")
        return []
    
    query = f"""
    {{
        reportData {{
            report(code: "{report_id}") {{
                masterData(translate: true) {{
                    actors(type: "player") {{
                        name
                        subType
                    }}
                }}
                startTime
                title
                zone {{
                    name
                }}
            }}
        }}
    }}
    """
    
    try:
        with st.spinner("Adatok lekérése a Warcraft Logs-ról..."):
            response = requests.post(
                'https://www.warcraftlogs.com/api/v2/client',
                json={'query': query},
                headers={'Authorization': f'Bearer {SECRETS["WCL_API_KEY"]}'},
                timeout=10
            )
            data = response.json()
        
        if 'errors' in data:
            st.error(f"Hiba a lekérdezés során: {data['errors'][0]['message']}")
            return [], None, None
        
        report = data['data']['reportData']['report']
        actors = report['masterData']['actors']
        players = [actor['name'] for actor in actors if actor['subType'] == 'Human']
        
        # Report adatok
        start_time = datetime.utcfromtimestamp(report['startTime']/1000).strftime('%Y-%m-%d %H:%M')
        title = report['title']
        zone = report['zone']['name'] if report['zone'] else "Ismeretlen"
        
        return players, title, f"{zone} - {start_time}"
    
    except Exception as e:
        st.error(f"Hiba történt: {str(e)}")
        return [], None, None

def check_attendance(participants):
    """Ellenőrzi a részvételt a játékosok listája alapján"""
    attendance = []
    
    for player in st.session_state.players:
        player_name = player['name']
        characters = player['characters']
        attended_chars = []
        
        for char in characters:
            # Nagybetű/kisbetű érzékenység elkerülése
            if any(char.lower() == p.lower() for p in participants):
                attended_chars.append(char)
        
        attendance.append({
            'player': player_name,
            'characters': characters,
            'attended': len(attended_chars) > 0,
            'attended_chars': attended_chars,
            'count': len(attended_chars)
        })
    
    return attendance

def to_csv_download_link(df, filename):
    """Generál egy CSV letöltési linket"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">📥 {filename} letöltése</a>'
    return href

def connect_google_sheets():
    """Kapcsolódás a Google Sheets-hez"""
    if not SECRETS.get("GOOGLE_CREDS"):
        st.error("Google Sheets hitelesítés nincs beállítva!")
        return None
    
    try:
        creds_info = SECRETS["GOOGLE_CREDS"]
        creds = Credentials.from_service_account_info(creds_info)
        client = gspread.authorize(creds)
        st.session_state.google_sheets_connected = True
        return client
    except Exception as e:
        st.error(f"Hiba a Google Sheets kapcsolódás során: {str(e)}")
        return None

# UI Komponensek
def player_management_section():
    """Játékoskezelő szekció"""
    st.sidebar.header("⚔️ Játékosok kezelése")
    
    # Új játékos hozzáadása
    with st.sidebar.expander("➕ Új játékos hozzáadása", expanded=True):
        with st.form("player_form", clear_on_submit=True):
            player_name = st.text_input("Játékos neve")
            characters = st.text_input("Karakterek (vesszővel elválasztva)", 
                                      help="Pl.: Arthas, Illidan, Jaina")
            submitted = st.form_submit_button("Mentés")
            
            if submitted:
                if player_name and characters:
                    char_list = [c.strip() for c in characters.split(",") if c.strip()]
                    st.session_state.players.append({
                        "name": player_name,
                        "characters": char_list
                    })
                    st.sidebar.success(f"{player_name} hozzáadva!")
                else:
                    st.sidebar.error("Add meg a játékos nevét és legalább egy karakterét!")
    
    # Játékosok listája
    st.sidebar.subheader("Játékosok listája")
    
    if not st.session_state.players:
        st.sidebar.info("Nincsenek játékosok a listában. Adj hozzá új játékosokat!")
    else:
        for i, player in enumerate(st.session_state.players):
            cols = st.sidebar.columns([4, 1])
            with cols[0]:
                st.markdown(f"**{player['name']}**")
                st.caption(", ".join(player['characters']))
            with cols[1]:
                if st.button("🗑️", key=f"delete_{i}"):
                    st.session_state.players.pop(i)
                    st.experimental_rerun()
    
    # Google Sheets integráció
    st.sidebar.subheader("Google Sheets Integráció")
    
    if st.sidebar.button("🔗 Kapcsolódás Google Sheets-hez"):
        connect_google_sheets()
    
    if st.session_state.get('google_sheets_connected'):
        st.sidebar.success("Sikeresen kapcsolódva Google Sheets-hez!")
        
        sheet_url = st.sidebar.text_input("Google Sheet URL", 
                                         placeholder="https://docs.google.com/spreadsheets/d/...")
        sheet_name = st.sidebar.text_input("Munkalap neve", "Roster")
        
        if st.sidebar.button("📥 Roster importálása Google Sheets-ből"):
            import_roster_from_google(sheet_url, sheet_name)
    
    # Import/Export
    st.sidebar.subheader("Adatkezelés")
    
    # Export jelenlegi roster CSV-be
    if st.session_state.players:
        df_roster = pd.DataFrame(st.session_state.players)
        st.sidebar.markdown(to_csv_download_link(df_roster, 'wcl_roster.csv'), 
                           unsafe_allow_html=True)
    
    # Import CSV-ből
    uploaded_file = st.sidebar.file_uploader("Roster importálása CSV-ből", type="csv")
    if uploaded_file is not None:
        try:
            df_import = pd.read_csv(uploaded_file)
            # Konvertálás: minden karakterlista stringként van, listává kell alakítani
            if 'characters' in df_import.columns:
                df_import['characters'] = df_import['characters'].apply(
                    lambda x: [c.strip() for c in str(x).split(",") if c.strip()]
                )
                st.session_state.players = df_import.to_dict('records')
                st.sidebar.success(f"{len(df_import)} játékos importálva!")
                st.experimental_rerun()
        except Exception as e:
            st.sidebar.error(f"Hiba történt az importálás során: {str(e)}")

def import_roster_from_google(sheet_url, sheet_name):
    """Roster importálása Google Sheets-ből"""
    if not st.session_state.get('google_sheets_connected'):
        st.error("Először kapcsolódj a Google Sheets-hez!")
        return
    
    try:
        client = gspread.authorize(Credentials.from_service_account_info(SECRETS["GOOGLE_CREDS"]))
        
        # Sheet megnyitása
        spreadsheet = client.open_by_url(sheet_url)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        # Adatok lekérése
        data = worksheet.get_all_records()
        
        if not data:
            st.warning("Nincsenek adatok a munkalapon!")
            return
        
        # Adatok feldolgozása
        players = []
        for row in data:
            if 'Player' in row and 'Characters' in row:
                characters = [c.strip() for c in str(row['Characters']).split(",") if c.strip()]
                players.append({
                    'name': row['Player'],
                    'characters': characters
                })
        
        st.session_state.players = players
        st.success(f"{len(players)} játékos importálva Google Sheets-ből!")
        st.experimental_rerun()
        
    except Exception as e:
        st.error(f"Hiba történt az importálás során: {str(e)}")

def log_analysis_section():
    """Log elemző szekció"""
    st.header("📜 Log elemzés")
    
    # Adatforrás választás
    source = st.radio("Adatforrás", 
                      ["Warcraft Logs Report", "Kézi karakterlista"],
                      horizontal=True)
    
    participants = []
    report_info = ""
    
    if source == "Warcraft Logs Report":
        report_link = st.text_input("Warcraft Logs Report Link", 
                                   placeholder="https://www.warcraftlogs.com/reports/...")
        
        if report_link:
            report_id = extract_report_id(report_link)
            if report_id:
                st.info(f"Report ID: `{report_id}`")
                
                if st.button("Résztvevők lekérése", disabled=not SECRETS.get("WCL_API_KEY")):
                    participants, title, info = get_participants_from_log(report_id)
                    
                    if participants:
                        st.success(f"{len(participants)} résztvevő található a logban!")
                        report_info = f"{title} - {info}" if title else info
            else:
                st.error("Érvénytelen link! A linknek tartalmaznia kell a report kódot.")
    else:
        char_input = st.text_area("Karakterek (vesszővel elválasztva)", 
                                 placeholder="Arthas, Illidan, Jaina, Sylvanas...",
                                 height=100)
        if char_input:
            participants = [c.strip() for c in char_input.split(",") if c.strip()]
    
    # Ha vannak résztvevők, akkor részvétel számítása
    if participants:
        st.subheader("📊 Részvételi eredmények")
        
        if report_info:
            st.info(report_info)
        
        # Részvétel számítása
        attendance = check_attendance(participants)
        
        # Eredmények megjelenítése
        results = []
        for a in attendance:
            attended_chars = ", ".join(a['attended_chars']) if a['attended_chars'] else "-"
            results.append({
                "Játékos": a['player'],
                "Karakterek": ", ".join(a['characters']),
                "Részt vett": "Igen" if a['attended'] else "Nem",
                "Részt vevő karakterek": attended_chars,
                "Karakterek száma": len(a['attended_chars'])
            })
        
        df_results = pd.DataFrame(results)
        
        # Színezés
        def color_attended(row):
            colors = [''] * len(row)
            if row['Részt vett'] == 'Igen':
                colors[2] = 'background-color: #2e7d32; color: white;'
            else:
                colors[2] = 'background-color: #c62828; color: white;'
            return colors
        
        styled_df = df_results.style.apply(color_attended, axis=1)
        st.dataframe(styled_df, use_container_width=True, height=600)
        
        # Részvételi adatok mentése
        st.session_state.attendance_records.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": report_info if report_info else "Kézi bevite",
            "results": results
        })
        
        # Export gomb
        st.markdown(to_csv_download_link(df_results, 'wcl_attendance.csv'), 
                   unsafe_allow_html=True)

def history_section():
    """Előzmények szekció"""
    if st.session_state.attendance_records:
        st.header("🕒 Előzmények")
        
        for record in reversed(st.session_state.attendance_records):
            with st.expander(f"{record['timestamp']} - {record['source']}"):
                df_record = pd.DataFrame(record['results'])
                st.dataframe(df_record, use_container_width=True)
                
                # Törlés gomb
                if st.button("Törlés", key=f"delete_record_{record['timestamp']}"):
                    st.session_state.attendance_records.remove(record)
                    st.experimental_rerun()

def user_guide_section():
    """Használati útmutató szekció"""
    with st.expander("ℹ️ Használati útmutató és beállítások"):
        st.markdown("""
        ### 🚀 Bevezetés
        Ez az alkalmazás segít nyomon követni a raidjeidet a Warcraft Logs reportok alapján,
        és automatikusan generál részvételi listát a játékosaidról.
        
        ### 🔑 API Kulcs beállítása
        A Warcraft Logs API használatához szükséges egy ingyenes API kulcs:
        1. Regisztrálj a [Warcraft Logs API oldalon](https://www.warcraftlogs.com/api/clients)
        2. Hozz létre egy új klienst
        3. Másold ki a generált API kulcsot
        
        ### ⚙️ Streamlit Secrets beállítása
        Az alkalmazás működéséhez be kell állítani a titkos kulcsokat:
        1. A Streamlit Cloud-on nyisd meg az alkalmazás beállításait
        2. Lépj a "Secrets" fülre
        3. Illeszd be a következő formátumban:
        ```
        [secrets]
        WCL_API_KEY = "az_api_kulcsod"
        
        [google_credentials]
        type = "service_account"
        project_id = "projekt_id"
        private_key_id = "private_key_id"
        private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
        client_email = "email@projekt.iam.gserviceaccount.com"
        client_id = "1234567890"
        auth_uri = "https://accounts.google.com/o/oauth2/auth"
        token_uri = "https://oauth2.googleapis.com/token"
        auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
        client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/email%40projekt.iam.gserviceaccount.com"
        ```
        """)
        
        st.image("https://i.imgur.com/7QZ4D3e.png", caption="Warcraft Logs report példa", width=300)

# Fő alkalmazás
def main():
    # Fejléc
    st.title("Warcraft Logs Részvételi Nyilvántartó")
    st.markdown("Kövesd nyomon a raidjeidet és a játékosok részvételét")
    
    # Szekciók
    player_management_section()
    log_analysis_section()
    history_section()
    user_guide_section()

if __name__ == "__main__":
    main()