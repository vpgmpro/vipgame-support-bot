# search.py
import re
import logging
from typing import List, Set, Optional, Tuple
from models import FAQ, Candidate, SearchResult, SearchDebug
from repository import FAQRepository

SEARCH_ENGINE_VERSION = "2.0.0"
MIN_MATCH_RATIO = 0.3
TOPIC_BONUS = 15
TOPIC_MIN_SCORE = 2
LOG_SEARCH_DEBUG = True

STOP_WORDS = {'что', 'как', 'где', 'когда', 'ли', 'это', 'такое', 'то', 'чем', 'для', 'без', 'по', 'с', 'в', 'на', 'зачем', 'почему', 'откуда', 'куда', 'кто', 'чей', 'какой', 'какая', 'какое', 'какие', 'мой', 'твой', 'свой', 'наш', 'ваш', 'его', 'её', 'их', 'быть', 'стать', 'являться', 'иметь', 'можно', 'нужно', 'надо', 'будет', 'есть'}

TOPIC_WORDS = {'аккаунт', 'игра', 'маркет', 'кристалл', 'статус', 'ячейка'}

logger = logging.getLogger(__name__)

HAS_MORPH = False
try:
    import pymorphy3
    morph = pymorphy3.MorphAnalyzer()
    HAS_MORPH = True
except ImportError:
    pass

