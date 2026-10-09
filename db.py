import sqlite3
import json

DB_PATH = "qcm.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS matieres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT UNIQUE NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS chapitres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matiere_id INTEGER NOT NULL,
        nom TEXT NOT NULL,
        UNIQUE(matiere_id, nom))""")
    c.execute("""CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapitre_id INTEGER NOT NULL,
        enonce TEXT NOT NULL,
        options TEXT NOT NULL,
        bonne_reponse INTEGER NOT NULL,
        explication TEXT,
        image BLOB,
        niveau INTEGER DEFAULT 0,
        prochaine_revision TEXT,
        nb_reussites INTEGER DEFAULT 0,
        nb_echecs INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()


def lister_matieres():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM matieres ORDER BY nom").fetchall()
    conn.close()
    return rows


def ajouter_matiere(nom):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO matieres (nom) VALUES (?)", (nom.strip(),))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def lister_chapitres(matiere_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chapitres WHERE matiere_id=? ORDER BY nom",
        (matiere_id,)).fetchall()
    conn.close()
    return rows


def ajouter_chapitre(matiere_id, nom):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO chapitres (matiere_id, nom) VALUES (?, ?)",
            (matiere_id, nom.strip()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def ajouter_questions(chapitre_id, questions):
    """questions: liste de dicts avec enonce, options, bonne_reponse,
    explication, image (bytes ou None)."""
    conn = get_conn()
    for q in questions:
        conn.execute(
            """INSERT INTO questions
               (chapitre_id, enonce, options, bonne_reponse, explication, image)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chapitre_id, q["enonce"], json.dumps(q["options"], ensure_ascii=False),
             q["bonne_reponse"], q.get("explication", ""), q.get("image")))
    conn.commit()
    conn.close()


def lister_questions(chapitre_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM questions WHERE chapitre_id=?", (chapitre_id,)).fetchall()
    conn.close()
    return rows


def compter_questions(chapitre_id):
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE chapitre_id=?",
        (chapitre_id,)).fetchone()[0]
    conn.close()
    return n


def supprimer_question(question_id):
    conn = get_conn()
    conn.execute("DELETE FROM questions WHERE id=?", (question_id,))
    conn.commit()
    conn.close()
