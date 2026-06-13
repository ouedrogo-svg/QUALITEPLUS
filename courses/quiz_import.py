"""Construction du quiz à partir de tableaux (CSV ou lignes extraites d’un PDF)."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import Counter
from typing import BinaryIO

# Numéros d’ordre du PDF : 1 … N (souvent 60 ; peut dépasser 60 si le corrigé est plus long).
QUIZ_QUESTION_NUMBER_MIN = 1
QUIZ_QUESTION_NUMBER_DEFAULT = 60
QUIZ_QUESTION_NUMBER_ABSOLUTE_MAX = 300
# Rétrocompatibilité (barème par défaut quand le quiz est vide).
QUIZ_QUESTION_NUMBER_MAX = QUIZ_QUESTION_NUMBER_DEFAULT
# QCM : nombre de propositions variable (max 4 comme dans le PDF)
QUIZ_MAX_OPTIONS = 4


def _valid_question_number(n: int | None) -> bool:
    return (
        isinstance(n, int)
        and QUIZ_QUESTION_NUMBER_MIN <= n <= QUIZ_QUESTION_NUMBER_ABSOLUTE_MAX
    )


def quiz_question_count_for_scoring(question_count: int) -> int:
    """Nombre de questions pour la barre de progression et le score (1 pt / question)."""
    if question_count > 0:
        return question_count
    return QUIZ_QUESTION_NUMBER_DEFAULT


def _finalize_quiz_specs(specs: list[dict]) -> list[dict]:
    """Une question par numéro d’ordre valide, triée par numéro (1 … N selon le PDF)."""
    by_number: dict[int, dict] = {}
    for spec in specs:
        n = spec.get("number")
        if not _valid_question_number(n):
            continue
        spec = _sanitize_question_spec_dict(spec)
        if n not in by_number:
            by_number[n] = spec
    return [by_number[i] for i in sorted(by_number.keys())]


def _norm_header(s: str) -> str:
    t = (s or "").strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", "_", t)


def _parse_reponses_cell(cell: str) -> list[int]:
    """
    Indices 1-based des bonnes réponses (colonne « Réponses » du corrigé).

    Formats acceptés : 1, 1;3, A, B, C, D, A;B, A,B, AB, AC, CB, ABCD, A+B, etc.
    (A=1, B=2, … ; plusieurs lettres collées = plusieurs bonnes réponses).
    """
    if not cell or not str(cell).strip():
        return []
    raw = str(cell).strip().upper()
    raw = "".join(
        c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn"
    )
    raw = re.sub(r"\s+", "", raw)
    for sep in (";", "|", "/", "\\", "·", "—", "–", "-", "+"):
        raw = raw.replace(sep, ",")
    raw = raw.replace(" ET ", ",").replace(" AND ", ",")
    parts = [p.strip(".,;:)]}(") for p in raw.split(",") if p.strip(".,;:)]}(")]
    out: list[int] = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            n = int(p)
            if n >= 1:
                out.append(n)
            continue
        letters_only = re.sub(r"[^A-Z]", "", p)
        if letters_only and re.sub(r"[A-Z]", "", p) == "":
            for ch in letters_only:
                out.append(ord(ch) - ord("A") + 1)
            continue
        if len(p) == 1 and "A" <= p <= "Z":
            out.append(ord(p) - ord("A") + 1)
    return sorted({i for i in out if i >= 1})


def _detect_answer_column_index(rows: list[list[str]]) -> int | None:
    """Repère la colonne dont les cellules ressemblent le plus à des indices / lettres de correction."""
    if not rows:
        return None
    width = max((len(r) for r in rows), default=0)
    if width < 2:
        return None
    best_j: int | None = None
    best_score = 0
    for j in range(width):
        score = 0
        for r in rows:
            if j < len(r) and _parse_reponses_cell(r[j]):
                score += 1
        if score > best_score:
            best_score = score
            best_j = j
    min_hits = 1 if len(rows) <= 4 else max(2, min(3, len(rows) // 4))
    if best_j is None or best_score < min_hits:
        return None
    return best_j


def _rectangularize_rows(rows: list[list[str]]) -> list[list[str]]:
    """Aligne toutes les lignes sur la même largeur (PDF : cellules fusionnées / colonnes manquantes)."""
    if not rows:
        return rows
    w = max((len(r) for r in rows), default=0)
    if w == 0:
        return rows
    out: list[list[str]] = []
    for r in rows:
        rr = [(r[i] if i < len(r) else "") for i in range(w)]
        out.append(rr)
    return out


def _strip_question_number_prefix(text: str) -> str:
    """Retire « 1. », « N°2 », « Q3) » en tête d’énoncé."""
    t = (text or "").strip()
    t = re.sub(r"^\s*(?:n[o°]\s*)?\d{1,3}\s*[\.\)\:、\-–]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*q(?:uestion)?\s*\d{1,3}\s*[\.\)\:]\s*", "", t, flags=re.IGNORECASE)
    return t.strip()


_OPTION_LETTER_MARK = re.compile(
    r"(?:^|\n)\s*(?:\(([A-Za-z])\)|([A-Za-z])\s*[\)\.\-\u2013:、])\s*\t?\s*",
    re.MULTILINE,
)
_ANSWER_KEY_ONLY_RE = re.compile(
    r"^[A-Z](?:\s*[,;+\/|]\s*[A-Z]|\s+et\s+[A-Z])*$",
    re.IGNORECASE,
)
_FALSE_OPTION_LINE_RE = re.compile(
    r"^[A-Za-z]\s*[\)\.\-\u2013:、]\s*(?:[A-Z]{2,20}|[A-Z](?:\s*[,;+\/|]\s*[A-Z])+)\s*$",
    re.IGNORECASE,
)


def _normalize_stem_text(stem: str) -> str:
    """Énoncé sur plusieurs lignes PDF → une seule phrase (comme dans le corrigé)."""
    t = (stem or "").strip()
    if not t:
        return t
    # Retirer les références NB d'abord
    t = strip_nb_references(t)
    if "\n" not in t:
        return t
    return re.sub(r"\s*\n\s*", " ", t).strip()


def _strip_option_letter_prefix(text: str) -> str:
    """Retire « A) », « A. », « A- », « A– », « A: », « (A) », « A » (lettre seule) en tête."""
    t = (text or "").strip()
    if not t:
        return ""
    
    # Normaliser les espaces
    original = t
    
    # (A), (B), (a), (b) — lettre entre parenthèses
    t = re.sub(r"^\([A-Za-z]\)\s*", "", t)
    if t != original:
        return t.strip()
    
    # A), A., A-, A–, A:, A、 avec espace optionnel
    t = re.sub(r"^[A-Za-z]\s*[\)\.\-\u2013:、]\s*", "", original)
    if t != original:
        return t.strip()
    
    # Format: lettre seule suivie d'espace puis texte (ex: "A Le principe...")
    # Vérifier que la première "lettre" est bien isolée
    match = re.match(r"^([A-Za-z])\s+(.+)$", original)
    if match:
        letter, rest = match.groups()
        # Vérifier que ce qui suit ressemble à du texte (pas juste une autre lettre)
        if len(rest) > 2 and not re.match(r"^[A-Za-z]\s*$", rest):
            return rest.strip()
    
    # Format numérique: 1), 1., 1-, etc.
    t = re.sub(r"^[0-9]+\s*[\)\.\-\u2013:]\s*", "", original)
    if t != original:
        return t.strip()
    
    return original


def _normalize_option_dedup_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _clean_prompt_text(prompt: str) -> str:
    t = _normalize_stem_text(_clean_fragmented_text(strip_nb_references(prompt or "")))
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    if re.match(r"^[A-D]\s*[\)\.\-\u2013:]\s*", t, flags=re.IGNORECASE):
        rest = re.sub(
            r"^[A-D]\s*[\)\.\-\u2013:]\s*[^.!?]*[.!?]\s*",
            "",
            t,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        if rest:
            t = rest
    marker = re.search(r"\s+[A-D]\s*[\)\.\-\u2013:]\s+", t, flags=re.IGNORECASE)
    if marker:
        t = t[: marker.start()].strip()
    next_question = re.search(
        r"(\?)\s+(?=(?:Quels?|Quelle?s?|Qui|Que|Comment|Pourquoi|Quand|Le|La|Les|L['’]))",
        t,
        flags=re.IGNORECASE,
    )
    if next_question:
        t = t[: next_question.end(1)].strip()
    elif "?" in t:
        after_question = re.search(r"\?\s+\S", t)
        if after_question:
            t = t[: after_question.start() + 1].strip()
    return t


def _clean_option_text_fragment(text: str) -> str:
    """Retire une lettre de correction isolée (ex. « 420 ans\\nC ») laissée par le PDF."""
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r"\n\s*([A-Za-z])\s*$", "", t, flags=re.IGNORECASE).strip()
    # Ne pas tronquer « A et B » / « A ou B » (propositions légitimes du corrigé).
    if not re.search(r"\s+(?:et|ou)\s+[A-Za-z]\s*$", t, re.IGNORECASE):
        if len(t) <= 48 and not re.search(r"[a-zàâéèêëïîôùûüç]{3,}", t):
            t = re.sub(r"\s+([A-Za-z])\s*$", "", t, flags=re.IGNORECASE).strip()
    return t


def _looks_like_answer_key_not_option(text: str) -> bool:
    """Vrai si le texte n’est qu’une clé de correction (A, B, ABC…), pas une vraie proposition."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    # Proposition réelle (mots en minuscules : « A et B », « A prix ferme », etc.)
    if re.search(r"[a-zàâäéèêëïîôùûüçœ]{2,}", t):
        return False
    if "'" in t or "’" in t:
        return False
    compact = re.sub(r"\s+", "", t.upper())
    if len(compact) == 1 and "A" <= compact <= "Z":
        return True
    if re.fullmatch(r"[A-Z]{2,20}", compact):
        return True
    return bool(_ANSWER_KEY_ONLY_RE.match(t) and len(t) <= 40)


