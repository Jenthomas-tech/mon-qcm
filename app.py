import io
import json
import random
import re
import time

import fitz  # pymupdf
import streamlit as st
from google import genai
from google.genai import types
from PIL import Image

import db

st.set_page_config(page_title="Mon QCM", page_icon="📚", layout="wide")
db.init_db()

MODELE = "gemini-3.8-flash"


# ---------- Extraction des documents ----------

def pages_depuis_pdf(fichier_bytes):
    """Retourne une liste d'images (bytes PNG) et de textes, une par page."""
    doc = fitz.open(stream=fichier_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=110)
        pages.append({"image": pix.tobytes("png"), "texte": page.get_text()})
    return pages


def pages_depuis_pptx(_bytes):
    """Pour un PPTX : texte par diapositive + images intégrées."""
    from pptx import Presentation
    prs = Presentation(io.BytesIO(_bytes))
    pages = []
    for slide in prs.slides:
        texte = []
        image = None
        for shape in slide.shapes:
            if shape.has_text_frame:
                texte.append(shape.text_frame.text)
            if shape.shape_type == 13 and image is None:  # image
                try:
                    image = shape.image.blob
                except Exception:
                    pass
        pages.append({"image": image, "texte": "\n".join(texte)})
    return pages


# ---------- Génération des QCM ----------

PROMPT = """Tu es un enseignant qui crée des QCM de révision pour un étudiant.
À partir du contenu fourni (texte et images de pages de cours), génère des
questions à choix multiples en français.

Règles :
- Couvre toutes les notions importantes. Environ une question par notion clé.
  Nombre cible : {cible} questions (ajuste selon la densité réelle du contenu).
- 4 options par question, une seule bonne réponse.
- Rédige toutes les questions, les propositions de réponses et les explications en espagnol, même si le document source est en français.
- N'invente rien : base-toi uniquement sur le contenu fourni.
- Si une question porte sur un schéma, un graphique ou une image, indique le
  numéro de la page concernée dans "page" (numéro relatif à ce lot, en
  commençant à 1). Sinon, mets null.
- Ajoute une courte explication de la bonne réponse.

Réponds UNIQUEMENT avec un tableau JSON valide, sans texte autour, au format :
[{{"enonce": "...", "options": ["A", "B", "C", "D"],
   "bonne_reponse": 0, "explication": "...", "page": 1}}]
"""

def lire_json_tolerant(texte):
    """Parse le JSON renvoyé par Gemini, en réparant les erreurs fréquentes."""
    texte = texte.strip()
    # Retire les éventuelles balises ```json ... ```
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte)
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        # Supprime les virgules en trop avant ] ou }
        texte = re.sub(r",\s*([\]}])", r"\1", texte)
        return json.loads(texte)

def generer_qcm(cle_api, pages, cible):
    client = genai.Client(api_key=cle_api)
    contenu = [PROMPT.format(cible=cible)]
    for i, p in enumerate(pages, start=1):
        contenu.append(f"--- Page {i} ---\n{p['texte']}")
        if p["image"]:
            try:
                img = Image.open(io.BytesIO(p["image"]))
                contenu.append(img)
            except Exception:
                pass
    reponse = client.models.generate_content(
        model=MODELE,
        contents=contenu,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"),
    )
    donnees = lire_json_tolerant(reponse.text)
    resultat = []
    for q in donnees:
        try:
            page_num = q.get("page")
            image = None
            if page_num and 1 <= page_num <= len(pages):
                image = pages[page_num - 1]["image"]
            resultat.append({
                "enonce": q["enonce"],
                "options": q["options"],
                "bonne_reponse": int(q["bonne_reponse"]),
                "explication": q.get("explication", ""),
                "image": image,
            })
        except (KeyError, ValueError, TypeError):
            continue
    return resultat

def generer_qcm_avec_retry(cle_api, pages, cible, essais=4):
    """Réessaie si Google est surchargé (503) ou limite le débit (429)."""
    for tentative in range(essais):
        try:
            return generer_qcm(cle_api, pages, cible)
        except Exception as e:
            message = str(e)
            temporaire = ("503" in message or "UNAVAILABLE" in message
                or "429" in message or "RESOURCE_EXHAUSTED" in message
                or isinstance(e, json.JSONDecodeError))
            if temporaire and tentative < essais - 1:
                attente = 5 * (2 ** tentative)  # 5 s, 10 s, 20 s
                st.toast(f"Google est surchargé, nouvel essai dans {attente} s...")
                time.sleep(attente)
            else:
                raise


