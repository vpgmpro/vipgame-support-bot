# tests.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from repository import FAQRepository
from search import SearchEngine

TESTS = [
    ("Привет", "greeting"),
    ("Как купить кристаллы?", "buy_crystals"),
    ("Что такое статус?", "what_is_status"),
    ("Где посмотреть свой статус?", "how_to_check_status"),
    ("Как зарегистрироваться?", "registration"),
    ("Забыл пароль", "forgot_password"),
    ("Можно ли иметь несколько аккаунтов?", "multiple_accounts"),
]

def run_tests():
    print("\n🧪 Запуск регрессионных тестов...")
    print("─" * 70)
    
    repo = FAQRepository("faq.json")
    search = SearchEngine(repo)
    
    passed = 0
    failed = 0
    errors = []
    
    for question, expected_slug in TESTS:
        result = search.find_best(question)
        got_slug = result.slug
        
        if got_slug == expected_slug:
            status = "✅"
            passed += 1
        else:
            status = "❌"
            failed += 1
            errors.append({'question': question, 'expected': expected_slug, 'got': got_slug, 'score': result.score})
        
        print(f"{status} {question[:35]:<35} → {got_slug} (score: {result.score:.2f})")
    
    print("─" * 70)
    print(f"\n📊 Результаты: ✅ {passed} | ❌ {failed}")
    
    if errors:
        print("\n📋 Ошибки:")
        for err in errors:
            print(f"  Вопрос: '{err['question']}' → ожидался {err['expected']}, получен {err['got']}")
    
    return passed, failed

if __name__ == "__main__":
    run_tests()
