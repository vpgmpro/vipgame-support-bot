# repository.py - НОВАЯ ВЕРСИЯ

import json
import logging
from typing import List, Optional
from config import FAQ_FILE
from models import FAQ

logger = logging.getLogger(__name__)

class FAQRepository:
    def __init__(self, file_path: str = FAQ_FILE):
        self.file_path = file_path
        self.faqs: List[FAQ] = []
        self.by_slug: dict = {}
        self.by_category: dict = {}
        self._load()
    
    def _load(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.faqs = []
                
                for item in data.get('faq', []):
                    faq = FAQ(
                        id=item['id'],
                        slug=item['slug'],
                        title=item.get('title', item['keywords'][0].capitalize()),
                        category=item.get('category', 'other'),
                        sort=item.get('sort', 0),
                        keywords=item.get('keywords', []),
                        answer=item.get('answer', '')
                    )
                    self.faqs.append(faq)
                
                # Кэшируем индексы
                self.by_slug = {faq.slug: faq for faq in self.faqs}
                self.by_category = {}
                for faq in self.faqs:
                    self.by_category.setdefault(faq.category, []).append(faq)
                for cat in self.by_category:
                    self.by_category[cat].sort(key=lambda x: x.sort)
                
                logger.info(f"✅ Загружено FAQ: {len(self.faqs)} записей")
        except Exception as e:
            logger.error(f"Ошибка загрузки FAQ: {e}")
            self.faqs = []
            self.by_slug = {}
            self.by_category = {}
    
    def reload(self):
        """Перезагружает данные из файла"""
        self._load()
    
    def all(self) -> List[FAQ]:
        return self.faqs
    
    def by_slug(self, slug: str) -> Optional[FAQ]:
        return self.by_slug.get(slug)
    
    def by_category(self, category: str) -> List[FAQ]:
        return self.by_category.get(category, [])
    
    def categories(self) -> dict:
        return self.by_category
    
    def search(self, query: str) -> List[FAQ]:
        query_lower = query.lower().strip()
        if not query_lower:
            return []
        results = []
        for faq in self.faqs:
            if query_lower in faq.title.lower():
                results.append(faq)
                continue
            for kw in faq.keywords:
                if query_lower in kw.lower():
                    results.append(faq)
                    break
        return results
