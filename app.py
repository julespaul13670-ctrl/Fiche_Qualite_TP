import streamlit as st
import pandas as pd
import os
from datetime import datetime
import base64
import smtplib
from datetime import datetime
from fpdf import FPDF
# Pour les emails
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
# Pour consulter les archives Gmail
import imaplib
import email
from email.header import decode_header
import time
import gspread
from google.oauth2.service_account import Credentials
st.set_page_config(page_title="Qualité Exécution VRD", layout="wide")
@st.cache_data
def charger_donnees():
    # Lit le fichier Excel déposé sur ton GitHub
    df = pd.read_excel("Configuration_QuestionTP.xlsx")
    return df
if "df_config" not in st.session_state:
    try:
        # On remplit le tiroir avec le fichier Excel
        st.session_state.df_config = charger_donnees()
    except Exception as e:
        st.error(f"Impossible de charger l'Excel : {e}")
        st.session_state.df_config = pd.DataFrame()
    
def envoyer_par_email(pdf_bytes, nom_fichier, chantier, ouvrage):
    try:
        # 1. CONFIGURATION (Utilise tes identifiants Gmail)
        expediteur = "fichequalitetp@gmail.com"
        # Ton code d'application Google (les 16 lettres)
        mot_de_passe = "feculdalnfoyotdb" 
        destinataire = "fichequalitetp@gmail.com" # Tu t'envoies le mail à toi-même

        # 2. CRÉATION DU MAIL
        msg = MIMEMultipart()
        msg['From'] = expediteur
        msg['To'] = destinataire
        
        # Objet précis pour que les Archives puissent le lire plus tard
        date_str = datetime.now().strftime("%d/%m/%Y")
        # Format : RAPPORT ID - CHANTIER - OUVRAGE - DATE
        msg['Subject'] = f"RAPPORT {nom_fichier.split('_')[1]} - {chantier} - {ouvrage} - {date_str}"

        corps = f"Veuillez trouver ci-joint le rapport qualité pour le chantier {chantier}.\nOuvrage : {ouvrage}\nDate : {date_str}"
        msg.attach(MIMEText(corps, 'plain'))

        # 3. PIÈCE JOINTE (Le PDF)
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {nom_fichier}")
        msg.attach(part)

        # 4. ENVOI VIA LE SERVEUR GMAIL
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(expediteur, mot_de_passe)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erreur d'envoi mail : {e}")
        return False
    

def valider_numero_gsheet(chantier, pref, num):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("Suivi_Qualite_BTP")
        sheet = spreadsheet.worksheet("suivi_codes")
        
        # --- LECTURE BRUTE (Plus fiable que get_all_records) ---
        data = sheet.get_all_values()
        if not data:
            df_suivi = pd.DataFrame(columns=['chantier', 'pref', 'num'])
        else:
            df_suivi = pd.DataFrame(data[1:], columns=data[0])

        # Nettoyage : Tout en minuscules pour la comparaison
        df_suivi.columns = [str(c).strip().lower() for c in df_suivi.columns]

        # Comparaison (On met tout en minuscules et texte)
        filtre = (df_suivi['chantier'].astype(str).str.strip().str.lower() == str(chantier).strip().lower()) & \
                 (df_suivi['pref'].astype(str).str.strip().str.lower() == str(pref).strip().lower())
        
        if filtre.any():
            index_ligne = df_suivi.index[filtre][0] + 2
            sheet.update_cell(index_ligne, 3, int(num))
        else:
            sheet.append_row([str(chantier), str(pref), int(num)])
            
    except Exception as e:
        st.error(f"Erreur écriture GSheet : {e}")
        
def recuperer_dernier_numero_gsheet(chantier, pref):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("Suivi_Qualite_BTP")
        sheet = spreadsheet.worksheet("suivi_codes")
        
        data = sheet.get_all_values()
        if len(data) <= 1:
            return 0
            
        df_suivi = pd.DataFrame(data[1:], columns=data[0])
        df_suivi.columns = [str(c).strip().lower() for c in df_suivi.columns]
        
        filtre = (df_suivi['chantier'].astype(str).str.strip().str.lower() == str(chantier).strip().lower()) & \
                 (df_suivi['pref'].astype(str).str.strip().str.lower() == str(pref).strip().lower())
        
        if filtre.any():
            # On transforme la colonne num en nombres réels pour trouver le max
            nums = pd.to_numeric(df_suivi.loc[filtre, 'num'], errors='coerce').fillna(0)
            return int(nums.max())
        return 0
    except Exception as e:
        return 0
        

        
