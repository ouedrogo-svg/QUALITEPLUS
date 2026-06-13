"""Extraction des tableaux d’un PDF de correction pour alimenter le quiz."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections import defaultdict

from django.core.cache import cache

from .quiz_import import (
    _block_part_fingerprint,
    _content_column_indices,
    _enrich_spec_with_continuation,
    _finalize_quiz_specs,
    _first_ordre_row_index,
    _looks_like_option_line,
    _normalize_matrix_rows,
    _parse_ordre_cell,
    _parse_ordre_from_row,
    _rep_cell_from_row,
    _row_merged_content,
    _score_correction_table_rows,
    _spec_is_plausible,
    _spec_richness,
    _table_correction_layout,
    _table_has_option_rows,
    _try_spec_from_wide_correction_row,
    _valid_question_number,
    apply_question_specs_to_quiz,
    matrix_rows_to_question_specs,
    specs_from_correction_table_rows,
)

logger = logging.getLogger(__name__)

# Réglages pdfplumber : lignes / texte, tolérances (snap/join), mots minimum par arête.
# Les corrigés académiques varient beaucoup ; on enchaîne plusieurs profils.
_TABLE_EXTRACT_PRESETS: tuple[dict, ...] = (
    {},
    {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
    {"vertical_strategy": "lines", "horizontal_strategy": "lines", "snap_tolerance": 2, "join_tolerance": 2},
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 6,
        "join_tolerance": 6,
        "min_words_vertical": 1,
        "min_words_horizontal": 1,
        "edge_min_length": 2,
    },
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 10,
        "join_tolerance": 10,
        "min_words_vertical": 1,
        "min_words_horizontal": 1,
    },
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "text_x_tolerance": 5,
        "text_y_tolerance": 5,
    },
    {"vertical_strategy": "text", "horizontal_strategy": "text"},
    {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "min_words_vertical": 1,
        "min_words_horizontal": 1,
    },
    {"vertical_strategy": "lines", "horizontal_strategy": "text", "snap_tolerance": 5, "join_tolerance": 5},
    {"vertical_strategy": "text", "horizontal_strategy": "lines", "snap_tolerance": 5, "join_tolerance": 5},
)


def _merge_words_line_to_cells(line_ws: list[dict], x_gap: float) -> list[str]:
    """Regroupe les mots d’une même ligne en « cellules » selon l’espace horizontal."""
    if not line_ws:
        return []
    parts: list[str] = [str(line_ws[0].get("text") or "").strip()]
    cur_right = float(line_ws[0]["x1"])
    for w in line_ws[1:]:
        x0 = float(w["x0"])
        if x0 - cur_right > x_gap:
            parts.append(str(w.get("text") or "").strip())
        else:
            parts[-1] = (parts[-1] + " " + str(w.get("text") or "").strip()).strip()
        cur_right = max(cur_right, float(w["x1"]))
    return [p for p in parts if p]


def _words_cluster_matrix_from_page(page, x_gap: float) -> list[list[str]] | None:
    """
    Secours quand extract_tables produit peu : reconstruit des lignes type tableau
    à partir des positions des mots (QCM souvent alignés en colonnes).
    """
    try:
        words = page.extract_words(keep_blank_chars=False)
    except TypeError:
        words = page.extract_words()
    except Exception:
        return None
    if not words:
        return None
    by_y: dict[float, list[dict]] = defaultdict(list)
    for w in words:
        yk = round(float(w["top"]) / 2.5) * 2.5
        by_y[yk].append(w)
    rows_out: list[list[str]] = []
    for yk in sorted(by_y.keys()):
        line = sorted(by_y[yk], key=lambda z: float(z["x0"]))
        cells = _merge_words_line_to_cells(line, x_gap)
        if len(cells) >= 3:
            rows_out.append(cells)
    if len(rows_out) < 2:
        return None
    return rows_out


def _iter_raw_tables_from_pdf(path: str):
    """Itère des matrices (lignes de cellules) issues du PDF, sans doublons évidents."""
    import pdfplumber

    seen_fp: set[int] = set()

    def _emit_normalized(norm: list[list[str]]):
        if len(norm) < 2:
            return
        fp = hash(tuple(tuple(r[:12]) for r in norm[:10]))
        if fp in seen_fp:
            return
        seen_fp.add(fp)
        yield norm

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for settings in _TABLE_EXTRACT_PRESETS:
                try:
                    if settings:
                        raw_tables = page.extract_tables(table_settings=settings) or []
                    else:
                        raw_tables = page.extract_tables() or []
                except TypeError:
                    raw_tables = page.extract_tables() or []
                except Exception:
                    logger.debug("extract_tables a échoué pour un réglage", exc_info=True)
                    continue
                for raw in raw_tables:
                    norm = _normalize_matrix_rows(raw)
                    yield from _emit_normalized(norm)

            for gap in (8.0, 12.0, 18.0, 26.0, 36.0):
                pseudo = _words_cluster_matrix_from_page(page, gap)
                if pseudo:
                    norm = _normalize_matrix_rows(pseudo)
                    yield from _emit_normalized(norm)


def _append_rows_skip_page_duplicates(
    consolidated: list[list[str]],
    new_rows: list[list[str]],
    *,
    i_o: int,
    i_r: int,
) -> None:
    """
    Évite de répéter la toute dernière ligne en tête de page suivante
    (coupure PDF), sans supprimer des propositions identiques entre deux questions.
    """
    if not new_rows:
        return

    def _row_fp(row: list[str]) -> str:
        cc = _content_column_indices(i_o, i_r, len(row))
        return _block_part_fingerprint(_row_merged_content(row, cc))

    for r in new_rows:
        if _parse_ordre_from_row(r, i_o) is not None:
            consolidated.append(r)
            continue
        fp = _row_fp(r)
        if consolidated and fp:
            last = consolidated[-1]
            if _parse_ordre_from_row(last, i_o) is None and _row_fp(last) == fp:
                continue
        consolidated.append(r)


def _consolidated_correction_rows_from_pdf(path: str) -> list[list[str]]:
    """
    Sur chaque page, concatène les lignes de tous les tableaux utiles.
    Utilise plusieurs stratégies d'extraction pour ne pas rater les fragments sans bordures.
    """
    import pdfplumber

    consolidated: list[list[str]] = []
    layout_cols: tuple[int, int] | None = None
    
    try:
        with pdfplumber.open(path) as pdf:
            logger.info(f"[PDF] Ouverture du PDF, {len(pdf.pages)} pages")
            for page_num, page in enumerate(pdf.pages, start=1):
                page_chunks: list[list[str]] = []
                logger.info(f"[PDF] Traitement de la page {page_num}")
                
                # On essaie d'abord l'extraction standard
                raw_tables = page.extract_tables() or []
                logger.info(f"[PDF] Page {page_num}: {len(raw_tables)} tableaux extraits standard")
                
                # Si rien n'est trouvé, on essaie des stratégies plus agressives
                if not raw_tables:
                    for settings in _TABLE_EXTRACT_PRESETS[1:4]: # Quelques presets de base
                        raw_tables = page.extract_tables(table_settings=settings) or []
                        if raw_tables:
                            logger.info(f"[PDF] Page {page_num}: {len(raw_tables)} tableaux extraits avec preset")
                            break
                            
                # En dernier recours, clustering de mots
                if not raw_tables:
                    pseudo = _words_cluster_matrix_from_page(page, 12.0)
                    if pseudo:
                        raw_tables = [pseudo]
                        logger.info(f"[PDF] Page {page_num}: 1 tableau extrait avec clustering de mots")

                for raw_idx, raw in enumerate(raw_tables):
                    rows = _normalize_matrix_rows(raw)
                    if not rows:
                        logger.info(f"[PDF] Page {page_num}: tableau {raw_idx} vide après normalisation")
                        continue
                    layout = _table_correction_layout(rows)
                    if layout:
                        i_o, i_r, data_start = layout
                        layout_cols = (i_o, i_r)
                        logger.info(f"[PDF] Page {page_num}: tableau {raw_idx} a un layout valide (i_o={i_o}, i_r={i_r})")
                        first_ordre = _first_ordre_row_index(rows)
                        if first_ordre and first_ordre > 0:
                            page_chunks.append(rows[:first_ordre])
                        page_chunks.append(rows[data_start:])
                    elif _table_has_option_rows(rows):
                        logger.info(f"[PDF] Page {page_num}: tableau {raw_idx} a des lignes d'options")
                        page_chunks.append(rows)
                    elif layout_cols and len(rows[0]) >= layout_cols[1] + 1:
                        # Tableau sans N° ni options explicites, mais largeur compatible
                        if any(any((c or "").strip() for c in r) for r in rows):
                            logger.info(f"[PDF] Page {page_num}: tableau {raw_idx} ajouté (largeur compatible)")
                            page_chunks.append(rows)
                            
                if not page_chunks:
                     logger.info(f"[PDF] Page {page_num}: pas de chunks trouvés")
                     # Si aucun tableau n'est trouvé mais qu'on a du texte "libre", 
                     # on tente d'extraire les lignes significatives.
                     txt = page.extract_text()
                     if txt and layout_cols:
                         lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
                         for ln in lines:
                             # On ignore les lignes trop courtes ou qui ressemblent à des entêtes
                             if len(ln) < 10 and not _parse_ordre_cell(ln):
                                 continue
                             if "page" in ln.lower() or "session" in ln.lower():
                                 continue
                                 
                             i_o, i_r = layout_cols
                             dummy_row = [""] * (max(i_o, i_r) + 1)
                             i_q = i_o + 1 if i_o + 1 < i_r else i_o
                             if i_q < len(dummy_row):
                                 dummy_row[i_q] = ln
                                 page_chunks.append([dummy_row])
                                 logger.info(f"[PDF] Page {page_num}: ajout ligne libre: {repr(ln)}")

                if not page_chunks:
                    continue
                    
                i_o, i_r = layout_cols or (0, max(len(r) for r in page_chunks[0]) - 1)
                logger.info(f"[PDF] Page {page_num}: ajout de {len(page_chunks)} chunks")
                for chunk in page_chunks:
                    _append_rows_skip_page_duplicates(consolidated, chunk, i_o=i_o, i_r=i_r)
        logger.info(f"[PDF] Consolidation terminée: {len(consolidated)} lignes totales")
    except Exception:
        logger.exception("Consolidation lignes corrigé impossible")
        return []
    return consolidated


def _extract_questions_from_plain_text(text: str) -> list[dict]:
    """Extraire les questions depuis du texte brute (si les tableaux ne sont pas détectés)."""
    from .quiz_import import (
        _parse_reponses_cell, 
        _spec_with_number, 
        _valid_question_number,
    )
    
    specs = []
    # Séparer le texte en blocs par "Question X"
    question_blocks = re.split(r"(?i)Question\s*\d+", text)
    # Récupérer les numéros de question
    question_numbers = re.findall(r"(?i)Question\s*(\d+)", text)
    
    if not question_blocks or not question_numbers:
        return []
    
    # On saute le premier bloc (vide avant la première question)
    for i, block in enumerate(question_blocks[1:], start=0):
        if i >= len(question_numbers):
            break
        
        q_num = int(question_numbers[i])
        if not _valid_question_number(q_num):
            continue
            
        block = block.strip()
        if not block:
            continue
            
        # Extraire les options (A), B), ..., Z), 1), 2), ...)
        option_matches = list(re.finditer(
            r"(?m)^[\t ]*([A-Za-z0-9]+)[\)\.\:]+\s*(.*?)(?=(?:^[\t ]*[A-Za-z0-9]+[\)\.\:])|$)",
            block,
            re.DOTALL
        ))
        
        if len(option_matches) < 2:
            # Essayer une autre regex pour les options avec parenthèses ou espacées
            option_matches = list(re.finditer(
                r"(?m)^[\t ]*([A-Za-z0-9]+)[\)\.\:]\s*(.*?)(?=\n\n|\n[A-Za-z0-9]+[\)\.\:]|$)",
                block,
                re.DOTALL
            ))
            if len(option_matches) < 2:
                continue
                
        # Récupérer l'énoncé (tout ce qui est avant la première option)
        first_option_start = option_matches[0].start()
        stem = block[:first_option_start].strip()
        stem = re.sub(r"^\s*:\s*", "", stem)  # Supprimer les deux-points au début
        
        if not stem:
            # Si pas d'énoncé, prendre la première phrase
            first_line = block.splitlines()[0]
            stem = re.sub(r"^[\t ]*[A-Za-z0-9]+[\)\.\:]", "", first_line).strip()
        
        # Extraire les textes des options
        options = []
        for match in option_matches:
            option_text = match.group(2).strip() if len(match.groups()) > 1 else ""
            if not option_text:
                option_text = match.group(0).strip()
                option_text = re.sub(r"^[\t ]*[A-Za-z0-9]+[\)\.\:]\s*", "", option_text)
            option_text = re.sub(r"\s+", " ", option_text)  # Normaliser les espaces
            if option_text:
                options.append(option_text)
        
        if len(options) < 2:
            continue
            
        # Essayer de trouver la réponse correcte (si elle est dans le texte)
        correct = []
        # Chercher des marqueurs comme "Réponse: C" ou "Correct: A, B"
        answer_markers = [
            r"(?i)(?:R[ée]ponse|Correct|Vrai)[\s\:]*([A-Za-z0-9\s\,\;]+)",
            r"(?i)(?:Réponses|Corrects)[\s\:]*([A-Za-z0-9\s\,\;]+)",
        ]
        
        for marker in answer_markers:
            answer_match = re.search(marker, block)
            if answer_match:
                answer_str = answer_match.group(1).strip()
                correct = _parse_reponses_cell(answer_str)
                if correct:
                    break
        
        # Si pas de réponse trouvée, on laisse vide
        specs.append(_spec_with_number(stem, options, correct, q_num))
    
    return specs


def _score_quiz_specs(specs: list[dict]) -> tuple[int, int, int]:
    """Plus haut = mieux : couverture des N°, puis nombre de questions, puis max N°."""
    if not specs:
        return (0, 0, 0)
    numbers = {s["number"] for s in specs if _valid_question_number(s.get("number"))}
    coverage = len(numbers)
    n = len(specs)
    max_n = max(numbers) if numbers else 0
    return (coverage, n, max_n)


def best_question_specs_from_correction_pdf(path: str) -> list[dict]:
    """
    Extraction conforme au PDF : fusionne toutes les sources (pages + tableaux),
    une entrée par numéro d’ordre du PDF (y compris au-delà de 60) pour ne pas perdre de questions.
    """
    try:
        by_number: dict[int, dict] = {}

        def absorb(specs: list[dict], *, allow_incomplete: bool = False) -> None:
            for spec in _finalize_quiz_specs(specs):
                n = spec.get("number")
                if not _valid_question_number(n) or not (spec.get("prompt") or "").strip():
                    continue
                if not allow_incomplete and not _spec_is_plausible(spec):
                    continue
                if n not in by_number or _spec_richness(spec) > _spec_richness(by_number[n]):
                    logger.info(f"Absorbant question #{n} (options : {len(spec.get('texts', []))}, prompt : {spec.get('prompt','')[:50]})")
                    by_number[n] = spec

        # 1. Essayer d'abord avec les tableaux (comme avant)
        data_rows = _consolidated_correction_rows_from_pdf(path)
        if data_rows:
            absorb(specs_from_correction_table_rows(data_rows))

        last_ordre: int | None = max(by_number.keys()) if by_number else None
        logger.info(f"Après consolidation initiale : {len(by_number)} questions")
        
        for rows in _iter_raw_tables_from_pdf(path):
            layout = _table_correction_layout(rows)
            if not layout:
                continue
            i_o, i_r, _data_start = layout
            width = max(len(r) for r in rows)
            content_cols = [j for j in range(i_o + 1, i_r)]
            if not content_cols:
                content_cols = [min(i_o + 1, width - 1)]

            for r in rows:
                n_row = _parse_ordre_from_row(r, i_o)
                if n_row and n_row not in by_number:
                    wide = _try_spec_from_wide_correction_row(r)
                    if wide:
                        absorb([wide], allow_incomplete=True)

            first_ordre_i = _first_ordre_row_index(rows)
            if first_ordre_i is None:
                continue

            first_ordre_n = _parse_ordre_from_row(rows[first_ordre_i], i_o)

            # Lignes avant le N° d'ordre = suite de la question précédente
            # OU début de la question courante (quand le contenu commence en fin
            # de page précédente et le numéro n'apparaît qu'en haut de la suivante).
            if first_ordre_i > 0 and first_ordre_n:
                lead_parts: list[str] = []
                for r in rows[:first_ordre_i]:
                    row_cc = _content_column_indices(i_o, i_r, len(r))
                    chunk = _row_merged_content(r, row_cc or content_cols)
                    if chunk and not re.match(r"^\s*NB\s*:", chunk, flags=re.IGNORECASE):
                        lead_parts.append(chunk)
                if lead_parts and len(lead_parts) <= 12:
                    applied = False
                    # Essai 1 : enrichir la question précédente (cas classique)
                    prev_n = first_ordre_n - 1
                    if _valid_question_number(prev_n) and prev_n in by_number:
                        prev_prompt = (by_number[prev_n].get("prompt") or "").strip()
                        prev_complete = (
                            len(by_number[prev_n].get("texts") or []) >= 4
                            and len(prev_prompt) >= 25
                            and (prev_prompt.endswith("?") or prev_prompt.endswith(":"))
                        )
                        if not prev_complete:
                            enriched = _enrich_spec_with_continuation(
                                by_number[prev_n], lead_parts
                            )
                            if (
                                _spec_is_plausible(enriched)
                                and _spec_richness(enriched) > _spec_richness(by_number[prev_n])
                            ):
                                logger.info(f"Enrichissant question #{prev_n} avec {len(lead_parts)} lignes")
                                by_number[prev_n] = enriched
                                applied = True
                    # Essai 2 : prépendre au contenu de la question courante
                    # (le contenu commence en bas de la page précédente, le N° est ici)
                    if not applied and first_ordre_n in by_number:
                        current_prompt = (by_number[first_ordre_n].get("prompt") or "").strip()
                        current_needs_prefix = (
                            not current_prompt
                            or current_prompt == "Question"
                            or len(current_prompt) < 25
                            or _looks_like_option_line(current_prompt)
                        )
                        if current_needs_prefix:
                            enriched = _enrich_spec_with_continuation(
                                by_number[first_ordre_n], lead_parts, prepend=True
                            )
                            if _spec_richness(enriched) > _spec_richness(by_number[first_ordre_n]):
                                logger.info(f"Enrichissant (préfixe) question #{first_ordre_n} avec {len(lead_parts)} lignes")
                                by_number[first_ordre_n] = enriched
                    elif not applied and first_ordre_n not in by_number:
                        # La question n'existe pas encore — on la créera plus tard
                        # avec le tableau complet ; on injecte les lignes de tête
                        # dans le bloc courant comme amorce.
                        pass

            # Petit tableau isolé (ex. question 60 seule) non capté par la consolidation
            if len(rows) <= 12 and first_ordre_n:
                specs = specs_from_correction_table_rows(rows)
                if not specs:
                    specs = _finalize_quiz_specs(matrix_rows_to_question_specs(rows))
                absorb(specs)

            if by_number:
                last_ordre = max(by_number.keys())

        # 2. Si pas de questions ou pas assez, essayer l'extraction texte brute (fallback)
        if len(by_number) < 10:
            import pdfplumber
            logger.info("Tentative d'extraction depuis le texte brute (fallback)...")
            
            try:
                with pdfplumber.open(path) as pdf:
                    full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
                    plain_text_specs = _extract_questions_from_plain_text(full_text)
                    absorb(plain_text_specs, allow_incomplete=True)
                    logger.info(f"Fallback extrait {len(plain_text_specs)} questions")
            except Exception as e:
                logger.exception(f"Erreur lors de l'extraction fallback : {e}")

        logger.info(f"Avant plausibilité : {len(by_number)} questions")
        
        by_number = {
            n: s for n, s in by_number.items() if _spec_is_plausible(s)
        }
        
        logger.info(f"Après plausibilité : {len(by_number)} questions")
        logger.info(f"Numéros de questions : {sorted(by_number.keys())}")
        
        return [by_number[i] for i in sorted(by_number.keys())]
    except Exception:
        logger.exception("Lecture PDF pour quiz impossible : %s", path)
        return []




def _resolve_pdf_to_local_path(pdf_field):
    """
    Retourne un chemin local vers le PDF.
    - FileSystemStorage : retourne directement .path
    - Cloudinary / stockage distant : telecharge dans un fichier temporaire.
    Retourne None si impossible.
    """
    try:
        return pdf_field.path
    except (ValueError, NotImplementedError, AttributeError):
        pass
    # Stockage distant : telecharger via l'URL
    try:
        url = pdf_field.url
    except Exception:
        return None
    if not url or not url.startswith('http'):
        return None
    try:
        import requests
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception:
        logger.warning('Impossible de telecharger le PDF distant : %s', url)
        return None
    suffix = os.path.splitext(pdf_field.name)[1] or '.pdf'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content)
    tmp.close()
    return tmp.name


def _cleanup_temp_pdf(path, pdf_field):
    """Supprime le fichier temporaire si c'etait un telechargement distant."""
    try:
        local = pdf_field.path
        if local == path:
            return
    except (ValueError, NotImplementedError, AttributeError):
        pass
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def import_quiz_from_pdf_document(
    quiz,
    document,
    *,
    quiz_model,
    question_model=None,
    option_model=None,
    quiz_fk_field: str = "quiz",
) -> int:
    """
    Reconstruit le quiz à partir du PDF (correction ou examen).
    Retourne le nombre de questions créées (0 si aucun tableau exploitable).
    """
    n = 0
    if not document.pdf:
        return 0
    path = _resolve_pdf_to_local_path(document.pdf)
    if path is None:
        logger.warning("Impossible d'obtenir un chemin local pour le PDF.")
        return 0
    try:
        try:
            specs = best_question_specs_from_correction_pdf(path)
            if specs:
                _, n = apply_question_specs_to_quiz(
                    quiz,
                    specs,
                    question_model=question_model,
                    option_model=option_model,
                    quiz_fk_field=quiz_fk_field,
                )
            else:
                n = quiz.questions.count()
        finally:
            _cleanup_temp_pdf(path, document.pdf)
    except Exception:
        logger.exception("Erreur lors de l'analyse ou de l'import du quiz depuis le PDF")
        n = 0
    finally:
        quiz_model.objects.filter(pk=quiz.pk).update(
            quiz_last_built_for_pdf_key=document.pdf.name
        )
    return n


