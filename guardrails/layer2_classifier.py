"""
Layer 2 — Input Classifier
Blocks out-of-scope queries before spending GPU time on inference.
Three-step pipeline: keyword → embedding → decision.
"""

import re
import numpy as np

# --- Keyword patterns ---

OUT_OF_SCOPE_PATTERNS = [
    # Weather
    r'\b(weather|temperature|forecast|rain|sunny|humidity|climate|monsoon\s+season)\b',
    # Sports
    r'\b(cricket|ipl|football|match|score|team|player|tournament|wicket|century|goal\s+scored)\b',
    # Politics/government ('party' excluded — too common in ERP e.g. "third party invoice")
    r'\b(minister|parliament|election|vote|prime minister|president|politics)\b',
    r'\b(political party|ruling party|opposition party|bjp|congress|aap)\b',
    r'\bgovernment\b(?!\s*(portal|scheme|subsidy|tender|contract|e-tender|registration))',
    # Medical/health
    r'\b(doctor|medicine|hospital|disease|symptoms?|treatment|covid|diagnosis|dosage|side effects?)\b',
    r'\b(lose weight|weight loss|diet plan|calorie|fitness|gym|workout|exercise for)\b',
    # Entertainment
    r'\b(movies?|films?|songs?|actors?|actresses?|bollywood|netflix|ott|web series|tv show)\b',
    r'\b(releasing this|now playing|box office|trailer|review of the)\b',
    # News
    r'\b(latest news|breaking news|current events?|headlines?|today\'s news)\b',
    r'\bnews\b(?!\s*(gst|tax|erp|invoice|payroll|compliance))',  # "news" not followed by ERP terms
    # Jokes / creative
    r'\b(joke|poem|recipe|cooking|fashion|fun fact|riddle)\b',
    r'\bwrite\b.{0,15}?\b(poem|story|essay|letter|speech|song|script|novel)\b',
    r'\btell me (a|an)\b.{0,10}?\b(joke|story|riddle|fun fact)\b',
    # Injection phrases (also caught by layer4 but belt-and-suspenders)
    r'\b(jailbreak|pretend|ignore instructions|you are now|roleplay)\b',
    # General knowledge
    r'\b(capital of|who invented|when was|history of|what year did|who was the first)\b',
    r'\b(speed of light|gravitational constant|periodic table|atomic weight|chemical formula)\b',
    r'\b(photosynthesis|evolution|big bang|solar system|planet|constellation)\b',
    # Personal/relationship
    r'\b(girlfriend|boyfriend|relationship advice|breakup|divorce|dating|marriage tips)\b',
    # Travel/lifestyle
    r'\b(best place to visit|tourist spot|hotel booking|flight ticket|passport|visa)\b',
    r'\b(best restaurants?|restaurants? in|street food|cuisines?|food in)\b',
    # Non-ERP coding/tech
    r'\bhow (do i|to) (code|build|create|make|scrape|automate|write (python|java|javascript|html|css))\b',
    r'\b(web scraper|web scraping|selenium|beautifulsoup|automation bot|crawler)\b',
    r'\b(debug this code|fix this bug|write (python|java|javascript) code for)\b',
    # Science/math (non-ERP)
    r'\b(solve this equation|find the value of x|derivative of|integral of|matrix multiplication)\b',
    # Hindi OOS patterns (\b doesn't work with Devanagari, use plain search)
    r'(मौसम|बारिश|क्रिकेट|फ़िल्म|गाना|मज़ाक|कहानी|खाना बनाना|राजनीति|अस्पताल)',
    r'(कल का|आज का|खेल|मैच|नेता|सरकार|स्वास्थ्य|वज़न कम)',
    # Competitor ERP tutorials
    r'\bhow (do i|to) (use|setup|configure|install) (tally|zoho|sap|oracle|quickbooks)\b',
    r'\b(tally|zoho|sap|quickbooks) (tutorial|guide|help|support|error|issue)\b',
]

IN_SCOPE_PATTERNS = [
    r'\b(gst|igst|cgst|sgst|hsn|sac|itc|invoice|e-invoice|irn|e-way)\b',
    r'\b(payroll|salary|pf|epf|esic|tds|form 16|gratuity|bonus|ctc)\b',
    r'\b(kinnow|erp|vendor|purchase order|sales order|ledger|journal)\b',
    r'\b(gstr|gstr-1|gstr-3b|gstr-9|gstr-2a|gstr-2b|annual return)\b',
    r'\b(tcs|advance tax|itr|pan|tan|din|cin|mca|professional tax)\b',
]