def _sanitize_spec_options(texts: list[str], correct: list[int]) -> tuple[list[str], list[int]]:
    """
    Conforme au PDF : au plus 4 propositions distinctes, sans doublons ni clés de correction.
    Recalcule les indices des bonnes réponses après filtrage.
    """
    cleaned: list[str] = []
    old_to_new: dict[int, int] = {}
    seen: set[str] = set()
    for old_idx, raw in enumerate(texts, start=1):
        if len(cleaned) >= QUIZ_MAX_OPTIONS:
            break
        t = _clean_option_text_fragment(
            strip_nb_references(_strip_option_letter_prefix(raw))
        )
        if not t or _looks_like_answer_key_not_option(t):
            continue
        key = _normalize_option_dedup_key(t)
        if key in seen:
            continue
        seen.add(key)
        new_idx = len(cleaned) + 1
        old_to_new[old_idx] = new_idx
        cleaned.append(t)
    new_correct = sorted({old_to_new[i] for i in correct if i in old_to_new})
    return cleaned, new_correct


def _sanitize_question_spec_dict(spec: dict) -> dict:
    texts, correct = _sanitize_spec_options(spec.get("texts") or [], spec.get("correct") or [])
    out = dict(spec)
    out["prompt"] = _clean_prompt_text(out.get("prompt") or "")
    out["texts"] = texts
    out["correct"] = correct
    return out


# Dictionnaire des fragments de mots connus (mot coupé -> mot complet)
_WORD_FRAGMENTS = {
    'ministè re': 'ministère',
    'ministè res': 'ministères',
    'économi que': 'économique',
    'économi ques': 'économiques',
    'répo rdre': 'réponse',
    'répo rdres': 'réponses',
    'publi que': 'publique',
    'publi ques': 'publiques',
    'prépa ration': 'préparation',
    'administra tif': 'administratif',
    'administra tion': 'administration',
    'autorisa tion': 'autorisation',
    'program me': 'programme',
    'gesti on': 'gestion',
    'opera tion': 'opération',
    'exécu tion': 'exécution',
    'propo sition': 'proposition',
    'liquida tion': 'liquidation',
    'dépen se': 'dépense',
    'finan cier': 'financier',
    'dével oppement': 'développement',
    'informa tion': 'information',
    'popula tion': 'population',
    'région ale': 'régionale',
    'natio nale': 'nationale',
    'ordonna teur': 'ordonnateur',
    'comptable matière': 'comptable matière',  # Pas de changement mais valide
}

# En-têtes de table à filtrer
_HEADER_PATTERNS = [
    r'^Cont\s+Pr[eéè]p',
    r'^Adj\s+Cons',
    r'r[eéè]po\s+rdre',
    r'^rdre\s+Questions',
    r'^NB\s*:\s*page\s*\d+',
]

def _fix_word_fragments(text: str) -> str:
    """Corrige les mots coupés avec espace inséré."""
    for fragment, correction in _WORD_FRAGMENTS.items():
        text = text.replace(fragment, correction)
        # Essayer aussi avec des variantes de casse
        text = text.replace(fragment.capitalize(), correction.capitalize())
        text = text.replace(fragment.upper(), correction.upper())
    return text

def _is_header_line(line: str) -> bool:
    """Détecte si une ligne est un en-tête de table à ignorer."""
    line = line.strip()
    if not line:
        return False
    for pattern in _HEADER_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False

def _clean_fragmented_text(text: str) -> str:
    """
    Nettoie le texte PDF fragmenté pour tableau 3 colonnes (Ordre | Question | Réponse).
    Pipeline: 1) Filtrer en-têtes, 2) Corriger fragments, 3) Fusionner lignes coupées.
    """
    if not text:
        return text
    
    # Étape 1: Filtrer les en-têtes et lignes vides
    lines = text.split('\n')
    filtered = []
    for line in lines:
        line = line.strip()
        if line and not _is_header_line(line):
            filtered.append(line)
    
    if not filtered:
        return ""
    
    # Étape 2: Corriger les fragments avec espaces insérés
    text = '\n'.join(filtered)
    text = _fix_word_fragments(text)
    
    # Étape 3: Fusionner les lignes qui semblent être des fragments
    # ex: "crédits de pa" + "iement" -> "crédits de paiement"
    lines = text.split('\n')
    merged = []
    pending = ""
    
    for line in lines:
        if not pending:
            pending = line
            continue
        
        # Si pending se termine par des lettres et line commence par minuscule
        if pending[-1].isalpha() and line[0].islower():
            # Vérifier si la fusion crée un mot connu
            pending_last = pending.split()[-1]
            line_first = line.split()[0] if line else ""
            combined = (pending_last + line_first).lower()
            
            valid_combos = [
                'paiement', 'programme', 'ministère', 'autorisation',
                'économique', 'réponse', 'publique', 'préparation',
                'administration', 'gestion', 'opération', 'exécution',
                'proposition', 'liquidation', 'dépense', 'engagement',
                'investissement', 'financier', 'ordonnateur', 'programmes',
            ]
            
            if combined in valid_combos:
                # Fusionner sans espace
                pending = pending + line
                continue
        
        # Sinon, sauvegarder pending
        merged.append(pending)
        pending = line
    
    if pending:
        merged.append(pending)
    
    return '\n'.join(merged)


def strip_nb_references(text: str) -> str:
    """Retire les mentions « NB : Article… » (non affichées dans le quiz)."""
    t = (text or "").strip()
    if not t:
        return ""
    # D'abord nettoyer les fragments
    t = _clean_fragmented_text(t)
    lines = [
        ln
        for ln in t.splitlines()
        if ln.strip() and not re.match(r"^\s*NB\s*:", ln.strip(), flags=re.IGNORECASE)
    ]
    t = "\n".join(lines).strip()
    t = re.sub(r"\s*NB\s*:\s*.*$", "", t, flags=re.IGNORECASE | re.MULTILINE).strip()
    return t


def _normalize_option_texts(texts: list[str]) -> list[str]:
    """Nettoie les propositions (sans ligne NB) et fusionne les lignes multi-lignes."""
    out: list[str] = []
    for raw in texts:
        t = strip_nb_references(_strip_option_letter_prefix(raw))
        if t:
            # Fusionner les retours à la ligne en espaces pour les options multi-lignes
            t = re.sub(r"\s*\n+\s*", " ", t).strip()
            if t:
                out.append(t)
    return out