def import_quiz_from_correction_pdf(quiz, correction) -> int:
    from .models import CorrectionQuiz

    return import_quiz_from_pdf_document(quiz, correction, quiz_model=CorrectionQuiz)


def import_quiz_from_exam_pdf(quiz, exam) -> int:
    from .models import ExamQuiz, ExamQuizOption, ExamQuizQuestion

    return import_quiz_from_pdf_document(
        quiz,
        exam,
        quiz_model=ExamQuiz,
        question_model=ExamQuizQuestion,
        option_model=ExamQuizOption,
        quiz_fk_field="exam_quiz",
    )


def sync_quiz_after_correction_saved(
    correction, *, force: bool = False
) -> tuple[int, str | None]:
    """
    À appeler une fois la correction (et l’inline quiz) enregistrées.
    Retourne (nombre_de_questions, message_erreur_éventuel — toujours None si pas d’exception globale).
    """
    from .models import CorrectionQuiz

    if not correction.pdf:
        return 0, None
    quiz, _ = CorrectionQuiz.objects.get_or_create(correction=correction, defaults={})
    pdf_key = correction.pdf.name
    if not force and pdf_key and quiz.quiz_last_built_for_pdf_key == pdf_key:
        n_existing = quiz.questions.count()
        if n_existing > 0:
            return n_existing, None
    n = import_quiz_from_correction_pdf(quiz, correction)
    return n, None