# ---------- Interface ----------

st.title("📚 Mon QCM")

# Clé API (saisie par l'utilisateur, jamais stockée dans le code)
cle_api = st.sidebar.text_input("Clé API Gemini", type="password")
page = st.sidebar.radio("Menu", ["📁 Mes cours", "📝 Faire un quiz", "📊 Progression"])

# ----- Page : Mes cours -----
if page == "📁 Mes cours":
    st.header("Organisation des cours")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Matières")
        nouvelle = st.text_input("Nouvelle matière")
        if st.button("Ajouter la matière") and nouvelle:
            db.ajouter_matiere(nouvelle)
            st.rerun()

    matieres = db.lister_matieres()
    if not matieres:
        st.info("Commencez par ajouter une matière.")
        st.stop()

    noms = {m["nom"]: m["id"] for m in matieres}
    choix_m = st.selectbox("Matière", list(noms.keys()))
    matiere_id = noms[choix_m]

    with col2:
        st.subheader("Chapitres")
        nouveau = st.text_input("Nouveau chapitre")
        if st.button("Ajouter le chapitre") and nouveau:
            db.ajouter_chapitre(matiere_id, nouveau)
            st.rerun()

    chapitres = db.lister_chapitres(matiere_id)
    if not chapitres:
        st.info("Ajoutez un chapitre à cette matière.")
        st.stop()

    noms_c = {c["nom"]: c["id"] for c in chapitres}
    choix_c = st.selectbox("Chapitre", list(noms_c.keys()))
    chapitre_id = noms_c[choix_c]
    st.caption(f"{db.compter_questions(chapitre_id)} question(s) dans ce chapitre")

    st.divider()
    st.subheader("Téléverser un cours")
    fichiers = st.file_uploader(
        "PDF ou PowerPoint", type=["pdf", "pptx"], accept_multiple_files=True)
    intensite = st.select_slider(
        "Nombre de questions", ["Moins", "Standard", "Plus"], value="Standard")
    facteur = {"Moins": 0.5, "Standard": 1.0, "Plus": 1.6}[intensite]

    if fichiers and st.button("🚀 Générer les QCM"):
        if not cle_api:
            st.error("Saisissez votre clé API Gemini dans le menu de gauche.")
        else:
            for fichier in fichiers:
                st.subheader(fichier.name)
                with st.spinner("Lecture du document..."):
                    contenu = fichier.read()
                    if fichier.name.lower().endswith(".pdf"):
                        pages = pages_depuis_pdf(contenu)
                    else:
                        pages = pages_depuis_pptx(contenu)
                st.write(f"{len(pages)} page(s) détectée(s).")

                # Traitement par lots de 8 pages pour rester dans le quota
                TAILLE_LOT = 8
                total = 0
                barre = st.progress(0.0)
                nb_lots = (len(pages) + TAILLE_LOT - 1) // TAILLE_LOT
                for n in range(nb_lots):
                    lot = pages[n * TAILLE_LOT:(n + 1) * TAILLE_LOT]
                    cible = max(3, int(len(lot) * 1.5 * facteur))
                    try:
                        qs = generer_qcm_avec_retry(cle_api, lot, cible)
                        db.ajouter_questions(chapitre_id, qs)
                        total += len(qs)
                    except Exception as e:
                        st.warning(f"Lot {n + 1} ignoré : {e}")
                    barre.progress((n + 1) / nb_lots)
                st.success(f"{total} question(s) ajoutée(s) depuis {fichier.name} !")