class FicheQualite(FPDF):
    def header(self):
        # 1. LOGO GAUCHE (ex: Logo Entreprise)
        if os.path.exists("logo_gauche.png"):
            self.image("logo_gauche.png", 10, 8, 27) # x=10, y=8, largeur=33
            
        # 2. LOGO DROITE (ex: Logo Client ou Certification)
        if os.path.exists("logo_droit.png"):
            # On le place à 10mm du bord droit (210mm largeur A4 - 10mm marge - 33mm image = 167)
            self.image("logo_droit.png", 160, 12, 37) 
            
        # 3. TITRE CENTRAL
        self.set_font('Arial', 'B', 15)
        # On décale pour ne pas écrire sur le logo de gauche
        self.cell(80) 
        self.cell(30, 10, 'FICHE DE CONTROLE QUALITE', 0, 0, 'C')
        
        # Saut de ligne pour le contenu
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')


# --- 2. CSS "FORCE BRUTE" POUR CARTES GÉANTES ---
st.markdown("""
    <style>
    /* 1. FORCE LA COULEUR DES EMOJIS (Correction Mobile) */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap');

    div.stButton > button[key^="home_"] {
        font-family: "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif !important;
        width: 100% !important; 
        min-height: 550px !important; 
        background-color: white !important;
        border: 4px solid #e0e0e0 !important;
        border-radius: 35px !important;
        box-shadow: 0 20px 40px rgba(0,0,0,0.1) !important;
        transition: all 0.4s ease-in-out !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
    }

    /* 2. CIBLE L'EMOJI ET LE TEXTE */
    div.stButton > button[key^="home_"] p, 
    div.stButton > button[key^="home_"] span {
        font-family: "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif !important;
        text-rendering: optimizeLegibility !important;
        -webkit-font-smoothing: antialiased !important;
    }

    div.stButton > button[key^="home_"] p {
        font-size: 80px !important;    /* Taille de l'émoji boostée */
        line-height: 1.2 !important;
        text-align: center !important;
        margin-bottom: 20px !important;
    }

    div.stButton > button[key^="home_"] span {
        font-size: 35px !important;    /* Taille du texte */
        font-weight: bold !important;
        color: #31333F !important;     /* Force le texte en gris foncé/noir */
    }

    /* 3. EFFET AU SURVOL */
    div.stButton > button[key^="home_"]:hover {
        border-color: #3498db !important;
        transform: translateY(-15px) !important;
        box-shadow: 0 30px 60px rgba(52, 152, 219, 0.2) !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialisation de l'état de la page
if "page" not in st.session_state:
    st.session_state.page = "Accueil"

# --- 3. BARRE LATÉRALE ---
with st.sidebar:
    st.title("🏗️ Menu Navigation")
    st.write("---") # Une ligne pour faire propre

    # Bouton Accueil
    if st.sidebar.button("🏠 Accueil", use_container_width=True):
        st.session_state.page = "Accueil"
        st.rerun()

    st.write("") # Espace

    # Bouton Ajouter
    if st.sidebar.button("📝 Ajouter un document", use_container_width=True):
        st.session_state.page = "Ajouter"
        st.rerun()

    st.write("") # Espace

    # Bouton Archives
    if st.sidebar.button("📂 Consulter les Archives", use_container_width=True):
        st.session_state.page = "archives"
        st.rerun()

    st.write("") # Espace

    if st.sidebar.button("📦 Gestion du Stock", use_container_width=True):
        st.session_state.page = "stock"
        st.rerun()

    st.write("") # Espace
    st.write("---")

    # Bouton Paramètres
    if st.sidebar.button("⚙️ Paramètres", use_container_width=True):
        st.session_state.page = "parametres"
        st.rerun()

# --- 4. LOGIQUE DES PAGES ---

if st.session_state.page == "Accueil":
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🏗️ Gestionnaire Qualité BTP</h1>", unsafe_allow_html=True)
    st.write("---")

    _, col1, col2, _ = st.columns([0.5, 2, 2, 0.5])

    with col1:
        if st.button("➕\n\nAJOUTER UN\nDOCUMENT", key="home_add"):
            st.session_state.page = "Ajouter"
            st.rerun()

    with col2:
        if st.button("📁\n\nCONSULTER LES\nARCHIVES", key="home_arch"):
            st.session_state.page = "Archives"
            st.rerun()

# 2. On enchaîne obligatoirement avec ELIF
elif st.session_state.page == "Ajouter":
    st.title("📝 Nouveau Rapport de Contrôle")

    file_ch = "data_chantiers.csv"
    file_ctrl = "data_controleurs.csv"
    

    if os.path.exists(file_ch) and os.path.exists(file_ctrl):
        df_ch = pd.read_csv(file_ch)
        dict_chantiers = pd.Series(df_ch.Responsable.values, index=df_ch.Nom).to_dict()
        liste_personnel = pd.read_csv(file_ctrl)["Nom"].tolist()
        

        chantier = st.selectbox("📍 Choisir le chantier", ["Sélectionner..."] + list(dict_chantiers.keys()))
        if chantier != "Sélectionner...":
            st.info(f"Responsable : **{dict_chantiers.get(chantier, '')}**")
            c1, c2 = st.columns(2)
            with c1:
                choix_nom = st.selectbox("👤 Contrôleur", ["Sélectionner..."] + liste_personnel + ["Autre..."])
                nom_final = st.text_input("1er lettre Prenom + NOM") if choix_nom == "Autre..." else (choix_nom if choix_nom != "Sélectionner..." else "")
            with c2:
                date_auto = st.date_input("📅 Date", datetime.now())

            st.divider()
            # --- 1. SÉLECTION CASCADE ---
        df = st.session_state.df_config
        
        # On définit une liste vide par défaut pour éviter l'erreur NameError
        liste_ouvrages = [] 
        
        if df is not None and not df.empty:
            liste_ouvrages = [ov for ov in df['Ouvrage'].unique() if ov != "_GENERAL" and ov != ""]
        
        # Maintenant 'liste_ouvrages' existe toujours, même si elle est vide []
        
        # 1. Sélection de l'Ouvrage (Regards, Bordures...)
        # Modifie la création de la liste
            # --- 1. SÉLECTION DE L'OUVRAGE ---
        # --- 1. SÉLECTION DE L'OUVRAGE ---
        liste_ouvrages = [ov for ov in df['Ouvrage'].unique() if ov != "_GENERAL" and ov != ""]
        liste_ouvrages.append("Autre")

        ouvrage_sel = st.selectbox("🏗️ Ouvrage à contrôler", ["Sélectionner..."] + liste_ouvrages, key="sel_ouv_main")

        if ouvrage_sel != "Sélectionner...":
            # --- 2. GESTION DU CAS 'AUTRE' VS NORMAL ---
            if ouvrage_sel == "Autre":
                nom_ouvrage_libre = st.text_input("📝 Nom de l'ouvrage non prévu", placeholder="Ex: Muret, Escalier...")
                ouvrage_final_nom = nom_ouvrage_libre if nom_ouvrage_libre else "Autre ouvrage"
                # On crée un DataFrame vide avec les colonnes du Sheets pour éviter les erreurs NameError
                df_ouv = pd.DataFrame(columns=df.columns)
                st.info("💡 Pour cet ouvrage, vous pouvez remplir les contrôles généraux et l'observation ci-dessous.")
            else:
                df_ouv = df[df['Ouvrage'] == ouvrage_sel]
                ouvrage_final_nom = ouvrage_sel

            # --- 3. SOUS-CATÉGORIES ---
            df_scat = df_ouv[df_ouv['Niveau'].isin(['S-Cat', 'Type'])]
            sc_sel = "Standard" # Valeur par défaut si vide
            
            if not df_scat.empty:
                sc_list = df_scat['Sous-Catégorie / Type'].unique().tolist()
                sc_sel = st.selectbox("🔍 Sous-catégorie / Modèle", ["Sélectionner..."] + sc_list, key="sel_scat")

                if sc_sel != "Sélectionner...":
                    df_filtre_sc = df_scat[df_scat['Sous-Catégorie / Type'] == sc_sel]
                    deja_affiche = []

                    for i, row in df_filtre_sc.iterrows():
                        question_texte = row['Question ou Option']
                        if pd.isna(question_texte) or str(question_texte).strip() == "":
                            continue

                        if row['Niveau'] == 'Type':
                            if sc_sel not in deja_affiche:
                                st.radio(f"Configuration {sc_sel}", ["Ligne droite", "Courbe"], key=f"rad_{sc_sel}_{i}")
                                deja_affiche.append(sc_sel)
                        else:
                            st.checkbox(str(question_texte), key=f"chk_{question_texte}")

            # --- 4. QUESTIONS FIXES DE L'OUVRAGE ---
            df_fixes = df_ouv[df_ouv['Niveau'] == 'Ouvrage']
            if not df_fixes.empty:
                st.subheader(f"✅ Points de contrôle {ouvrage_final_nom}")
                for i, row in df_fixes.iterrows():
                    st.checkbox(row['Question ou Option'], key=f"chk_{row['Question ou Option']}")

            # --- 5. QUESTIONS GÉNÉRALES ---
            st.subheader("🌍 Contrôles Généraux")
            df_gen_data = df[df['Ouvrage'] == '_GENERAL']
            for i, row in df_gen_data.iterrows():
                q_txt = str(row['Question ou Option']).strip()
                st.checkbox(q_txt, key=f"chk_gen_{q_txt}")

            # --- 6. OBSERVATIONS ET PHOTO ---
            st.divider()
            commentaire = st.text_area("📝 Observations particulières", key="comm_zone")
            # --- 6. Capture ou Import Photo ---
            st.subheader("📸 Justificatif Photo")
            
            # file_uploader permet de choisir entre l'appareil photo et la galerie sur mobile
            photo = st.file_uploader(
                "Prendre une photo ou choisir une image", 
                type=['png', 'jpg', 'jpeg'],
                key=f"upload_{ouvrage_sel}"
            )
            if photo:
                st.image(photo, caption="Aperçu de la photo sélectionnée", width=300)
                # Stockage en session
                st.session_state['temp_photo_bytes'] = photo.getvalue()

            # --- 7. BOUTON DE GÉNÉRATION (CONTENU INCHANGÉ) ---
            if st.button("🚀 1. Générer l'Aperçu", key=f"btn_generer_{ouvrage_sel}"):
                if not nom_final:
                    st.error("Indiquez le contrôleur.")
                else:
                    try:
                        # 1. RÉCUPÉRATION DES RÉPONSES
                        controles = {}
                        # Questions Ouvrage
                        for _, row in df_ouv.iterrows():
                            q_txt = row['Question ou Option']
                            key_chk = f"chk_{q_txt}"
                            if key_chk in st.session_state:
                                controles[q_txt] = (st.session_state[key_chk], row['Catégorie Question'])

                        # Questions Générales
                        for _, row in df_gen_data.iterrows():
                            q_txt = str(row['Question ou Option']).strip()
                            key_gen = f"chk_gen_{q_txt}"
                            if key_gen in st.session_state:
                                cat_name = row['Catégorie Question'] if pd.notna(row['Catégorie Question']) else "Général"
                                controles[q_txt] = (st.session_state[key_gen], cat_name)

                        # 2. LOGIQUE ID INTELLIGENT
                        if ouvrage_sel == "Autre":
                            pref_final = "AU"
                        else:
                            char_ov = ouvrage_sel[0].upper()
                            char_sc = sc_sel[0].upper() if sc_sel != "Standard" else "G"
                            pref_final = f"{char_ov}{char_sc}"

                        # --- LECTURE SÉCURISÉE DU FICHIER DE SUIVI ---
                        # 2. LOGIQUE ID INTELLIGENT
                        if ouvrage_sel == "Autre":
                            pref_final = "AU"
                        else:
                            char_ov = ouvrage_sel[0].upper()
                            char_sc = sc_sel[0].upper() if sc_sel != "Standard" else "G"
                            pref_final = f"{char_ov}{char_sc}"
                
                        # --- NOUVELLE LECTURE VIA GOOGLE SHEETS ---
                        dernier_num = recuperer_dernier_numero_gsheet(chantier, pref_final)
                        nouveau_num = dernier_num + 1
                
                        code_fiche = f"{pref_final}-{nouveau_num:03d}"
                        # 3. GÉNÉRATION PDF (TA MISE EN PAGE EXACTE)
                        pdf = FicheQualite()
                        pdf.add_page()
                        
                        # Titre ouvrage libre ou sélectionné
                        
                        pdf.set_fill_color(240, 240, 240); pdf.set_font("Arial", 'B', 12)
                        pdf.cell(0, 10, f"Rapport : {chantier}", 1, 1, 'L', fill=True); pdf.ln(5)
                        
                        pdf.set_font("Arial", 'B', 10); pdf.cell(25, 8, "Responsable : ", 0, 0)
                        pdf.set_font("Arial", '', 10); pdf.cell(85, 8, f"{dict_chantiers[chantier]}", 0, 0)
                        pdf.set_font("Arial", 'B', 10); pdf.cell(40, 8, "ID : ", 0, 0, 'R')
                        pdf.set_font("Arial", '', 10); pdf.cell(20, 8, f"{code_fiche}", 0, 1, 'L')

                        pdf.set_font("Arial", 'B', 10); pdf.cell(25, 8, "Controleur: ", 0, 0)
                        pdf.set_font("Arial", '', 10); pdf.cell(85, 8, f"{nom_final}", 0, 0)
                        pdf.set_font("Arial", 'B', 10); pdf.cell(40, 8, "Ouvrage : ", 0, 0, 'R')
                        sc_display = sc_sel if 'sc_sel' in locals() else "Général"
                        pdf.set_font("Arial", '', 10); pdf.cell(20, 8, f"{ouvrage_sel} ({sc_display})", 0, 1, 'L')
                        pdf.ln(8)

                        # Tableau des points de contrôle
                        pdf.set_fill_color(230, 230, 230); pdf.set_font("Arial", 'B', 10)
                        pdf.cell(40, 10, "Catégorie", 1, 0, 'C', fill=True)
                        pdf.cell(100, 10, "Point de contrôle", 1, 0, 'C', fill=True)
                        pdf.cell(50, 10, "Statut", 1, 1, 'C', fill=True)

                        pdf.set_font("Arial", '', 9)
                        for pt_txt, info in controles.items():
                            etat, cat_name = info
                            pdf.cell(40, 10, str(cat_name), 1, 0, 'L')
                            pdf.cell(100, 10, str(pt_txt), 1, 0, 'L')
                            status = "OK" if etat else "NON CONFORME"
                            if not etat: pdf.set_text_color(200, 0, 0)
                            pdf.cell(50, 10, status, 1, 1, 'C')
                            pdf.set_text_color(0, 0, 0)

                        # Observations
                        pdf.ln(10)
                        if commentaire.strip():
                            pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "OBSERVATIONS :", 0, 1, 'L')
                            pdf.set_font("Arial", '', 11); pdf.multi_cell(0, 8, commentaire, border=1, align='L')
                            pdf.ln(5)

                        # Photo
                        if photo:
                            pdf.add_page()
                            pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "Photo de l'ouvrage :", 0, 1, 'L')
                            with open("temp_photo.png","temp_photo.jpeg","temp_photo.jpg", "wb") as f:
                                f.write(photo.getbuffer())
                            pdf.image("temp_photo.png","temp_photo.jpeg","temp_photo.jpg", x=10, y=30, w=180)

                        # Finalisation et stockage session
                        pdf_data = pdf.output(dest='S')
                        st.session_state.pdf_bytes = bytes(pdf_data) if not isinstance(pdf_data, str) else pdf_data.encode('latin-1')
                        st.session_state.nom_fichier = f"Rapport_{code_fiche}_{chantier}.pdf"
                        st.session_state.temp_num = nouveau_num
                        st.session_state.temp_pref = pref_final
                        st.success(f"✅ Aperçu prêt ! ({code_fiche})")

                    except Exception as e:
                        st.error(f"Erreur technique : {e}")

            # --- 8. AFFICHAGE DE L'APERÇU ET ENVOI ---
            if st.session_state.get('pdf_bytes'):
                b64 = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8')
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="600"></iframe>', unsafe_allow_html=True)
                
                if st.button("💾 2. Sauvegarder & Envoyer"):
                    if envoyer_par_email(st.session_state.pdf_bytes, st.session_state.nom_fichier, chantier, ouvrage_sel):
                        valider_numero_gsheet(chantier, st.session_state.temp_pref, st.session_state.temp_num)
                        st.toast("✅ Rapport envoyé avec succès !")
                        time.sleep(3)
                        st.session_state.pdf_bytes = None
                        if 'temp_photo' in st.session_state:
                            del st.session_state['temp_photo']
                  
                # 4. RELANCE DE LA PAGE
                # Cela remet l'interface à zéro pour le prochain ouvrage
                        st.rerun()

# 3. Encore ELIF
elif st.session_state.page == "archives":
    st.header("📂 Archives des Rapports (Cloud)")
    
    # 1. BARRE D'OUTILS
    col_search, col_date = st.columns([2, 1])
    with col_search:
        search_query = st.text_input("🔍 Rechercher un fichier", placeholder="ID, chantier, ouvrage...")
    with col_date:
        date_sel = st.date_input("📅 Filtrer par date", value=None)

    st.write("---")

    # 2. BOUTON DE SYNCHRONISATION
    if st.button("🔄 Synchroniser les archives"):
        with st.spinner("Recherche des rapports..."):
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login("fichequalitetp@gmail.com", "feculdalnfoyotdb")
                mail.select("INBOX")
                status, messages = mail.search(None, '(SUBJECT "RAPPORT")')
                mail_ids = messages[0].split()
                data_list = []
                for i in range(len(mail_ids)-1, max(-1, len(mail_ids)-41), -1):
                    res, msg_data = mail.fetch(mail_ids[i], "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes): 
                                subject = subject.decode(encoding if encoding else "utf-8")
                            parts = subject.split(" - ")
                            if len(parts) >= 4:
                                data_list.append({
                                    "ID": parts[0].replace("RAPPORT ", ""),
                                    "Chantier": parts[1],
                                    "Ouvrage": parts[2],
                                    "Date": parts[3],
                                    "Mail_ID": mail_ids[i]
                                })
                mail.logout()
                st.session_state.archives_data = data_list
            except Exception as e:
                st.error(f"Erreur : {e}")

    # 3. AFFICHAGE DU TABLEAU
    if "archives_data" in st.session_state:
        df = pd.DataFrame(st.session_state.archives_data)
        
        # Filtres
        if search_query:
            df = df[df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)]
        if date_sel:
            d_str = date_sel.strftime('%d/%m/%Y')
            df = df[df['Date'] == d_str]

        # --- NOUVEAU : ZONE D'AFFICHAGE DU PDF (S'affiche en haut si un PDF est sélectionné) ---
        if "current_pdf" in st.session_state and st.session_state.current_pdf:
            st.write("---")
            c_titre, c_fermer = st.columns([5, 1])
            c_titre.subheader("📄 Consultation du rapport")
            if c_fermer.button("❌ Fermer l'aperçu"):
                st.session_state.current_pdf = None
                st.rerun()
            
            st.markdown(st.session_state.current_pdf, unsafe_allow_html=True)
            st.write("---")

        st.metric(label="Rapports trouvés", value=len(df))
        st.write("---")

        # --- EN-TÊTE FIXE DU TABLEAU ---
        h1, h2, h3, h4, h5 = st.columns([1, 2, 2, 2, 1])
        h1.write("**ID**")
        h2.write("**Chantier**")
        h3.write("**Ouvrage**")
        h4.write("**Date**")
        h5.write("**Action**")
        st.divider()

        if not df.empty:
            for index, row in df.iterrows():
                c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 1])
                c1.write(row['ID'])
                c2.write(row['Chantier'])
                c3.write(row['Ouvrage'])
                c4.write(row['Date'])
                
                if c5.button("Consulter", key=f"arch_{row['Mail_ID'].decode()}"):
                    with st.spinner("Récupération du PDF..."):
                        try:
                            m = imaplib.IMAP4_SSL("imap.gmail.com")
                            m.login("fichequalitetp@gmail.com", "feculdalnfoyotdb")
                            m.select("INBOX")
                            _, data = m.fetch(row['Mail_ID'], "(RFC822)")
                            msg = email.message_from_bytes(data[0][1])
                            for part in msg.walk():
                                if part.get_content_maintype() == 'multipart': continue
                                if part.get('Content-Disposition') is None: continue
                                filename = part.get_filename()
                                if filename and filename.lower().endswith(".pdf"):
                                    pdf_content = part.get_payload(decode=True)
                                    base64_pdf = base64.b64encode(pdf_content).decode('utf-8')
                                    # ON STOCKA DANS LE SESSION STATE AU LIEU D'AFFICHER DIRECTEMENT
                                    st.session_state.current_pdf = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
                            m.logout()
                            st.rerun() # On relance pour afficher le PDF en haut
                        except Exception as e:
                            st.error(f"Erreur : {e}")
        else:
            st.warning("Aucun rapport ne correspond à votre recherche.")
    else:
        st.info("Utilisez le bouton ci-dessus pour charger vos rapports.")


# --- PAGE GESTION DU STOCK ---
# --- PAGE GESTION DU STOCK (VERSION INTUITIVE) ---
elif st.session_state.page == "stock":
    st.title("📦 Gestion des Stocks")
    
    file_stock = "data_stock.csv"
    
    # 1. Chargement des données
    if os.path.exists(file_stock):
        df_stock = pd.read_csv(file_stock)
    else:
        df_stock = pd.DataFrame(columns=["Chantier", "Article", "Quantite", "Unite"])

    # 2. Sélection du chantier
    file_ch = "data_chantiers.csv"
    if os.path.exists(file_ch):
        liste_chantiers = pd.read_csv(file_ch)["Nom"].tolist()
        chantier_sel = st.selectbox("📍 Chantier", ["Sélectionner..."] + liste_chantiers)
        
        if chantier_sel != "Sélectionner...":
            st.divider()
            
            # --- AJOUTER UN NOUVEL ARTICLE ---
            with st.expander("➕ Ajouter un nouvel article au stock"):
                c1, c2, c3 = st.columns([3, 1, 1])
                nouvel_art = c1.text_input("Nom de l'article (ex: Bordure T2)")
                qte_init = c2.number_input("Qté", min_value=0, value=0)
                unite_init = c3.selectbox("Unité", ["u", "ml", "m2", "m3", "t"])
                
                if st.button("Valider l'ajout"):
                    nouvelle_ligne = pd.DataFrame([[chantier_sel, nouvel_art, qte_init, unite_init]], 
                                                columns=["Chantier", "Article", "Quantite", "Unite"])
                    df_stock = pd.concat([df_stock, nouvelle_ligne], ignore_index=True)
                    df_stock.to_csv(file_stock, index=False)
                    st.rerun()

            st.subheader(f"Inventaire de {chantier_sel}")

            # --- AFFICHAGE DES ARTICLES SOUS FORME DE CARTES ---
            stock_actuel = df_stock[df_stock["Chantier"] == chantier_sel]
            
            if stock_actuel.empty:
                st.info("Aucun article en stock pour ce chantier.")
            else:
                for idx, row in stock_actuel.iterrows():
                    # Création d'une "Tuile" pour chaque article
                    with st.container(border=True):
                        col_nom, col_moins, col_qte, col_plus = st.columns([3, 1, 2, 1])
                        
                        col_nom.write(f"**{row['Article']}**")
                        col_qte.markdown(f"<h3 style='text-align:center; margin:0;'>{row['Quantite']} <small>{row['Unite']}</small></h3>", unsafe_allow_html=True)
                        
                        # Bouton MOINS (Consommer)
                        if col_moins.button("➖", key=f"moins_{idx}"):
                            df_stock.at[idx, "Quantite"] = max(0, row["Quantite"] - 1)
                            df_stock.to_csv(file_stock, index=False)
                            st.rerun()
                            
                        # Bouton PLUS (Livraison)
                        if col_plus.button("➕", key=f"plus_{idx}"):
                            df_stock.at[idx, "Quantite"] = row["Quantite"] + 1
                            df_stock.to_csv(file_stock, index=False)
                            st.rerun()
                            
                        # Option pour retirer manuellement une grosse quantité
                        with st.expander("Consommation précise"):
                            val_conso = st.number_input("Quantité consommée", min_value=0, key=f"val_{idx}")
                            if st.button("Valider conso", key=f"btn_val_{idx}"):
                                df_stock.at[idx, "Quantite"] = max(0, row["Quantite"] - val_conso)
                                df_stock.to_csv(file_stock, index=False)
                                st.rerun()
            
            if st.button("🗑️ Supprimer l'article", key=f"del_{idx}", help="Supprime définitivement de la liste"):
                 df_stock = df_stock.drop(idx)
                 df_stock.to_csv(file_stock, index=False)
                 st.rerun()
    else:
        st.warning("Veuillez d'abord configurer vos chantiers dans les Paramètres.")



# 4. Encore ELIF pour les paramètres
# --- PAGE PARAMÈTRES (VERSION NETTOYÉE ET SÉCURISÉE) ---
elif st.session_state.page == "parametres":
    st.header("⚙️ Configuration Système")
    
    # 1. SYSTÈME DE VERROUILLAGE
    if not st.session_state.get("auth_admin", False):
        st.subheader("🔐 Accès Restreint")
        mdp_saisi = st.text_input("Entrez le mot de passe administrateur", type="password", key="login_admin_unique")
        
        if mdp_saisi:
            if mdp_saisi == "12345":  # TON SEUL ET UNIQUE MOT DE PASSE
                st.session_state.auth_admin = True
                st.success("✅ Accès accordé")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
        
        # On arrête TOUT ici si l'utilisateur n'est pas identifié
        st.stop() 

    # 2. CONTENU AFFICHÉ UNIQUEMENT SI AUTHENTIFIÉ
    # Bouton de déconnexion en haut pour plus de facilité
    if st.button("🔓 Déconnexion"):
        st.session_state.auth_admin = False
        st.rerun()
        
    st.write("---")
    
    # Création des onglets
    tab1, tab2, tab3, tab4 = st.tabs(["🏗️ Chantiers", "👤 Contrôleurs", "📐 Structure & Questions", "🔑 Sécurité"])

    with tab1:
        st.subheader("Liste des chantiers")
        df_ch = pd.read_csv("data_chantiers.csv") if os.path.exists("data_chantiers.csv") else pd.DataFrame(columns=["Nom", "Responsable"])
        e_ch = st.data_editor(df_ch, num_rows="dynamic", key="ed_ch", use_container_width=True)
        if st.button("Sauvegarder Chantiers"): 
            e_ch.to_csv("data_chantiers.csv", index=False)
            st.success("Chantiers sauvegardés !")

    with tab2:
        st.subheader("Gestion du personnel")
        df_ct = pd.read_csv("data_controleurs.csv") if os.path.exists("data_controleurs.csv") else pd.DataFrame(columns=["Nom"])
        e_ct = st.data_editor(df_ct, num_rows="dynamic", key="ed_ct", use_container_width=True)
        if st.button("Sauvegarder Personnel"): 
            e_ct.to_csv("data_controleurs.csv", index=False)
            st.success("Personnel sauvegardé !")

    with tab3:
        st.subheader("📐 Éditeur de Structure VRD")
        if "df_config" in st.session_state:
            df_edite = st.data_editor(st.session_state.df_config, num_rows="dynamic", use_container_width=True, key="ed_config_sheet")
            st.warning("⚠️ La sauvegarde directe sur Google Sheets nécessite une configuration spécifique de l'API.")

    with tab4:
        st.subheader("🔑 Sécurité du compte")
        nouveau_mdp = st.text_input("Nouveau mot de passe", type="password", key="new_pwd")
        confirmation = st.text_input("Confirmer le mot de passe", type="password", key="conf_pwd")
        
        if st.button("💾 Enregistrer le nouveau mot de passe"):
            if nouveau_mdp == confirmation and len(nouveau_mdp) >= 4:
                # Ici tu peux mettre à jour ton système de mot de passe
                st.success("✅ Mot de passe mis à jour (pense à modifier la valeur dans ton code Python également) !")
            else:

                st.error("Les mots de passe ne correspondent pas ou sont trop courts.")