def force_rebuild_quiz_from_correction_pdf(correction) -> int:
    """Action admin : oublie la synchro et relit le PDF."""
    from .models import CorrectionQuiz

    quiz, _ = CorrectionQuiz.objects.get_or_create(correction=correction, defaults={})
    CorrectionQuiz.objects.filter(pk=quiz.pk).update(quiz_last_built_for_pdf_key="")
    quiz.refresh_from_db()
    return import_quiz_from_correction_pdf(quiz, correction)


def _try_rebuild_quiz_for_document(
    document,
    *,
    quiz_model,
    parent_fk_name: str,
    force_rebuild_fn,
    cache_prefix: str,
) -> int:
    from django.db.models import Count

    quiz = (
        quiz_model.objects.filter(**{parent_fk_name: document})
        .annotate(n_questions=Count("questions", distinct=True))
        .first()
    )
    if not quiz:
        quiz, _ = quiz_model.objects.get_or_create(**{parent_fk_name: document}, defaults={})
        quiz.n_questions = 0
    n = quiz.n_questions
    if n > 0 or not document.pdf:
        return n
    path = _resolve_pdf_to_local_path(document.pdf)
    if path is None:
        return 0
    _cleanup_temp_pdf(path, document.pdf)
    cache_key = f"{cache_prefix}:{document.pk}:{document.pdf.name}"
    if cache.get(cache_key):
        return 0
    n_new = force_rebuild_fn(document)
    quiz.refresh_from_db()
    n = quiz.questions.count()
    if n_new == 0:
        cache.set(cache_key, 1, timeout=900)
    else:
        cache.delete(cache_key)
    return n