def _split_stem_and_embedded_options(full_question: str) -> tuple[str, list[str]]:
    """
    Détecte des propositions « A) … B) … » (format corrigé) ou « A. … » dans le bloc question.
    Retourne (énoncé principal, textes des propositions sans le préfixe lettre).
    """
    full = (full_question or "").strip()
    if not full:
        return "", []
    marks = _OPTION_LETTER_MARK
    matches = list(marks.finditer(full))
    if len(matches) < 2:
        marks = re.compile(
            r"(?:(?:^|\n)|(?<=[\s\?\!\:;«»]))\s*(?:\(([A-Za-z])\)|([A-Za-z])\s*[\.\)\:、\-–])\s*",
            re.MULTILINE,
        )
        matches = list(marks.finditer(full))
    if len(matches) < 2:
        return full, []
    matches = matches[:QUIZ_MAX_OPTIONS]
    stem = full[: matches[0].start()].strip()
    texts: list[str] = []
    for k, m in enumerate(matches):
        start = m.end()
        end = matches[k + 1].start() if k + 1 < len(matches) else len(full)
        chunk = full[start:end].strip()
        if chunk:
            texts.append(_strip_option_letter_prefix(chunk))
    if not stem:
        stem = _strip_question_number_prefix(full[: matches[0].start()].strip())
    return _normalize_stem_text(stem), _normalize_option_texts(texts)


def _split_stem_embedded_numbered_options(full_question: str) -> tuple[str, list[str]]:
    """Propositions numérotées « 1) … 2) … » dans la cellule Questions (hors tout-chiffre isolé)."""
    full = (full_question or "").strip()
    if not full:
        return "", []
    marks = re.compile(
        r"(?:(?:^|\n)|(?<=[\s\?\!\:;«»]))\s*([1-9]|[12][0-9])\s*[\.\)\:、\-–]\s*",
        re.MULTILINE,
    )
    matches = list(marks.finditer(full))
    if len(matches) < 2:
        return full, []
    matches = matches[:QUIZ_MAX_OPTIONS]
    stem = full[: matches[0].start(1)].strip()
    texts: list[str] = []
    for k, m in enumerate(matches):
        start = m.end()
        end = matches[k + 1].start(1) if k + 1 < len(matches) else len(full)
        chunk = full[start:end].strip()
        if chunk:
            texts.append(chunk)
    if not stem:
        stem = _strip_question_number_prefix(full[: matches[0].start(1)].strip())
    return stem, texts


def _split_stem_embedded_bullet_options(full_question: str) -> tuple[str, list[str]]:
    """Propositions en puces « - … » ou « • … » sur des lignes distinctes."""
    full = (full_question or "").strip()
    if not full:
        return "", []
    lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
    if len(lines) < 3:
        return full, []
    bullet_pat = re.compile(r"^[\-–•·▪▸]\s*(.+)$")
    bullets: list[str] = []
    first_bi = None
    for i, ln in enumerate(lines):
        m = bullet_pat.match(ln)
        if m:
            if first_bi is None:
                first_bi = i
            bullets.append(m.group(1).strip())
        elif bullets:
            break
    if len(bullets) < 2 or first_bi is None or first_bi == 0:
        return full, []
    stem = "\n".join(lines[:first_bi]).strip()
    if not stem:
        stem = full
    return stem, bullets


def _correct_indices_from_rep_vs_options(embedded: list[str], rep_cell: str) -> list[int]:
    """
    Interprète la colonne « Réponses » pour cocher les bonnes cases : indices / lettres,
    ou texte identique (ou très proche) d’une proposition — jamais affiché comme choix.
    """
    rep = (rep_cell or "").strip()
    if not rep or not embedded:
        return []
    idxs = _parse_reponses_cell(rep)
    idxs_ok = sorted({i for i in idxs if 1 <= i <= len(embedded)})
    if idxs_ok:
        return idxs_ok
    rep_l = rep.lower()
    for j, t in enumerate(embedded):
        tt = t.strip().lower()
        if tt == rep_l:
            return [j + 1]
    if len(rep_l) >= 2:
        for j, t in enumerate(embedded):
            tt = t.strip().lower()
            if rep_l in tt or tt in rep_l:
                return [j + 1]
    return []


