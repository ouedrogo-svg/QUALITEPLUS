#!/usr/bin/env python
"""Test de la nouvelle version de nettoyage."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from courses.quiz_import_v2 import clean_pdf_text, is_header_line

test_cases = [
    {
        "name": "En-tête de table",
        "input": "Cont Prép Adm Adj Cons répo rdre Questions Les crédits ouverts",
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
        
        result = clean_pdf_text(case['input'])
        print(f"Output: {result[:60]}...")
        
        passed = True
        if 'should_contain' in case:
            for expected in case['should_contain']:
                if expected in result:
                    print(f"  ✓ Contient: '{expected}'")
                else:
                    print(f"  ✗ Manque: '{expected}'")
                    passed = False
        
        if 'should_not_contain' in case:
            for unwanted in case['should_not_contain']:
                if unwanted not in result:
                    print(f"  ✓ Ne contient pas: '{unwanted}'")
                else:
                    print(f"  ✗ Contient encore: '{unwanted}'")
                    passed = False
        
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ TOUS LES TESTS PASSENT")
    else:
        print("✗ CERTAINS TESTS ÉCHOUENT")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
