from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict

# ====== НОВЫЙ КЛАСС ДЛЯ FAQ ======
@dataclass
class FAQ:
    id: int
    slug: str
    title: str
    category: str
    sort: int = 0
    keywords: List[str] = field(default_factory=list)
    answer: str = ""


# ====== СТАРЫЕ КЛАССЫ ДЛЯ ПОИСКА (восстановлены) ======
@dataclass
class Candidate:
    """Кандидат (результат поиска)"""
    id: int
    text: str
    score: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SearchResult:
    """Результат поиска"""
    query: str
    candidates: List[Candidate]
    total: int
    took_ms: float
    debug: Optional['SearchDebug'] = None


@dataclass
class SearchDebug:
    """Отладочная информация поиска"""
    raw_query: str
    tokens: List[str]
    expanded: List[str]
    vector: Optional[List[float]] = None
    index_scan: int = 0
    candidates_before_rerank: int = 0