# Production thresholds (Section 21b)
CLASSIFIER_THRESHOLD_PASS = 0.65     # score >= 0.65 → pass (high confidence ERP)
CLASSIFIER_THRESHOLD_CLARIFY = 0.45  # score 0.45–0.65 → ask for clarification

CLARIFICATION_MESSAGE = (
    "I'm Kinnow's ERP assistant. Could you clarify — are you asking about "
    "GST, payroll, invoice matching, or another ERP topic?"
)

# Loaded once at startup (SentenceTransformer imported lazily)
_emb_model = None
_domain_centroids: dict[str, np.ndarray] = {}


def load_embedding_model():
    global _emb_model
    if _emb_model is None:
        from sentence_transformers import SentenceTransformer  # lazy import
        _emb_model = SentenceTransformer(
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
    return _emb_model


def build_centroids(training_examples: dict) -> dict:
    """
    Pre-compute category centroids from training data at startup.
    training_examples: {'GST': ['question1', 'question2', ...], 'PAYROLL': [...], ...}
    """
    model = load_embedding_model()
    centroids = {}
    for category, examples in training_examples.items():
        embeddings = model.encode(examples, show_progress_bar=False)
        centroids[category] = embeddings.mean(axis=0)
    return centroids


def set_domain_centroids(centroids: dict[str, np.ndarray]) -> None:
    """Call this at app startup after building centroids from training data."""
    global _domain_centroids
    _domain_centroids = centroids


def classify_input_fast(query: str) -> tuple[str, float]:
    """
    Fast keyword/regex classification. Returns (decision, confidence).
    decision: 'in_scope' | 'out_of_scope' | 'uncertain'
    """
    q = query.lower()
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return 'out_of_scope', 1.0
    in_scope_hits = sum(1 for p in IN_SCOPE_PATTERNS if re.search(p, q, re.IGNORECASE))
    if in_scope_hits >= 2:
        return 'in_scope', 0.95
    if in_scope_hits == 1:
        return 'in_scope', 0.75
    return 'uncertain', 0.5


def classify_by_embedding(query: str) -> tuple[str, float]:
    """
    Embedding-based classification against domain centroids.
    Returns (best_category, similarity_score).
    Falls back to 'out_of_scope' if no centroids are loaded.
    """
    if not _domain_centroids:
        return 'uncertain', 0.5

    model = load_embedding_model()
    q_emb = model.encode([query], show_progress_bar=False)[0]
    scores = {
        cat: float(np.dot(q_emb, c) / (np.linalg.norm(q_emb) * np.linalg.norm(c)))
        for cat, c in _domain_centroids.items()
    }
    best_cat = max(scores, key=scores.get)
    max_score = scores[best_cat]
    return best_cat, max_score


def classify_query(query: str) -> dict:
    """
    Full classification pipeline. Returns decision dict:
    {
        'decision': 'pass' | 'block' | 'clarify',
        'reason': str,
        'confidence': float,
        'clarification': str  # only when decision == 'clarify'
    }
    """
    fast_decision, fast_conf = classify_input_fast(query)

    # Fast block: keyword clearly OOS
    if fast_decision == 'out_of_scope' and fast_conf >= 0.9:
        return {'decision': 'block', 'reason': 'keyword_oos', 'confidence': fast_conf}

    # Fast pass: strong ERP keyword signal (2+ matches)
    if fast_decision == 'in_scope' and fast_conf >= 0.9:
        return {'decision': 'pass', 'reason': 'keyword_in_scope', 'confidence': fast_conf}

    # When no centroids are loaded, promote keyword-only decision directly
    if not _domain_centroids:
        if fast_decision == 'in_scope':
            return {'decision': 'pass', 'reason': 'keyword_in_scope_no_centroids', 'confidence': fast_conf}
        if fast_decision == 'out_of_scope':
            return {'decision': 'block', 'reason': 'keyword_oos', 'confidence': fast_conf}
        return {
            'decision': 'clarify',
            'reason': 'no_centroids_uncertain',
            'confidence': 0.5,
            'clarification': CLARIFICATION_MESSAGE,
        }

    # Uncertain — use embedding similarity
    _, emb_conf = classify_by_embedding(query)

    if emb_conf >= CLASSIFIER_THRESHOLD_PASS:
        return {'decision': 'pass', 'reason': 'embedding_high_confidence', 'confidence': emb_conf}

    if emb_conf >= CLASSIFIER_THRESHOLD_CLARIFY:
        return {
            'decision': 'clarify',
            'reason': 'ambiguous_query',
            'confidence': emb_conf,
            'clarification': CLARIFICATION_MESSAGE,
        }

    # Below clarify threshold — block. When in doubt, block.
    return {'decision': 'block', 'reason': 'low_erp_similarity', 'confidence': emb_conf}