def sync_quiz_after_exam_saved(exam, *, force: bool = False) -> tuple[int, str | None]:
    from .models import ExamQuiz

    if not exam.pdf:
        return 0, None
    quiz, _ = ExamQuiz.objects.get_or_create(exam=exam, defaults={})
    pdf_key = exam.pdf.name
    if not force and pdf_key and quiz.quiz_last_built_for_pdf_key == pdf_key:
        n_existing = quiz.questions.count()
        if n_existing > 0:
            return n_existing, None
    n = import_quiz_from_exam_pdf(quiz, exam)
    return n, None


def force_rebuild_quiz_from_exam_pdf(exam) -> int:
    from .models import ExamQuiz

    quiz, _ = ExamQuiz.objects.get_or_create(exam=exam, defaults={})
    ExamQuiz.objects.filter(pk=quiz.pk).update(quiz_last_built_for_pdf_key="")
    quiz.refresh_from_db()
    return import_quiz_from_exam_pdf(quiz, exam)


def try_rebuild_quiz_for_correction(correction) -> int:
    from .models import CorrectionQuiz

    return _try_rebuild_quiz_for_document(
        correction,
        quiz_model=CorrectionQuiz,
        parent_fk_name="correction",
        force_rebuild_fn=force_rebuild_quiz_from_correction_pdf,
        cache_prefix="quiz_autobuild_fail",
    )


def try_rebuild_quiz_for_exam(exam) -> int:
    from .models import ExamQuiz

    return _try_rebuild_quiz_for_document(
        exam,
        quiz_model=ExamQuiz,
        parent_fk_name="exam",
        force_rebuild_fn=force_rebuild_quiz_from_exam_pdf,
        cache_prefix="exam_quiz_autobuild_fail",
    )
