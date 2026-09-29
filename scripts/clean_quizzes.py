import os
import sys
from pathlib import Path
import psycopg2

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.execute_sync import DB_PARAMS

def main():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    
    # Trouver les quiz avec plus de 60 questions
    cur.execute("""
        SELECT q.id, c.title, cat.name, count(ques.id)
        FROM courses_correctionquiz q
        JOIN courses_monthlycorrection c ON q.correction_id = c.id
        JOIN courses_category cat ON c.category_id = cat.id
        JOIN courses_quizquestion ques ON ques.quiz_id = q.id
        GROUP BY q.id, c.title, cat.name
        HAVING count(ques.id) > 60
    """)
    quizzes = cur.fetchall()
    print(f"Quiz concernés avec > 60 questions : {len(quizzes)}")
    
    total_deleted = 0
    for qid, title, cat_name, total_q in quizzes:
        print(f"\n--- Nettoyage Quiz ID {qid} [{cat_name} - {title}] (actuellement {total_q} questions) ---")
        
        # Trouver les questions parasites avec order > 59
        cur.execute("""
            SELECT id, "order", prompt
            FROM courses_quizquestion
            WHERE quiz_id = %s AND "order" > 59
            ORDER BY "order" ASC
        """, (qid,))
        parasites = cur.fetchall()
        
        for pid, porder, pprompt in parasites:
            # Supprimer les options associées
            cur.execute("DELETE FROM courses_quizoption WHERE question_id = %s", (pid,))
            # Supprimer la question parasite
            cur.execute("DELETE FROM courses_quizquestion WHERE id = %s", (pid,))
            print(f"  [SUPPRIMÉ] Question #{pid} (order={porder}): {pprompt[:60]}")
            total_deleted += 1
            
        conn.commit()
        
        # Vérifier le nouveau nombre
        cur.execute("SELECT count(*) FROM courses_quizquestion WHERE quiz_id = %s", (qid,))
        new_count = cur.fetchone()[0]
        print(f"  --> Nouveau nombre de questions : {new_count}")

    conn.close()
    print(f"\nTotal des questions parasites supprimées : {total_deleted}")

if __name__ == '__main__':
    main()
