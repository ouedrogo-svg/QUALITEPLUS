import os
import sys
sys.path.insert(0, os.getcwd())
import psycopg2
from scripts.execute_sync import DB_PARAMS

conn = psycopg2.connect(**DB_PARAMS)
cur = conn.cursor()

for qid in [124, 137, 135]:
    cur.execute("""
        SELECT q.id, q.order, q.prompt, count(o.id) as n_opts
        FROM courses_quizquestion q
        LEFT JOIN courses_quizoption o ON o.question_id = q.id
        WHERE q.quiz_id = %s
        GROUP BY q.id, q.order, q.prompt
        ORDER BY q.order ASC
    """, (qid,))
    questions = cur.fetchall()
    print(f"\n=================== QUIZ {qid} (Total: {len(questions)}) ===================")
    print("--- PREMIÈRES QUESTIONS ---")
    for q in questions[:3]:
        print(f"  Order {q[1]}: {repr(q[2][:80])} ({q[3]} options)")
    print("--- DERNIÈRES QUESTIONS ---")
    for q in questions[-5:]:
        print(f"  Order {q[1]}: {repr(q[2][:80])} ({q[3]} options)")

conn.close()
