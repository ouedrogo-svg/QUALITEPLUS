#!/usr/bin/env python
"""Test de la nouvelle version de nettoyage."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from courses.quiz_import import (
    _clean_fragmented_text as clean_pdf_text,
    _is_header_line as is_header_line,
    strip_nb_references,
)

test_cases = [
    {
        "name": "En-tête de table",
        "input": "Cont Prép\nAdj Cons\nLes crédits ouverts",
        "should_not_contain": ["Cont Prép", "Adj Cons"],
        "should_contain": ["Les crédits ouverts"],
    },
    {
        "name": "Mot avec espace inséré",
        "input": "Les crédits de personnel par ministè re sont assortis",
        "should_contain": ["ministère sont"],
    },
    {
        "name": "Fragment de mot collé",
        "input": "crédits de pa\niement (CP).",
        "should_contain": ["de paiement"],
    },
    {
        "name": "Économique fragmenté",
        "input": "nature économi\nque de dépenses",
        "should_contain": ["économique de"],
    },
    {
        "name": "Suppression NB multi-lignes",
        "input": "Le 30 janvier de l'année en cours\nNB : Page 31 de l'instruction N°2019, portant application de la\ncomptabilité générale de l'Etat",
        "use_strip_nb": True,
        "should_contain": ["Le 30 janvier de l'année en cours"],
        "should_not_contain": ["NB", "Page 31", "instruction", "comptabilité", "générale"],
    },
]

def run_tests():
    print("=" * 60)
    print("Test de la nouvelle version de nettoyage PDF")
    print("=" * 60)
    
    all_passed = True
    for case in test_cases:
        print(f"\n{case['name']}:")
        print("-" * 40)
        print(f"Input: {case['input'][:60]}...")
        
        fn = strip_nb_references if case.get("use_strip_nb") else clean_pdf_text
        result = fn(case['input'])
        print(f"Output: {result[:60]}...")
        
        passed = True
        if 'should_contain' in case:
            for expected in case['should_contain']:
                if expected in result:
                    print(f"  [OK] Contient: '{expected}'")
                else:
                    print(f"  [X] Manque: '{expected}'")
                    passed = False
        
        if 'should_not_contain' in case:
            for unwanted in case['should_not_contain']:
                if unwanted not in result:
                    print(f"  [OK] Ne contient pas: '{unwanted}'")
                else:
                    print(f"  [X] Contient encore: '{unwanted}'")
                    passed = False
        
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("[OK] TOUS LES TESTS PASSENT")
    else:
        print("[X] CERTAINS TESTS ECHOVENT")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