def _parse_ordre_cell(cell: str) -> int | None:
    """Numéro de question depuis la colonne « N° d’ordre » (1 … 300)."""
    t = (cell or "").strip()
    if not t:
        return None
    # Cas classique : le numéro est seul ou précédé de N°, Q, Question
    m = re.match(r"^\s*(?:n[o°]|q(?:uestion)?\s*)?\s*(\d{1,3})\s*[\.\)\:]?\s*$", t, flags=re.IGNORECASE)
    if not m:
        m = re.match(r"^\s*(\d{1,3})\s*$", t)
    if not m:
        # Cas plus souple : le numéro est suivi d'un espace ou d'un séparateur et de texte
        m = re.match(r"^\s*(?:n[o°]|q(?:uestion)?\s*)?\s*(\d{1,3})\s*[\.\)\:、\-–\s]", t, flags=re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    return n if _valid_question_number(n) else None


def _parse_ordre_from_row(row: list[str], preferred_col: int = 0) -> int | None:
    """Repère le N° d’ordre (col. 0, ou 1/2 si le PDF décale la colonne)."""
    if not row:
        return None
    cols = [preferred_col]
    for j in (0, 1, 2):
        if j not in cols:
            cols.append(j)
    for j in cols:
        if j < len(row):
            n = _parse_ordre_cell(row[j])
            if n is not None:
                return n
    return None


def _spec_with_number(prompt: str, texts: list[str], correct: list[int], number: int | None) -> dict:
    """Construit une spec ; le champ order en base = number - 1 (numéro affiché = number)."""
    texts, correct = _sanitize_spec_options(texts, correct)
    return {"prompt": prompt, "texts": texts, "correct": correct, "number": number}


def _norm_column_header_suggests_ordre(n: str) -> bool:
    """Colonne d’en-tête type « N° d’ordre », « rang », etc. (pas question ni réponse)."""
    if "question" in n or "reponse" in n:
        return False
    return (
        "ordre" in n
        or n in ("no", "rang", "index", "item", "numero")
        or re.match(r"^n_o_?d", n)
        or re.match(r"^n_?d_?ordre", n)
    )


def _column_data_looks_like_ordre_index(data_rows: list[list[str]], col_j: int) -> bool:
    """Heuristique : la colonne contient surtout des numéros d’ordre."""
    sample = [r for r in data_rows[:30] if r and len(r) > col_j]
    if len(sample) < 2:
        return False
    hits = sum(
        1
        for r in sample
        if _parse_ordre_cell((r[col_j] if col_j < len(r) else "") or "") is not None
    )
    return hits >= max(2, int(len(sample) * 0.6))


def _exclude_column_from_propositions(
    col_i: int,
    *,
    qi: int,
    ri: int,
    norms: list[str],
    data_rows: list[list[str]],
) -> bool:
    """Évite d’utiliser la colonne « N° » comme proposition (erreur fréquente PDF / tableur)."""
    if col_i == qi or col_i == ri:
        return True
    if col_i < len(norms) and _norm_column_header_suggests_ordre(norms[col_i]):
        return True
    if col_i != qi and qi != 0 and col_i == 0 and _column_data_looks_like_ordre_index(data_rows, 0):
        return True
    return False


def _options_texts_align_with_extracted(embedded: list[str], col_texts: list[str]) -> bool:
    """Les options extraites du texte coïncident avec les colonnes (énoncé seul dans la cellule question)."""
    cols = [(c or "").strip() for c in col_texts if (c or "").strip()]
    if len(cols) < 2 or len(embedded) < 2:
        return False
    n = min(len(cols), len(embedded), QUIZ_MAX_OPTIONS)
    for k in range(n):
        a = re.sub(r"\s+", " ", embedded[k].strip().lower())[:140]
        b = re.sub(r"\s+", " ", cols[k].strip().lower())[:140]
        if a == b or a in b or b in a:
            continue
        return False
    return True


def _stem_for_oqr_with_column_options(q_cell: str, col_texts: list[str]) -> str:
    """
    Énoncé principal quand les réponses sont en colonnes séparées : évite de répéter A/B dans le libellé
    si la cellule question contient déjà le même texte que les colonnes.
    """
    stem_a, emb_a = _split_stem_and_embedded_options(q_cell)
    if stem_a and len(emb_a) >= 2 and _options_texts_align_with_extracted(emb_a, col_texts):
        return _strip_question_number_prefix(stem_a)
    stem_n, emb_n = _split_stem_embedded_numbered_options(q_cell)
    if stem_n and len(emb_n) >= 2 and _options_texts_align_with_extracted(emb_n, col_texts):
        return _strip_question_number_prefix(stem_n)
    return _strip_question_number_prefix(q_cell)


def _detect_answer_column_index_oqr(rows: list[list[str]], i_o: int, width: int) -> int:
    """Colonne « Réponses » : lettres A–D (souvent dernière colonne du corrigé)."""
    sample = rows[: min(50, len(rows))]
    best_j = width - 1
    best_hits = 0
    for j in range(i_o + 1, width):
        hits = 0
        for r in sample:
            if j >= len(r):
                continue
            cell = (r[j] or "").strip().upper()
            if re.match(r"^[A-D](?:\s*[,;]\s*[A-D])*$", cell) or cell in ("A", "B", "C", "D"):
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_j = j
    return best_j


def _first_ordre_row_index(rows: list[list[str]]) -> int | None:
    for i, r in enumerate(rows):
        if _parse_ordre_from_row(r, 0) is not None:
            return i
    return None


def _try_spec_from_wide_correction_row(row: list[str]) -> dict | None:
    """
    Ligne de tableau élargi (N° en col. 1, énoncé au centre, réponse à droite)
    non lue par le parseur multi-lignes standard.
    """
    n = _parse_ordre_from_row(row, 0)
    if not _valid_question_number(n):
        return None
    rep = ""
    for j in range(len(row) - 1, -1, -1):
        cell = (row[j] if j < len(row) else "").strip()
        if _cell_looks_like_reponse(cell):
            rep = cell
            break
    if not rep:
        rep = _rep_cell_from_row(row, len(row) - 1)

    q_cell = ""
    for j, cell in enumerate(row):
        t = (cell or "").strip()
        if not t:
            continue
        if j < 3 and _parse_ordre_cell(t) == n:
            continue
        if _cell_looks_like_reponse(t):
            continue
        if len(t) > len(q_cell):
            q_cell = t
    if not q_cell:
        return None

    stem, embedded = _embedded_from_merged_question_text(q_cell)
    prompt = _normalize_stem_text(stem or q_cell)
    correct = _correct_indices_from_rep_vs_options(embedded, rep)
    return _spec_with_number(prompt, embedded, correct, n)


def _table_has_option_rows(rows: list[list[str]]) -> bool:
    """Lignes de propositions (a) b) …) sans numéro d’ordre — suite d’une question."""
    pat = re.compile(r"(?:^|\n)\s*[A-Za-z1-9][0-9]?\s*[\)\.]\s*\S", re.MULTILINE)
    for r in rows:
        for c in r:
            if c and pat.search(c):
                return True
    return False


def _spec_is_plausible(spec: dict) -> bool:
    """Évite d’écraser une bonne question par un tableau PDF mal découpé."""
    spec = _sanitize_question_spec_dict(spec)
    n_opts = len(spec.get("texts") or [])
    return 2 <= n_opts <= QUIZ_MAX_OPTIONS and bool((spec.get("prompt") or "").strip())


def _spec_richness(spec: dict) -> tuple[int, int, int, int]:
    """Score pour comparer deux specs : priorité à la présence de réponses correctes,
    puis nombre d'options raisonnable (2-4), puis longueur de l'énoncé."""
    n_opts = len(spec.get("texts") or [])
    has_correct = 1 if spec.get("correct") else 0
    # Pénaliser les specs avec trop d'options (> 4 est suspect pour un QCM)
    opts_score = n_opts if n_opts <= 4 else 4 - (n_opts - 4)
    prompt_len = len(spec.get("prompt") or "")
    return (has_correct, opts_score, prompt_len, n_opts)


def _enrich_spec_with_continuation(spec: dict, continuation_parts: list[str], *, prepend: bool = False) -> dict:
    """
    Ajoute la suite d’une question (ex. options c) d) sur la page suivante)
    OU le début d'une question (quand le numéro n'apparaît qu'après quelques lignes).
    """
    continuation_parts = _dedupe_and_clean_block_parts(continuation_parts)
    extra = "\n".join(p for p in continuation_parts if p).strip()
    if not extra:
        return spec
        
    _, embedded_extra = _embedded_from_merged_question_text(extra)
    existing = list(spec.get("texts") or [])
    seen = {t.strip().lower() for t in existing}
    merged = list(existing)
    for t in embedded_extra:
        key = t.strip().lower()
        if key and key not in seen:
            merged.append(t)
            seen.add(key)
            
    if len(merged) <= len(existing):
        # Pas de nouvelles propositions détectées -> c'est de l'énoncé pur
        if prepend:
            combined = f"{extra}\n{spec.get('prompt', '')}".strip()
        else:
            combined = f"{spec.get('prompt', '')}\n{extra}".strip()
            
        stem, embedded = _embedded_from_merged_question_text(combined)
        if len(embedded) > len(existing) or len(combined) > len(spec.get('prompt', '')):
            out = dict(spec)
            out["prompt"] = _normalize_stem_text(stem or combined)
            if len(embedded) > len(existing):
                out["texts"] = embedded
            return _sanitize_question_spec_dict(out)
        return spec
        
    out = dict(spec)
    out["texts"] = merged
    return _sanitize_question_spec_dict(out)


def _table_correction_layout(rows: list[list[str]]) -> tuple[int, int, int] | None:
    """
    Détecte la structure du corrigé : N° d’ordre | texte question (souvent col. 2) | Réponses.
    Retourne (i_o, i_r, index_première_ligne_données) ou None.
    """
    if not rows:
        return None
    width = max(len(r) for r in rows)
    if width < 3:
        return None

    hdr = _header_ordre_question_reponse_indices(rows[0])
    if hdr:
        return hdr[0], hdr[2], 1

    data_start = 0
    sample = rows[data_start : data_start + min(45, len(rows))]
    ordre_hits = sum(
        1 for r in sample if _parse_ordre_cell((r[0] if r else "") or "") is not None
    )
    i_o = 0
    eff_w = _dominant_data_row_width(rows, data_start)
    if eff_w == 3:
        i_r = 2
    else:
        i_r = _detect_answer_column_index_oqr(rows, i_o, width)
        if eff_w >= 3 and i_r >= eff_w:
            i_r = eff_w - 1

    if ordre_hits >= 2:
        return i_o, i_r, data_start

    if ordre_hits == 1:
        first_ordre = _first_ordre_row_index(rows)
        if first_ordre is not None:
            return i_o, i_r, first_ordre

    if len(rows) >= 2 and _table_has_option_rows(rows):
        return i_o, i_r, data_start

    return None


def _score_correction_table_rows(rows: list[list[str]]) -> int:
    """Nombre de N° d’ordre valides dans le tableau."""
    layout = _table_correction_layout(rows)
    if not layout:
        return 0
    i_o, _, data_start = layout
    return sum(
        1
        for r in rows[data_start:]
        if _parse_ordre_cell((r[i_o] if i_o < len(r) else "") or "") is not None
    )


def specs_from_correction_table_rows(rows: list[list[str]]) -> list[dict]:
    """Convertit un tableau corrigé (une ou plusieurs pages) en questions quiz."""
    layout = _table_correction_layout(rows)
    if not layout:
        return []
    i_o, i_r, data_start = layout
    width = max(len(r) for r in rows)
    i_q = i_o + 1 if i_o + 1 < i_r else i_o
    specs = _parse_oqr_multiline_blocks(
        rows[data_start:], i_o=i_o, i_q=i_q, i_r=i_r, width=width
    )
    return _finalize_quiz_specs(specs)


def _header_ordre_question_reponse_indices(header: list[str]) -> tuple[int, int, int] | None:
    """Repère les indices des colonnes « N° d’ordre », « Questions », « Réponses »."""
    norms = [_norm_header(h) for h in header]

    def col_ordre(i: int, n: str) -> bool:
        if "question" in n or "reponse" in n:
            return False
        return (
            "ordre" in n
            or n in ("no", "rang", "index", "item", "numero")
            or re.match(r"^n_o_?d", n)
            or re.match(r"^n_?d_?ordre", n)
        )

    def col_question(i: int, n: str) -> bool:
        return (
            "question" in n
            or n in ("enonce", "intitule", "libelle", "texte", "stem", "prompt", "q")
        )

    def col_reponse(i: int, n: str) -> bool:
        return "reponse" in n or n in ("corrige", "solution", "cle", "key", "rep", "ok")

    i_o = next((i for i, n in enumerate(norms) if col_ordre(i, n)), None)
    i_q = next((i for i, n in enumerate(norms) if col_question(i, n)), None)
    i_r = next((i for i, n in enumerate(norms) if col_reponse(i, n)), None)
    if i_o is None or i_q is None or i_r is None:
        return None
    if len({i_o, i_q, i_r}) != 3:
        return None
    return i_o, i_q, i_r


def _dominant_data_row_width(rows: list[list[str]], data_start: int = 0) -> int:
    """Largeur la plus fréquente des lignes de données (évite un en-tête plus large que le corps)."""
    lens = [len(r) for r in rows[data_start:] if any((c or "").strip() for c in r)]
    if not lens:
        return max((len(r) for r in rows), default=0)
    return Counter(lens).most_common(1)[0][0]


def _cell_looks_like_reponse(cell: str) -> bool:
    """Vrai si la cellule ressemble à la colonne « Réponses » (A, BC, 1;3…)."""
    t = (cell or "").strip()
    if not t or len(t) > 16:
        return False
    if _parse_reponses_cell(t):
        return True
    compact = re.sub(r"\s+", "", t.upper())
    if re.fullmatch(r"[A-Z]{1,4}", compact):
        return True
    return bool(re.match(r"^[A-Z](?:\s*[,;+\/|]\s*[A-Z])+$", t, re.IGNORECASE))


def _rep_cell_from_row(row: list[str], i_r: int) -> str:
    """Lit la colonne « Réponses » même si les lignes ont moins de colonnes que l’en-tête."""
    if i_r < len(row):
        cell = (row[i_r] or "").strip()
        if _cell_looks_like_reponse(cell):
            return cell
    for j in range(len(row) - 1, 0, -1):
        cell = (row[j] or "").strip()
        if not cell or _parse_ordre_cell(cell) is not None:
            continue
        if _cell_looks_like_reponse(cell):
            return cell
    return ""


def _content_column_indices(i_o: int, i_r: int, row_width: int) -> list[int]:
    """Colonnes d’énoncé / propositions (exclut N° d’ordre et colonne Réponses)."""
    return [j for j in range(i_o + 1, min(i_r, row_width))]


def _row_merged_content(row: list[str], col_indices: list[int]) -> str:
    """Fusionne le texte des colonnes « question » (souvent réparti sur col. 2–3 dans le PDF)."""
    parts: list[str] = []
    for j in col_indices:
        if j < len(row):
            t = (row[j] or "").strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _explicit_option_column_indices(header: list[str], i_q: int, i_r: int) -> list[int]:
    cols: list[int] = []
    expected = "abcd"
    for j in range(i_q + 1, i_r):
        h = re.sub(r"[^a-z]", "", _norm_header(header[j] if j < len(header) else ""))
        if len(h) == 1 and h in expected:
            cols.append(j)
    if len(cols) >= 2 and "".join(
        re.sub(r"[^a-z]", "", _norm_header(header[j] if j < len(header) else ""))
        for j in cols[:QUIZ_MAX_OPTIONS]
    ).startswith(expected[: len(cols[:QUIZ_MAX_OPTIONS])]):
        return cols[:QUIZ_MAX_OPTIONS]
    return []


def _is_false_option_line(text: str) -> bool:
    """Ligne type « D) ABC » : clé de correction PDF, pas une proposition."""
    t = (text or "").strip()
    if not t:
        return False
    if _FALSE_OPTION_LINE_RE.match(t):
        return True
    body = _strip_option_letter_prefix(t)
    return bool(body) and _looks_like_answer_key_not_option(body)


def _dedupe_and_clean_block_parts(parts: list[str]) -> list[str]:
    """Supprime doublons de page, lignes NB et fausses propositions « D) ABC »."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        p = (raw or "").strip()
        if not p or re.match(r"^\s*NB\s*:", p, flags=re.IGNORECASE):
            continue
        if _is_false_option_line(p):
            continue
        key = _normalize_option_dedup_key(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return _merge_split_option_parts(out)


def _orphan_parts_safe_for_next_question(parts: list[str], *, has_response: bool = False) -> list[str]:
    safe: list[str] = []
    for raw in parts:
        p = (raw or "").strip()
        if not p:
            continue
        if re.match(r"^\s*NB\s*:", p, flags=re.IGNORECASE):
            continue
        if not has_response and (_looks_like_option_line(p) or _OPTION_LETTER_MARK.search(p)):
            continue
        safe.append(p)
    return safe


def _block_has_complete_options(parts: list[str]) -> bool:
    text = "\n".join(p for p in parts if p)
    letters: set[str] = set()
    for m in _OPTION_LETTER_MARK.finditer(text):
        letter = (m.group(1) or m.group(2) or "").upper()
        if letter in {"A", "B", "C", "D"}:
            letters.add(letter)
    return len(letters) >= QUIZ_MAX_OPTIONS


def _option_line_looks_incomplete(line: str) -> bool:
    """Détecte si une ligne d'option semble incomplète (troncature)."""
    # Retirer le préfixe A), B), etc.
    content = _strip_option_letter_prefix(line).strip()
    if not content:
        return True
    if "'" in content or "’" in content:
        return False
    if re.search(r"\b[A-Z]{3,}\b", content):
        return False
    
    # Si ça se termine par une ponctuation forte, c'est probablement complet
    if re.search(r"[.!?;:…]$", content):
        return False
    
    # Si c'est très court (moins de 12 caractères) et sans ponctuation, probablement incomplet
    if len(content) < 12:
        return True
    
    # Si le dernier mot est très court (moins de 4 lettres) et sans ponctuation
    words = content.split()
    if words:
        last_word = words[-1]
        # Mot court sans ponctuation = probablement un fragment
        if len(last_word) < 4 and not re.search(r"[.!?;:…]$", last_word):
            return True
        # Mot qui finit par une consonne et une seule voyelle = probablement incomplet
        # (ex: "no", "sim", "op", "exc")
        if len(last_word) <= 3 and last_word.isalpha():
            vowels = sum(1 for c in last_word.lower() if c in 'aeiouyéèêëïîôùûü')
            if vowels <= 1:
                return True
    
    return False


def _merge_split_option_parts(parts: list[str]) -> list[str]:
    """Fusionne les lignes de suite (ex. « disposition » après « A) … leur »)."""
    out: list[str] = []
    pending_option: str | None = None
    
    for p in parts:
        p = p.strip()
        if not p:
            continue
        
        # Vérifier si c'est une nouvelle option (commence par lettre+nombre+ponctuation)
        is_new_option = (
            re.match(r"^[A-Za-z]\s*[\)\.\-\u2013:、]", p) or  # A), B., C-, etc.
            re.match(r"^\([A-Za-z]\)", p) or  # (A), (B)
            re.match(r"^[1-9][0-9]?\s*[\)\.\-\u2013:、]", p)  # 1), 2., etc.
        )
        
        # Si on a une option en attente qui semble incomplète
        if pending_option:
            if is_new_option:
                # La ligne courante est une nouvelle option
                # Vérifier si l'option en attente est vraiment incomplète
                if _option_line_looks_incomplete(pending_option):
                    # Essayer de fusionner avec la nouvelle option si elle commence par une minuscule
                    # (ex: "A) Procédure no" + "rmale." -> "A) Procédure normale.")
                    new_content = _strip_option_letter_prefix(p).strip()
                    if new_content and new_content[0].islower():
                        # Fusionner l'ancien préfixe avec le nouveau contenu combiné
                        old_prefix = re.match(r"^([A-Za-z]\s*[\)\.\-\u2013:、]|\([A-Za-z]\))", pending_option)
                        if old_prefix:
                            merged = f"{old_prefix.group(1)} {_strip_option_letter_prefix(pending_option).strip()}{new_content}"
                            pending_option = merged
                        else:
                            out.append(pending_option)
                    else:
                        out.append(pending_option)
                else:
                    out.append(pending_option)
                pending_option = None
            else:
                # La ligne courante n'est pas une option, fusionner
                merged_content = f"{_strip_option_letter_prefix(pending_option).strip()}\n{p}"
                old_prefix = re.match(r"^([A-Za-z]\s*[\)\.\-\u2013:、]|\([A-Za-z]\))", pending_option)
                if old_prefix:
                    pending_option = f"{old_prefix.group(1)} {merged_content}"
                else:
                    out.append(pending_option)
                    pending_option = p
                continue
        
        if out and not is_new_option:
            prev = out[-1]
            # Fusionner si la ligne précédente ne se termine pas par une ponctuation forte
            prev_ends_strong = re.search(r"[.!?;:…]\s*$", prev)
            current_is_continuation = len(p) < 40 and not re.search(r"[.!?;:…]$", p)
            
            if not prev_ends_strong or current_is_continuation:
                # Vérifier que ce n'est pas une nouvelle question
                if not _looks_like_new_question_start(p):
                    out[-1] = f"{prev}\n{p}"
                    continue
        
        # Si c'est une option qui semble incomplète, la mettre en attente
        if is_new_option and _option_line_looks_incomplete(p):
            pending_option = p
        else:
            out.append(p)
    
    # Ne pas oublier la dernière option en attente
    if pending_option:
        out.append(pending_option)
    
    return out


def _block_part_fingerprint(text: str) -> str:
    return _normalize_option_dedup_key(text)


def _embedded_from_merged_question_text(full: str) -> tuple[str, list[str]]:
    """Énoncé + propositions A/B/… à partir du bloc texte fusionné (plusieurs lignes PDF)."""
    full = (full or "").strip()
    if not full:
        return "", []
    
    # 0. Nettoyer et normaliser le texte d'entrée
    # Remplacer les espaces insécables et normaliser les retours
    full_clean = full.replace("\r\n", "\n").replace("\r", "\n")
    full_clean = re.sub(r"[\t\u00a0]+", " ", full_clean)
    
    # 1. Essayer le cas où énoncé et options sont sur des lignes séparées
    lines = [line.strip() for line in full_clean.splitlines() if line.strip()]
    if len(lines) >= 3:
        # Trouver la première ligne qui ressemble à une option
        option_start_idx = None
        for i, line in enumerate(lines):
            if _looks_like_option_line(line):
                option_start_idx = i
                break
        
        if option_start_idx is not None and option_start_idx > 0 and (len(lines) - option_start_idx) >= 2:
            stem_lines = lines[:option_start_idx]
            option_lines_raw = lines[option_start_idx:]
            
            # Fusionner les lignes d'options qui sont des continuations
            option_lines = _merge_split_option_parts(option_lines_raw)
            
            # Extraire le texte de chaque option
            embedded = []
            for opt_line in option_lines:
                # D'abord retirer les références NB
                opt_clean = strip_nb_references(opt_line)
                cleaned_opt = _strip_option_letter_prefix(opt_clean)
                # Filtrer les lignes qui ressemblent à des clés de réponse (A, B, AB)
                if cleaned_opt and not _looks_like_answer_key_not_option(cleaned_opt):
                    embedded.append(cleaned_opt)
            
            # Limiter à 4 options comme dans le PDF
            embedded = embedded[:QUIZ_MAX_OPTIONS]
            
            if len(embedded) >= 2:
                stem = " ".join(stem_lines)
                stem = _strip_question_number_prefix(stem)
                # Nettoyer les fragments de mots dans l'énoncé
                stem = _clean_fragmented_text(stem)
                return _normalize_stem_text(stem), _normalize_option_texts(embedded)
    
    # 2. Essayer les méthodes classiques avec patterns A), B), etc.
    stem, embedded = _split_stem_and_embedded_options(full_clean)
    if len(embedded) >= 2:
        stem = _strip_question_number_prefix(stem)
        stem = _clean_fragmented_text(stem)
        return _normalize_stem_text(stem), _normalize_option_texts(embedded)
    
    # 3. Essayer avec options numérotées 1), 2), etc.
    stem_n, embedded_n = _split_stem_embedded_numbered_options(full_clean)
    if len(embedded_n) >= 2:
        stem_n = _strip_question_number_prefix(stem_n)
        stem_n = _clean_fragmented_text(stem_n)
        return _normalize_stem_text(stem_n), _normalize_option_texts(embedded_n)
    
    # 4. Essayer avec puces
    stem_b, embedded_b = _split_stem_embedded_bullet_options(full_clean)
    if len(embedded_b) >= 2:
        stem_b = _strip_question_number_prefix(stem_b)
        stem_b = _clean_fragmented_text(stem_b)
        return _normalize_stem_text(stem_b), _normalize_option_texts(embedded_b)
    
    # 5. Dernier recours: essayer de deviner la structure
    # Si on a au moins 4 lignes, peut-être que c'est: énoncé, A..., B..., C..., D...
    if len(lines) >= 5:
        possible_stem = lines[0]
        possible_options = lines[1:5]  # Prendre jusqu'à 4 options
        # Vérifier que les 4 lignes suivantes pourraient être des options
        if all(len(opt) > 5 for opt in possible_options):
            cleaned_opts = [_strip_option_letter_prefix(opt) for opt in possible_options]
            cleaned_opts = [o for o in cleaned_opts if o]
            if len(cleaned_opts) >= 2:
                possible_stem = _strip_question_number_prefix(possible_stem)
                possible_stem = _clean_fragmented_text(possible_stem)
                return _normalize_stem_text(possible_stem), _normalize_option_texts(cleaned_opts)
    
    stem = _strip_question_number_prefix(full)
    stem = _clean_fragmented_text(stem)
    return _normalize_stem_text(stem), []


def _looks_like_option_line(text: str) -> bool:
    """Vrai si la ligne commence par une marque de proposition (A., B), A-, (A), etc.)."""
    t = (text or "").strip()
    if not t:
        return False
    # Normaliser les espaces et tirnets
    t_norm = re.sub(r"[\s\u00a0]+", " ", t)
    # A), B., A-, A–, A:, a), b. — avec ou sans espace avant le séparateur
    if re.match(r"^[A-Za-z]\s*[\)\.\-\u2013:、]", t_norm):
        return True
    # (A), (B), (a), (b) — lettre entre parenthèses
    if re.match(r"^\([A-Za-z]\)\s*", t_norm):
        return True
    # Lettre majuscule isolée suivie d'au moins 2 mots (ex: "A Le principe de...")
    # Plus permissif : accepte A-Z suivi d'espace puis n'importe quel mot
    if re.match(r"^[A-Z]\s+\S", t_norm) and len(t) > 3:
        # Vérifier que ce n'est pas juste une lettre isolée
        words = t_norm.split()
        if len(words) >= 2 and len(words[0]) == 1 and words[0].isalpha():
            return True
    # 1), 2., 1-, 2- (si utilisé pour les options)
    if re.match(r"^[1-9][0-9]?\s*[\)\.\-\u2013:、]", t_norm):
        return True
    # Format spécial: lettre suivie immédiatement de texte sans séparateur explicite
    # ex: "A Le principe" où A est seul et suivi d'un mot commençant par majuscule
    if re.match(r"^[A-Z]\s+[A-Z]", t):
        return True
    return False


def _has_any_options_in_block(parts: list[str]) -> bool:
    """Vrai si l'un des morceaux contient déjà une marque de proposition."""
    for p in parts:
        if _looks_like_option_line(p):
            return True
        if _OPTION_LETTER_MARK.search(p):
            return True
    return False


def _looks_like_new_question_start(text: str) -> bool:
    """Heuristique : le texte ressemble au début d'un nouvel énoncé."""
    t = (text or "").strip()
    if len(t) < 10:
        return False
    # Commence par une majuscule et contient plusieurs mots
    if re.match(r"^[A-ZÀÂÉÈÊËÏÎÔÙÛÜÇ]", t) and len(t.split()) >= 3:
        return True
    return False


def _parse_oqr_multiline_blocks(
    data_rows: list[list[str]],
    *,
    i_o: int,
    i_q: int,
    i_r: int,
    width: int,
) -> list[dict]:
    """
    Corrigé PDF réel : une question occupe plusieurs lignes du tableau.
    - Ligne de tête : N° d'ordre (col. 0) + lettre de réponse (dernière col.)
    - Lignes suivantes : énoncé et « A. … B. … » dans les colonnes centrales (souvent col. 2).
    Gère le cas où le contenu commence en fin de page et le numéro est sur la page suivante.
    """
    specs: list[dict] = []
    current_n: int | None = None
    current_rep = ""
    block_parts: list[str] = []
    orphan_parts: list[str] = []
    orphan_rep = ""

    def flush() -> None:
        nonlocal current_n, current_rep, block_parts
        if not _valid_question_number(current_n):
            block_parts = []
            return
        parts = _dedupe_and_clean_block_parts(block_parts)
        block_parts = []
        if not parts:
            return
        full = "\n".join(parts).strip()
        if not full:
            return
        stem, embedded = _embedded_from_merged_question_text(full)

        # Fallback : séparer directement les parts en énoncé / propositions
        # quand _embedded_from_merged_question_text ne trouve rien
        if len(embedded) < 2:
            stem_parts: list[str] = []
            opt_parts: list[str] = []
            found_first_option = False
            for p in parts:
                # Nettoyer avant de vérifier
                p_clean = strip_nb_references(p).strip()
                if not p_clean:
                    continue
                if not found_first_option and _looks_like_option_line(p_clean):
                    found_first_option = True
                if found_first_option:
                    opt_parts.append(p)
                else:
                    stem_parts.append(p)
            # Limiter à max 4 options comme dans le PDF
            if len(opt_parts) >= 2 and len(opt_parts) <= QUIZ_MAX_OPTIONS:
                embedded = [_strip_option_letter_prefix(o) for o in opt_parts]
                embedded = [e for e in embedded if e and not _looks_like_answer_key_not_option(e)]
                # Appliquer strip_nb_references sur chaque option
                embedded = [strip_nb_references(e) for e in embedded]
                embedded = [e for e in embedded if e]
                stem = " ".join(stem_parts).strip() if stem_parts else stem
                # Nettoyer les fragments de mots dans l'énoncé
                stem = _clean_fragmented_text(stem)

        if len(embedded) < 2:
            return
        correct = _correct_indices_from_rep_vs_options(embedded, current_rep)
        
        # Construire le prompt final
        if stem:
            # Nettoyer les fragments de mots
            stem = _clean_fragmented_text(stem)
            prompt = _normalize_stem_text(stem)
        else:
            # Essayer de prendre la première ligne comme énoncé si pas de stem détecté
            first_lines = [p for p in parts if not _looks_like_option_line(p)]
            if first_lines:
                prompt_text = _strip_question_number_prefix(first_lines[0])[:500]
                # Nettoyer les fragments de mots
                prompt_text = _clean_fragmented_text(prompt_text)
                prompt = _normalize_stem_text(prompt_text)
            else:
                prompt = "Question"
        
        specs.append(_spec_with_number(prompt, embedded, correct, current_n))

    for row in data_rows:
        while len(row) < width:
            row.append("")
        n_ord = _parse_ordre_from_row(row, i_o)
        row_cc = [i_q] if i_q < len(row) else (_content_column_indices(i_o, i_r, width) or [i_q])
        chunk = _row_merged_content(row, row_cc)
        row_rep = _rep_cell_from_row(row, i_r)

        if _valid_question_number(n_ord):
            flush()
            current_n = n_ord
            if row_rep:
                current_rep = row_rep
            safe_orphans = _orphan_parts_safe_for_next_question(orphan_parts, has_response=bool(orphan_rep))
            if safe_orphans:
                clean_chunk = _strip_question_number_prefix(chunk)
                block_parts = safe_orphans + ([clean_chunk] if clean_chunk else [])
                if orphan_rep and not current_rep:
                    current_rep = orphan_rep
                orphan_parts = []
            else:
                block_parts = [chunk] if chunk else []
                orphan_parts = []
            orphan_rep = ""
        elif current_n is not None and chunk:
            if row_rep and _block_has_complete_options(block_parts):
                flush()
                orphan_parts = [chunk]
                orphan_rep = row_rep
                current_n = None
                current_rep = ""
            else:
                if row_rep:
                    current_rep = row_rep
                block_parts.append(chunk)
        elif current_n is None and chunk:
            orphan_parts.append(chunk)
            if row_rep:
                orphan_rep = row_rep
    flush()
    return specs


def _rows_look_like_ordre_question_reponse_no_header(rows: list[list[str]]) -> bool:
    """Heuristique : 3 colonnes, 1re colonne = petits entiers sur les premières lignes."""
    if not rows:
        return False
    if not all(len(r) >= 3 for r in rows[: min(10, len(rows))]):
        return False
    sample = rows[: min(8, len(rows))]
    hits = sum(1 for r in sample if _parse_ordre_cell(r[0]) is not None)
    if len(sample) == 1:
        return hits == 1
    return hits >= max(2, len(sample) - 2)


def _try_ordre_question_reponse_table(rows: list[list[str]]) -> list[dict] | None:
    """
    Tableaux type corrigé : N° d’ordre | Questions | … | Réponses.

    - Si des **colonnes de propositions** se trouvent entre « Questions » et « Réponses »
      (ex. A, B, C, D), elles sont utilisées telles que dans le PDF (cas le plus fidèle).
    - Sinon, propositions détectées **dans** la cellule Questions (A., B., …, 1) 2), puces).
    - La colonne « Réponses » sert uniquement aux indices / lettres de correction.
    """
    if not rows:
        return None

    width = max(len(r) for r in rows)
    if width < 3:
        return None

    header = rows[0]
    idx = _header_ordre_question_reponse_indices(header)
    data_start = 1
    if idx is None:
        if width != 3 or not _rows_look_like_ordre_question_reponse_no_header(rows):
            return None
        i_o, i_q, i_r = 0, 1, 2
        data_start = 0
    else:
        if len(rows) < 2:
            return None
        i_o, i_q, i_r = idx

    data_rows = rows[data_start:]
    width = max(width, max((len(r) for r in data_rows), default=0))

    multiline_specs = _parse_oqr_multiline_blocks(
        data_rows, i_o=i_o, i_q=i_q, i_r=i_r, width=width
    )
    if multiline_specs:
        return _finalize_quiz_specs(multiline_specs) or None

    prop_col_indices = _explicit_option_column_indices(header, i_q, i_r)
    content_cols = list(range(i_o + 1, i_r)) or [i_q]

    specs: list[dict] = []
    for row in data_rows:
        while len(row) < width:
            row.append("")
        ordre_s = (row[i_o] if i_o < len(row) else "").strip()
        row_cc = [i_q] if i_q < len(row) else content_cols
        q_cell = _row_merged_content(row, row_cc) or (row[i_q] if i_q < len(row) else "").strip()
        rep_cell = _rep_cell_from_row(row, i_r)
        if not q_cell:
            continue
        n_ord = _parse_ordre_cell(ordre_s)
        if not _valid_question_number(n_ord):
            continue

        embedded: list[str] = []
        stem = ""
        texts_from_cols = (
            [(row[j] if j < len(row) else "").strip() for j in prop_col_indices]
            if len(prop_col_indices) >= 2
            else []
        )
        filled_cols = [t for t in texts_from_cols if t]
        used_col_options = len(prop_col_indices) >= 2 and len(filled_cols) >= 2
        if used_col_options:
            embedded = texts_from_cols
            stem = _stem_for_oqr_with_column_options(q_cell, embedded)
        else:
            stem, embedded = _split_stem_and_embedded_options(q_cell)
            if len(embedded) < 2:
                stem_n, embedded_n = _split_stem_embedded_numbered_options(q_cell)
                if len(embedded_n) >= 2:
                    stem, embedded = stem_n, embedded_n
            if len(embedded) < 2:
                stem_b, embedded_b = _split_stem_embedded_bullet_options(q_cell)
                if len(embedded_b) >= 2:
                    stem, embedded = stem_b, embedded_b
        if len(embedded) < 2:
            continue

        if used_col_options:
            correct = sorted(
                {i for i in _parse_reponses_cell(rep_cell) if 1 <= i <= len(embedded)}
            )
        else:
            correct = _correct_indices_from_rep_vs_options(embedded, rep_cell)

        main = _strip_question_number_prefix(stem) if stem else ""
        if not main and q_cell and used_col_options:
            main = _strip_question_number_prefix(q_cell)
        elif not main and q_cell and not used_col_options:
            first_ln = q_cell.splitlines()[0].strip()
            if first_ln and not re.match(r"^[A-Da-d]\s*[\.\)\:、\-–]", first_ln):
                main = _strip_question_number_prefix(first_ln)[:500]
        prompt = main or _strip_question_number_prefix(q_cell)[:400] or "Question"
        specs.append(_spec_with_number(prompt, embedded, correct, n_ord))

    return _finalize_quiz_specs(specs) or None


def _normalize_matrix_cell_text(raw: object) -> str:
    """
    Nettoie une cellule de tableau sans fusionner les paragraphes.
    Les corrigés mettent souvent l’énoncé puis, sur les lignes suivantes, « A. … B. … »
    dans la même cellule : il faut conserver les retours à la ligne.
    """
    if raw is None:
        return ""
    s = str(raw).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return ""
    # Nettoyer les fragments de texte (mots coupés aux mauvais endroits)
    s = _clean_fragmented_text(s)
    lines: list[str] = []
    for ln in s.split("\n"):
        t = re.sub(r"[ \t\u00a0]+", " ", ln).strip()
        if t:
            lines.append(t)
    return "\n".join(lines)


def _normalize_matrix_rows(raw_rows: list[list]) -> list[list[str]]:
    """Convertit une table (PDF/CSV) en lignes de chaînes, cellules None → ''. Les sauts de ligne à l’intérieur d’une cellule sont conservés."""
    out: list[list[str]] = []
    for raw in raw_rows:
        if raw is None:
            continue
        row = []
        for c in raw:
            row.append(_normalize_matrix_cell_text(c))
        if any(cell for cell in row):
            out.append(row)
    return out


def _matrix_rows_to_question_specs_with_header(rows: list[list[str]], skip_header: bool) -> list[dict]:
    if not rows or len(rows) < 2:
        return []
    data_rows = rows[1:] if skip_header else rows
    width = max((len(r) for r in rows), default=0)
    if width < 3:
        return []

    qi, ri = 0, width - 1
    prop_indices: list[int] = []

    if skip_header:
        header = rows[0]
        width = max(width, len(header))
        norms = [_norm_header(h) for h in header] if header else []

        def idx_of(pred) -> int | None:
            for i, n in enumerate(norms):
                if pred(n):
                    return i
            return None

        if norms:
            qi = idx_of(
                lambda n: n
                in (
                    "question",
                    "enonce",
                    "intitule",
                    "intitule_de_la_question",
                    "libelle",
                    "libelle_question",
                    "item",
                    "texte",
                    "q",
                    "n",
                    "no",
                    "numero",
                    "n_question",
                    "titre",
                    "stem",
                    "prompt",
                )
            )
            ri = idx_of(
                lambda n: n
                in (
                    "reponses",
                    "reponse",
                    "reponses_correctes",
                    "reponse_correcte",
                    "bons_indices",
                    "bonne_reponse",
                    "correct",
                    "corrige",
                    "cle",
                    "key",
                    "rep",
                    "reps",
                    "solution",
                    "solutions",
                    "justification",
                    "ok",
                )
            )
        if qi is None:
            qi = 0
        if ri is None:
            ri = width - 1 if width > 2 else width - 1
        prop_indices = sorted(
            i
            for i in range(width)
            if not _exclude_column_from_propositions(
                i, qi=qi, ri=ri, norms=norms, data_rows=data_rows
            )
        )
        if not prop_indices and ri > qi + 1:
            prop_indices = list(range(qi + 1, ri))[:QUIZ_MAX_OPTIONS]
    else:
        prop_indices = list(range(1, ri)) if ri > 1 else []

    if len(prop_indices) < 2:
        return []

    specs: list[dict] = []
    for row in data_rows:
        if not row or all(not (c or "").strip() for c in row):
            continue
        while len(row) < width:
            row.append("")
        qtext = _strip_question_number_prefix((row[qi] if qi < len(row) else "").strip())
        if not qtext:
            continue
        rep_cell = (row[ri] if ri < len(row) else "").strip()
        correct_idx = _parse_reponses_cell(rep_cell)
        texts = [(row[i] if i < len(row) else "").strip() for i in prop_indices]
        if len(texts) < 2 or not all(texts):
            continue
        qnum = _parse_ordre_cell(row[0]) if qi != 0 and _column_data_looks_like_ordre_index(data_rows, 0) else None
        specs.append(_spec_with_number(qtext, texts, correct_idx, qnum))

    return specs


def matrix_rows_to_question_specs(rows: list[list[str]]) -> list[dict]:
    """
    Interprète une matrice : ligne 0 = en-têtes (cas tableur), puis lignes de questions.

    Colonne « question » (ou 1re colonne), colonnes propositions, colonne « réponses »
    (ou dernière colonne). Si aucune question n’est trouvée, réessaie en traitant
    toutes les lignes comme données (PDF sans ligne d’en-tête textuelle).
    """
    rows = _rectangularize_rows(_normalize_matrix_rows(rows))
    if not rows:
        return []
    oqr = _try_ordre_question_reponse_table(rows)
    if oqr:
        return oqr
    specs = _matrix_rows_to_question_specs_with_header(rows, skip_header=True)
    if specs:
        return _finalize_quiz_specs(specs)
    specs = _matrix_rows_to_question_specs_with_header(rows, skip_header=False)
    if specs:
        return _finalize_quiz_specs(specs)
    ri = _detect_answer_column_index(rows)
    if ri is not None and ri > 0:
        alt = _matrix_rows_to_question_specs_with_columns(rows, qi=0, ri=ri)
        if alt:
            return _finalize_quiz_specs(alt)
    if len(rows) >= 2:
        body = rows[1:]
        ri2 = _detect_answer_column_index(body)
        if ri2 is not None and ri2 > 0:
            alt2 = _matrix_rows_to_question_specs_with_columns(body, qi=0, ri=ri2)
            if alt2:
                return _finalize_quiz_specs(alt2)
    return []


def _matrix_rows_to_question_specs_with_columns(
    rows: list[list[str]], *, qi: int, ri: int
) -> list[dict]:
    """Construit les questions en fixant explicitement les indices question / réponses."""
    if not rows or len(rows) < 1:
        return []
    width = max((len(r) for r in rows), default=0)
    if width < 3 or ri >= width or qi >= width or qi == ri:
        return []
    prop_indices = sorted(
        i
        for i in range(width)
        if not _exclude_column_from_propositions(i, qi=qi, ri=ri, norms=[], data_rows=rows)
    )
    if len(prop_indices) < 2:
        return []
    specs: list[dict] = []
    for row in rows:
        if not row or all(not (c or "").strip() for c in row):
            continue
        while len(row) < width:
            row.append("")
        qtext = _strip_question_number_prefix((row[qi] if qi < len(row) else "").strip())
        if not qtext:
            continue
        rep_cell = (row[ri] if ri < len(row) else "").strip()
        correct_idx = _parse_reponses_cell(rep_cell)
        texts = [(row[i] if i < len(row) else "").strip() for i in prop_indices]
        if len(texts) < 2 or not all(texts):
            continue
        qnum = _parse_ordre_cell(row[0]) if qi != 0 and _column_data_looks_like_ordre_index(rows, 0) else None
        specs.append(_spec_with_number(qtext, texts, correct_idx, qnum))
    return specs


def _clip(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def apply_question_specs_to_quiz(
    quiz,
    specs: list[dict],
    *,
    question_model=None,
    option_model=None,
    quiz_fk_field: str = "quiz",
) -> tuple[int, int]:
    """Remplace toutes les questions du quiz. Retourne (lignes, nombre_questions)."""
    from .models import ExamQuizOption, ExamQuizQuestion, QuizOption, QuizQuestion
    import logging
    logger = logging.getLogger(__name__)

    if question_model is None:
        question_model = QuizQuestion
    if option_model is None:
        option_model = QuizOption

    specs = _finalize_quiz_specs(specs)
    logger.info(f"Spécifications initiales : {len(specs)} questions")

    quiz.questions.all().delete()
    n_questions = 0
    for i, spec in enumerate(specs, start=1):
        spec = _sanitize_question_spec_dict(spec)
        spec_num = spec.get("number")
        spec_texts = len(spec.get("texts") or [])
        spec_prompt = (spec.get("prompt") or "")[:50]
        if spec_texts < 2:
            logger.warning(f"Question #{spec_num} sautée : pas assez d'options ({spec_texts}) - prompt : {spec_prompt}")
            continue
        prompt = _clip(_normalize_stem_text(spec["prompt"]), 4000)
        qnum = spec["number"]
        logger.info(f"Création question #{qnum} avec {spec_texts} options")
        qq = question_model.objects.create(
            **{quiz_fk_field: quiz},
            order=qnum - 1,
            prompt=prompt,
        )
        n_questions += 1
        correct = set(spec["correct"])
        for j, t in enumerate(spec["texts"], start=1):
            option_model.objects.create(
                question=qq,
                order=j - 1,
                text=_clip(strip_nb_references(t), 500),
                is_correct=j in correct,
            )
    logger.info(f"Fin : {len(specs)} specs, {n_questions} questions créées")
    return len(specs), n_questions


def import_quiz_from_csv(
    quiz,
    fileobj: BinaryIO,
    *,
    question_model=None,
    option_model=None,
    quiz_fk_field: str = "quiz",
) -> tuple[int, int]:
    """
    Remplace les questions du quiz par le contenu d’un fichier CSV.

    Même logique de colonnes qu’à l’export d’un tableau depuis le PDF :
    question, propositions…, colonne réponses (indices 1,2,3… ou A,B… ; plusieurs : 1,3).
    """
    raw = fileobj.read()
    if isinstance(raw, str):
        text = raw
    else:
        text = raw.decode("utf-8-sig")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.reader(io.StringIO(text), dialect)
    raw_rows = list(reader)
    specs = matrix_rows_to_question_specs(raw_rows)
    return apply_question_specs_to_quiz(
        quiz,
        specs,
        question_model=question_model,
        option_model=option_model,
        quiz_fk_field=quiz_fk_field,
    )
