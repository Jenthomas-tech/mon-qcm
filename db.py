import json
import base64
import streamlit as st
from supabase import create_client


@st.cache_resource
def get_client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def init_db():
    # Les tables sont créées dans Supabase (SQL Editor), rien à faire ici.
    pass


def _image_to_text(image):
    if image is None:
        return None
    return base64.b64encode(image).decode("ascii")


def _text_to_image(texte):
    if not texte:
        return None
    return base64.b64decode(texte)


def _convertir_question(row):
    row = dict(row)
    row["image"] = _text_to_image(row.get("image"))
    return row


def lister_matieres():
    res = get_client().table("matieres").select("*").order("nom").execute()
    return res.data


def ajouter_matiere(nom):
    nom = nom.strip()
    if not nom:
        return
    get_client().table("matieres").upsert(
        {"nom": nom}, on_conflict="nom", ignore_duplicates=True).execute()


def lister_chapitres(matiere_id):
    res = (get_client().table("chapitres").select("*")
           .eq("matiere_id", matiere_id).order("nom").execute())
    return res.data


def ajouter_chapitre(matiere_id, nom):
    nom = nom.strip()
    if not nom:
        return
    get_client().table("chapitres").upsert(
        {"matiere_id": matiere_id, "nom": nom},
        on_conflict="matiere_id,nom", ignore_duplicates=True).execute()


def ajouter_questions(chapitre_id, questions):
    """questions: liste de dicts avec enonce, options, bonne_reponse,
    explication, image (bytes ou None)."""
    lignes = []
    for q in questions:
        lignes.append({
            "chapitre_id": chapitre_id,
            "enonce": q["enonce"],
            "options": json.dumps(q["options"], ensure_ascii=False),
            "bonne_reponse": q["bonne_reponse"],
            "explication": q.get("explication", ""),
            "image": _image_to_text(q.get("image")),
        })
    if lignes:
        get_client().table("questions").insert(lignes).execute()


def lister_questions(chapitre_id):
    res = (get_client().table("questions").select("*")
           .eq("chapitre_id", chapitre_id).execute())
    return [_convertir_question(r) for r in res.data]

def get_question(question_id):
    res = (get_client().table("questions")
           .select("*")
           .eq("id", question_id)
           .execute())
    return res.data[0] if res.data else None


def compter_questions(chapitre_id):
    res = (get_client().table("questions").select("id", count="exact")
           .eq("chapitre_id", chapitre_id).execute())
    return res.count or 0


def supprimer_question(question_id):
    get_client().table("questions").delete().eq("id", question_id).execute()
