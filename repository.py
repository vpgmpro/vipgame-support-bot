import json
import logging
import re
from typing import List, Optional, Set, Tuple, Dict, Any
from dataclasses import dataclass
from config import (
    FAQ_FILE,
    STOP_WORDS,
    SCORE_TITLE_MATCH,
    SCORE_ALIASES_MATCH,
    SCORE_KEYWORD_MATCH,
    EXACT_TITLE_BONUS,
    EXACT_ALIASES_BONUS,
    EXACT_KEYWORD_BONUS,
    MIN_SCORE,
    STRICT_MODE,
    VALID_CATEGORIES
)
from models import FAQ

logger = logging.getLogger(__name__)


@dataclass
class FAQIndex:
    """Индекс для одного FAQ, содержащий все предобработанные данные."""
    faq: FAQ
    title_clean: str
    title_words: Set[str]
    keyword_clean_list: List[str]
    keyword_words: Set[str]
    alias_clean_list: List[str]
    alias_words: Set[str]


class FAQRepository:
    def __init__(self, file_path: str = FAQ_FILE):
        self.file_path = file_path
        self.faqs: List[FAQ] = []
        self.indexes: List[FAQIndex] = []
        self._by_slug: Dict[str, FAQ] = {}
        self._by_category: Dict[str, List[FAQ]] = {}
        self._load()
    
    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===
    
    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.lower()
        text = text.replace("ё", "е")
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_words(self, text: str) -> Set[str]:
        if not text:
            return set()
        words = text.split()
        return {w for w in words if len(w) > 2 and w not in STOP_WORDS}
    
    def _validate_faq_item(self, item: Dict[str, Any], index: int) -> bool:
        """Проверяет корректность записи FAQ. Возвращает True, если запись валидна."""
        # Обязательные поля – теперь category и sort тоже обязательны
        required = ['id', 'slug', 'title', 'category', 'sort', 'keywords', 'answer']
        for field in required:
            if field not in item:
                logger.error(f"❌ FAQ #{index}: отсутствует поле '{field}'")
                return False
        
        # Проверка id
        if not isinstance(item['id'], int) or item['id'] <= 0:
            logger.error(f"❌ FAQ #{index}: 'id' должен быть положительным целым числом")
            return False
        
        # Проверка slug
        if not isinstance(item['slug'], str) or not item['slug']:
            logger.error(f"❌ FAQ #{index}: 'slug' должен быть непустой строкой")
            return False
        
        # Проверка title
        if not isinstance(item['title'], str) or not item['title']:
            logger.error(f"❌ FAQ #{index}: 'title' должен быть непустой строкой")
            return False
        
        # Проверка category
        if item['category'] not in VALID_CATEGORIES:
            logger.error(f"❌ FAQ #{index}: недопустимая категория '{item['category']}' (допустимые: {VALID_CATEGORIES})")
            return False
        
        # Проверка sort
        if not isinstance(item['sort'], int) or item['sort'] < 0:
            logger.error(f"❌ FAQ #{index}: 'sort' должен быть неотрицательным целым числом")
            return False
        
        # Проверка keywords – каждый элемент должен быть непустой строкой
        if not isinstance(item['keywords'], list) or not item['keywords']:
            logger.error(f"❌ FAQ #{index}: 'keywords' должен быть непустым списком")
            return False
        for kw in item['keywords']:
            if not isinstance(kw, str) or not kw.strip():
                logger.error(f"❌ FAQ #{index}: элемент 'keywords' должен быть непустой строкой")
                return False
        
        # Проверка answer
        if not isinstance(item['answer'], str) or not item['answer']:
            logger.error(f"❌ FAQ #{index}: 'answer' должен быть непустой строкой")
            return False
        
        # Проверка aliases (опционально, но если есть – каждый элемент должен быть строкой)
        if 'aliases' in item:
            if not isinstance(item['aliases'], list):
                logger.error(f"❌ FAQ #{index}: 'aliases' должен быть списком")
                return False
            for alias in item['aliases']:
                if not isinstance(alias, str) or not alias.strip():
                    logger.error(f"❌ FAQ #{index}: каждый элемент 'aliases' должен быть непустой строкой")
                    return False
        
        return True
    
    def _build_index(self, item: Dict[str, Any]) -> FAQIndex:
        """Создаёт объект FAQIndex из сырых данных."""
        faq = FAQ(
            id=item['id'],
            slug=item['slug'],
            title=item['title'],
            category=item['category'],
            sort=item['sort'],
            keywords=item['keywords'],
            answer=item['answer'],
            aliases=item.get('aliases', [])
        )
        
        title_clean = self._clean_text(faq.title)
        title_words = self._extract_words(title_clean)
        
        keyword_clean_list = [self._clean_text(kw) for kw in faq.keywords]
        keyword_words = set()
        for kw_clean in keyword_clean_list:
            keyword_words.update(self._extract_words(kw_clean))
        
        alias_clean_list = [self._clean_text(al) for al in faq.aliases]
        alias_words = set()
        for al_clean in alias_clean_list:
            alias_words.update(self._extract_words(al_clean))
        
        return FAQIndex(
            faq=faq,
            title_clean=title_clean,
            title_words=title_words,
            keyword_clean_list=keyword_clean_list,
            keyword_words=keyword_words,
            alias_clean_list=alias_clean_list,
            alias_words=alias_words
        )
    
    # === ЗАГРУЗКА ===
    
    def _load(self):
        """Загружает FAQ из файла, заменяя текущий кэш только при успехе."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                raw_items = data.get('faq', [])
            
            if not isinstance(raw_items, list):
                logger.error("❌ Ошибка: корневой ключ 'faq' должен быть списком")
                if STRICT_MODE:
                    raise ValueError("Неверный формат faq.json")
                return
            
            new_faqs: List[FAQ] = []
            new_indexes: List[FAQIndex] = []
            new_by_slug: Dict[str, FAQ] = {}
            new_by_category: Dict[str, List[FAQ]] = {}
            
            seen_ids = set()
            seen_slugs = set()
            
            for idx, item in enumerate(raw_items):
                if not self._validate_faq_item(item, idx):
                    if STRICT_MODE:
                        raise ValueError(f"Ошибка валидации FAQ #{idx}")
                    continue
                
                if item['id'] in seen_ids:
                    logger.error(f"❌ FAQ #{idx}: дублирующийся id={item['id']} – пропущено")
                    if STRICT_MODE:
                        raise ValueError(f"Дублирующийся id: {item['id']}")
                    continue
                seen_ids.add(item['id'])
                
                if item['slug'] in seen_slugs:
                    logger.error(f"❌ FAQ #{idx}: дублирующийся slug='{item['slug']}' – пропущено")
                    if STRICT_MODE:
                        raise ValueError(f"Дублирующийся slug: {item['slug']}")
                    continue
                seen_slugs.add(item['slug'])
                
                index = self._build_index(item)
                new_indexes.append(index)
                new_faqs.append(index.faq)
                
                new_by_slug[index.faq.slug] = index.faq
                new_by_category.setdefault(index.faq.category, []).append(index.faq)
            
            for cat in new_by_category:
                new_by_category[cat].sort(key=lambda x: x.sort)
            
            self.faqs = new_faqs
            self.indexes = new_indexes
            self._by_slug = new_by_slug
            self._by_category = new_by_category
            
            logger.info(f"✅ Загружено и проиндексировано {len(self.faqs)} записей FAQ")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            if STRICT_MODE:
                raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при загрузке FAQ: {e}")
            if STRICT_MODE:
                raise
    
    def reload(self):
        """Безопасная перезагрузка – старый кэш остаётся, если загрузка не удалась."""
        old_faqs = self.faqs
        old_indexes = self.indexes
        old_by_slug = self._by_slug
        old_by_category = self._by_category
        
        try:
            self._load()
            if not self.faqs and old_faqs:
                logger.warning("⚠️ После перезагрузки FAQ пуст, восстанавливаем старый кэш")
                self.faqs = old_faqs
                self.indexes = old_indexes
                self._by_slug = old_by_slug
                self._by_category = old_by_category
        except Exception as e:
            logger.error(f"❌ Ошибка при reload: {e}, восстанавливаем старый кэш")
            self.faqs = old_faqs
            self.indexes = old_indexes
            self._by_slug = old_by_slug
            self._by_category = old_by_category
    
    # === ПУБЛИЧНЫЕ МЕТОДЫ ===
    
    def all(self) -> List[FAQ]:
        return self.faqs
    
    def by_slug(self, slug: str) -> Optional[FAQ]:
        return self._by_slug.get(slug)
    
    def by_category(self, category: str) -> List[FAQ]:
        return self._by_category.get(category, [])
    
    def categories(self) -> dict:
        return self._by_category

    def _score_index(self, index: FAQIndex, query_clean: str, query_words: Set[str]) -> Tuple[int, Set[str], Set[str], Set[str]]:
        """Вычисляет релевантность для одного индекса."""
        score = 0
        
        title_matches = query_words & index.title_words
        score += len(title_matches) * SCORE_TITLE_MATCH
        
        keyword_matches = query_words & index.keyword_words
        score += len(keyword_matches) * SCORE_KEYWORD_MATCH
        
        alias_matches = query_words & index.alias_words
        score += len(alias_matches) * SCORE_ALIASES_MATCH
        
        if query_clean == index.title_clean:
            score += EXACT_TITLE_BONUS
        
        for kw_clean in index.keyword_clean_list:
            if query_clean == kw_clean:
                score += EXACT_KEYWORD_BONUS
                break
        
        for al_clean in index.alias_clean_list:
            if query_clean == al_clean:
                score += EXACT_ALIASES_BONUS
                break
        
        return score, title_matches, keyword_matches, alias_matches

    def search(self, query: str) -> List[FAQ]:
        query_clean = self._clean_text(query)
        if not query_clean:
            return []
        
        # Извлекаем слова – если после удаления стоп-слов ничего не осталось,
        # используем исходные слова (чтобы запросы из одного стоп-слова работали)
        query_words = self._extract_words(query_clean)
        if not query_words:
            # Берём все слова из очищенного запроса (включая стоп-слова)
            query_words = set(query_clean.split())
            # Убираем слишком короткие (≤2) – они всё равно шумные
            query_words = {w for w in query_words if len(w) > 2}
            if not query_words:
                return []
        
        logger.debug(f"🔍 Запрос: '{query_clean}' -> слова: {query_words}")
        
        scored = []
        for index in self.indexes:
            score, t_m, k_m, a_m = self._score_index(index, query_clean, query_words)
            if score > 0:
                scored.append((index.faq, score, t_m, k_m, a_m))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        if scored:
            logger.debug(f"📊 Найдено {len(scored)} результатов. Топ-5:")
            for i, (faq, score, t_m, k_m, a_m) in enumerate(scored[:5]):
                logger.debug(
                    f"   {i+1}. ID {faq.id}: '{faq.title}' "
                    f"(баллы: {score}, title: {t_m}, keywords: {k_m}, aliases: {a_m})"
                )
        else:
            logger.debug(f"❌ Ничего не найдено для запроса: '{query_clean}'")
            return []
        
        max_score = scored[0][1]
        min_score = 1 if len(query_words) == 1 else MIN_SCORE
        
        if max_score < min_score:
            logger.debug(f"⚠️ Порог не пройден (max_score={max_score}, min_score={min_score})")
            return []
        
        # Возвращаем первые 5 результатов – обычно достаточно для FAQ
        return [faq for faq, _, _, _, _ in scored[:5]]


# Глобальный экземпляр
repo = FAQRepository()