# ----- Page : Quiz -----
elif page == "📝 Faire un quiz":
    st.header("Quiz")
    matieres = db.lister_matieres()
    if not matieres:
        st.info("Ajoutez d'abord des cours.")
        st.stop()

    noms = {m["nom"]: m["id"] for m in matieres}
    choix_m = st.selectbox("Matière", list(noms.keys()))
    chapitres = db.lister_chapitres(noms[choix_m])
    if not chapitres:
        st.info("Cette matière n'a pas encore de chapitre.")
        st.stop()

    noms_c = {c["nom"]: c["id"] for c in chapitres}
    choix_c = st.selectbox("Chapitre", list(noms_c.keys()))
    chapitre_id = noms_c[choix_c]

    # 1. Choix du chapitre
    noms_c = {c["nom"]: c["id"] for c in chapitres}
    choix_c = st.selectbox("Chapitre", list(noms_c.keys()))
    chapitre_id = noms_c[choix_c]
    
    # 2. Le bouton Démarrer
    if st.button("▶️ Démarrer / Relancer le quiz"):
        qs = list(db.lister_questions(chapitre_id))
        random.shuffle(qs)
        st.session_state.quiz = [q["id"] for q in qs]
        st.session_state.index = 0
        st.session_state.score = 0
        st.session_state.repondu = False
    
    # 3. ICI : la vérification (cause 1)
    if not st.session_state.get("quiz"):
        st.warning("Aucune question chargée. Choisissez un chapitre et cliquez sur « ▶️ Démarrer / Relancer le quiz ».")
        st.stop()
    
    # 4. Ensuite seulement, l'affichage de la question
    quiz = st.session_state.quiz
    i = st.session_state.index
    # ... le reste de votre code (affichage de la question, options, etc.)



        if i >= len(quiz):
            st.success(f"Terminé ! Score : {st.session_state.score}/{len(quiz)}")
            if not st.session_state.get("resultat_enregistre"):
                db.enregistrer_resultat(chapitre_id, st.session_state.score, len(quiz))
                st.session_state.resultat_enregistre = True
        else:
            q = db.get_question(quiz[i])
            options = q["options"]
            if isinstance(options, str):
                options = json.loads(options)

            st.progress(i / len(quiz))
            st.subheader(f"Question {i + 1}/{len(quiz)}")
            if q["image"]:
                try:
                    img = q["image"]
                    if isinstance(img, str):
                        if img.startswith("\\x"):
                            img = bytes.fromhex(img[2:])
                        else:
                            import base64
                            img = base64.b64decode(img)
                    st.image(img)
                except Exception:
                    st.caption("⚠️ Image illisible pour cette question.")

            reponse = st.radio("Votre réponse :", options, index=None,
                               key=f"rep_{i}", disabled=st.session_state.repondu)

            if not st.session_state.repondu:
                if st.button("Valider") and reponse is not None:
                    st.session_state.repondu = True
                    st.session_state.derniere = options.index(reponse)
                    if st.session_state.derniere == q["bonne_reponse"]:
                        st.session_state.score += 1
                    st.rerun()
            else:
                if st.session_state.derniere == q["bonne_reponse"]:
                    st.success("✅ Bonne réponse !")
                else:
                    st.error(f"❌ Bonne réponse : {options[q['bonne_reponse']]}")
                if q["explication"]:
                    st.info(q["explication"])
                if st.button("Question suivante ➡️"):
                    st.session_state.index += 1
                    st.session_state.repondu = False
                    st.session_state.resultat_enregistre = False
                    st.rerun()

# ----- Page : Progression -----
elif page == "📊 Progression":
    st.header("📊 Progression")
    matieres = db.lister_matieres()
    if not matieres:
        st.info("Ajoutez d'abord des cours.")
        st.stop()

    for m in matieres:
        moy_m, nb_m = db.stats_matiere(m["id"])
        titre = f"📘 {m['nom']}"
        if moy_m is not None:
            titre += f" — {moy_m} % ({nb_m} quiz)"
        else:
            titre += " — pas encore de quiz"

        with st.expander(titre):
            chapitres = db.lister_chapitres(m["id"])
            if not chapitres:
                st.caption("Aucun chapitre.")
            for c in chapitres:
                moy_c, nb_c = db.stats_chapitre(c["id"])
                nb_q = db.compter_questions(c["id"])
                if moy_c is None:
                    st.write(f"**{c['nom']}** : {nb_q} question(s), jamais testé")
                else:
                    st.write(f"**{c['nom']}** : {nb_q} question(s), "
                             f"moyenne {moy_c} % sur {nb_c} quiz")
                    st.progress(moy_c / 100)
