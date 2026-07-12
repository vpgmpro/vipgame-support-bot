# repository.py
import json
import logging
from typing import List, Optional, Dict
from models import FAQ

logger = logging.getLogger(__name__)

class FAQRepository:
    def __init__(self, file_path: str = "faq.json"):
        self.file_path = file_path
        self.faqs: List[FAQ] = []
        self.by_slug: Dict[str, FAQ] = {}
        self.by_id: Dict[int, FAQ] = {}
        self._load()
    
    def _load(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.faqs = []
                seen_slugs = set()
                
                for item in data.get('faq', []):
                    if 'slug' not in item or not item['slug']:
                        raise ValueError(f"FAQ #{item.get('id')} не имеет slug")
                    
                    slug = item['slug']
                    if slug in seen_slugs:
                        raise ValueError(f"Дубликат slug: {slug}")
                    seen_slugs.add(slug)
                    
                    faq = FAQ(
                        id=item['id'],
                        slug=slug,
                        keywords=item.get('keywords', []),
                        answer=item.get('answer', '')
                    )
                    self.faqs.append(faq)
                
                self.by_slug = {faq.slug: faq for faq in self.faqs}
                self.by_id = {faq.id: faq for faq in self.faqs}
                logger.info(f"✅ Загружено FAQ: {len(self.faqs)} записей")
        except Exception as e:
            logger.error(f"Ошибка загрузки FAQ: {e}")
            raise
    
    def get_by_slug(self, slug: str) -> Optional[FAQ]:
        return self.by_slug.get(slug)
    
    def get_by_id(self, id: int) -> Optional[FAQ]:
        return self.by_id.get(id)
    
    def all(self) -> List[FAQ]:
        return self.faqs
    
    def invalidate(self):
        self._load()