class SearchEngine:
    def __init__(self, repository: FAQRepository):
        self.repo = repository
    
    def normalize_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def get_lemma(self, word: str) -> str:
        if HAS_MORPH:
            try:
                return morph.parse(word)[0].normal_form
            except:
                return word
        return word
    
    def prepare_tokens(self, text: str, remove_stop_words: bool = True) -> List[str]:
        normalized = self.normalize_text(text)
        words = normalized.split()
        if remove_stop_words:
            words = [w for w in words if w not in STOP_WORDS]
        if not words:
            words = normalized.split()
        return words
    
    def get_lemmatized_tokens(self, text: str, remove_stop_words: bool = True) -> List[str]:
        words = self.prepare_tokens(text, remove_stop_words)
        if HAS_MORPH:
            return [self.get_lemma(w) for w in words]
        return words
    
    def detect_topics(self, tokens: Set[str]) -> Set[str]:
        topics = set()
        for w in tokens:
            if w in TOPIC_WORDS:
                topics.add(w)
        return topics
    
    def find_exact_match(self, question: str, faq_list: List[FAQ]) -> Optional[FAQ]:
        for faq in faq_list:
            for normalized_keyword in faq.normalized_keywords:
                if question == normalized_keyword:
                    return faq
        return None
    
    def calculate_match_score(self, question_tokens: Set[str], question_words: List[str], faq: FAQ, idx: int):
        keyword_norm = faq.normalized_keywords[idx]
        if HAS_MORPH and idx < len(faq.lemmas):
            keyword_words = faq.lemmas[idx].split()
        else:
            keyword_words = [w for w in keyword_norm.split() if w not in STOP_WORDS]
        if not keyword_words:
            return None, 0, keyword_norm
        keyword_words_set = set(keyword_words)
        matched_words = len(question_tokens & keyword_words_set)
        keyword_len = len(keyword_words)
        if matched_words == 0:
            return None, 0, keyword_norm
        match_ratio = matched_words / keyword_len
        if match_ratio < MIN_MATCH_RATIO:
            return None, 0, keyword_norm
        score = match_ratio * 10
        keyword_without_stops = ' '.join(keyword_words)
        question_without_stops = ' '.join(question_words)
        if keyword_without_stops in question_without_stops:
            score += 30
        if keyword_len >= 2:
            score += keyword_len * 2
        else:
            score += 1
        return score, keyword_len, keyword_norm
    
    def calculate_topic_bonus(self, question_topics: Set[str], faq_topics: Set[str], base_score: float) -> int:
        if not question_topics or not faq_topics:
            return 0
        common_topics = len(faq_topics & question_topics)
        if common_topics == 0:
            return 0
        if base_score < TOPIC_MIN_SCORE:
            return 0
        return TOPIC_BONUS * common_topics
    
    def prepare_faq_for_search(self, faq_list: List[FAQ]) -> List[FAQ]:
        for faq in faq_list:
            for keyword in faq.keywords:
                keyword_norm = self.normalize_text(keyword)
                faq.normalized_keywords.append(keyword_norm)
                if HAS_MORPH:
                    keyword_lemmas = ' '.join(self.get_lemma(w) for w in keyword_norm.split())
                else:
                    keyword_lemmas = keyword_norm
                faq.lemmas.append(keyword_lemmas)
                keyword_tokens = set(keyword_norm.split())
                for w in keyword_tokens:
                    lemma = self.get_lemma(w) if HAS_MORPH else w
                    if lemma in TOPIC_WORDS:
                        faq.topics.add(lemma)
        return faq_list
    
    def find_best(self, question: str) -> SearchResult:
        normalized_question = self.normalize_text(question)
        faq_list = self.repo.all()
        self.prepare_faq_for_search(faq_list)
        
        exact_match = self.find_exact_match(normalized_question, faq_list)
        if exact_match:
            return SearchResult(
                id=exact_match.id,
                slug=exact_match.slug,
                answer=exact_match.answer,
                score=100,
                base_score=100,
                topic_bonus=0,
                keyword="Точное совпадение",
                topics=exact_match.topics,
                is_exact=True,
                engine_version=SEARCH_ENGINE_VERSION
            )
        
        question_words = self.prepare_tokens(normalized_question, remove_stop_words=True)
        question_tokens = set(self.get_lemmatized_tokens(normalized_question, remove_stop_words=True))
        if not question_tokens:
            question_words = normalized_question.split()
            question_tokens = set(question_words)
        
        question_topics = self.detect_topics(question_tokens)
        
        result = SearchResult()
        candidates = []
        
        for faq in faq_list:
            max_keyword_score = 0
            best_keyword_for_faq = ''
            best_keyword_count_for_faq = 0
            
            for idx, keyword in enumerate(faq.keywords):
                calc_result = self.calculate_match_score(question_tokens, question_words, faq, idx)
                if calc_result[0] is None:
                    continue
                score, keyword_len, keyword_norm = calc_result
                if score > max_keyword_score:
                    max_keyword_score = score
                    best_keyword_for_faq = keyword_norm
                    best_keyword_count_for_faq = keyword_len
            
            base_score = max_keyword_score
            faq_topics = faq.topics
            topic_bonus = self.calculate_topic_bonus(question_topics, faq_topics, base_score)
            total_score = base_score + topic_bonus
            
            if total_score > 0:
                candidates.append(Candidate(
                    id=faq.id,
                    slug=faq.slug,
                    score=total_score,
                    base_score=base_score,
                    topic_bonus=topic_bonus,
                    keyword=best_keyword_for_faq
                ))
            
            if total_score > result.score or (total_score == result.score and best_keyword_count_for_faq > result.score):
                result.score = total_score
                result.answer = faq.answer
                result.id = faq.id
                result.slug = faq.slug
                result.keyword = best_keyword_for_faq
                result.topics = faq_topics
                result.base_score = base_score
                result.topic_bonus = topic_bonus
                result.engine_version = SEARCH_ENGINE_VERSION
        
        result.candidates = sorted(candidates, key=lambda x: x.score, reverse=True)[:5]
        
        if LOG_SEARCH_DEBUG and result.answer:
            result.debug = SearchDebug(
                tokens=question_words,
                lemmas=list(question_tokens),
                topics=list(question_topics),
                candidates=[{'slug': c.slug, 'score': c.score, 'base_score': c.base_score, 'topic_bonus': c.topic_bonus} for c in result.candidates[:5]]
            )
        
        if result.score < 1:
            result.answer = None
            result.id = None
            result.slug = None
        
        return result
    
    def find_answer(self, question: str) -> Optional[str]:
        result = self.find_best(question)
        return result.answer
