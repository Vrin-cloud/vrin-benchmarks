"""
Shared utilities for VRIN benchmark scripts.

Provides common functionality for:
- Statistical margin of error calculation
- Stratified sampling
- API key handling
- Evaluation helpers (including LLM-based answer normalization)
"""

import math
import os
import random
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional


def calculate_margin_of_error(sample_size: int, population_size: int, confidence: float = 0.95) -> float:
    """
    Calculate margin of error with finite population correction.

    Formula: MOE = z * sqrt(p*(1-p)/n) * sqrt((N-n)/(N-1))

    Args:
        sample_size: Number of samples (n)
        population_size: Total population (N)
        confidence: Confidence level (0.95 or 0.99)

    Returns:
        Margin of error as percentage (e.g., 4.6 for ±4.6%)
    """
    if sample_size <= 0 or population_size <= 0:
        return 0.0

    if sample_size >= population_size:
        return 0.0  # No sampling error when using full population

    # Z-score for confidence level
    z = 1.96 if confidence == 0.95 else 2.576
    p = 0.5  # Conservative estimate (maximum variance)

    # Finite population correction factor
    fpc = math.sqrt((population_size - sample_size) / (population_size - 1))

    # Standard error
    standard_error = math.sqrt((p * (1 - p)) / sample_size) * fpc

    # Margin of error as percentage
    margin = z * standard_error * 100
    return round(margin, 2)


def stratified_sample(
    dataset: List[Dict],
    sample_size: int,
    stratify_key: str,
    seed: int = 42
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Stratified sampling to ensure proportional representation.

    Args:
        dataset: Full dataset
        sample_size: Target sample size
        stratify_key: Key to stratify by (e.g., 'question_type')
        seed: Random seed for reproducibility

    Returns:
        Tuple of (stratified sample, distribution counts dict)
    """
    random.seed(seed)

    # Group by stratification key
    by_group = defaultdict(list)
    for item in dataset:
        group = item.get(stratify_key, 'unknown')
        by_group[group].append(item)

    # Calculate proportional samples per group
    total = len(dataset)
    sample = []
    distribution = {}

    for group, items in sorted(by_group.items()):
        group_ratio = len(items) / total
        group_sample_size = max(1, round(sample_size * group_ratio))
        group_sample = random.sample(items, min(group_sample_size, len(items)))
        sample.extend(group_sample)
        distribution[group] = len(group_sample)

    # Adjust to exact sample size (may be slightly over due to rounding)
    random.shuffle(sample)
    final_sample = sample[:sample_size]

    # Recalculate distribution after trimming
    final_distribution = defaultdict(int)
    for item in final_sample:
        group = item.get(stratify_key, 'unknown')
        final_distribution[group] += 1

    return final_sample, dict(final_distribution)


def get_api_key() -> str:
    """
    Get VRIN API key from environment, raising error if not set.

    Returns:
        API key string

    Raises:
        ValueError: If TEST_ACC_API_KEY environment variable is not set
    """
    api_key = os.getenv('TEST_ACC_API_KEY')
    if not api_key:
        raise ValueError(
            "TEST_ACC_API_KEY environment variable must be set.\n"
            "Export it before running: export TEST_ACC_API_KEY=vrin_xxxx"
        )
    return api_key


def normalize_answer_with_llm(vrin_response: str, expected_format: str, question: str = "") -> str:
    """
    Use LLM to normalize VRIN's verbose response to the expected answer format.

    VRIN returns detailed, well-reasoned responses (e.g., "Based on the evidence,
    the data strongly suggests a positive outcome..." for a Yes/No question).
    The benchmark expected answer might just be "Yes". This function uses an LLM
    to extract the core answer from the verbose response.

    Args:
        vrin_response: VRIN's full response
        expected_format: Hint about expected format (e.g., "Yes/No", "entity name")
        question: Original question for context

    Returns:
        Normalized answer string
    """
    import os
    import requests

    # Get OpenAI API key from environment or .env file
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        try:
            # Check script directory first, then parent
            env_path = os.path.join(os.path.dirname(__file__), '.env')
            if not os.path.exists(env_path):
                env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith('OPENAI_API_KEY='):
                            api_key = line.split('=', 1)[1].strip()
                            break
        except:
            pass

    if not api_key:
        # Fallback to pattern-based extraction
        return extract_answer_pattern(vrin_response, expected_format)

    prompt = f"""Extract the core answer from this response. Return ONLY the answer, nothing else.

Question: {question}
Expected answer format: {expected_format}

Response to analyze:
{vrin_response[:1500]}

Rules:
- If the response indicates YES/agreement/confirmation → return "Yes"
- If the response indicates NO/disagreement/denial → return "No"
- If comparing and they are SIMILAR/same/consistent → return "Similar"
- If comparing and they are DIFFERENT/contrasting → return "Different"
- If the answer is a name/entity, return just the name (e.g., "Sam Bankman-Fried", "Google")
- If insufficient information → return "Insufficient information"

Your answer (just the core answer, no explanation):"""

    try:
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-4o-mini',  # Fast and cheap for simple extraction
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 50,
                'temperature': 0
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        pass

    # Fallback to pattern extraction
    return extract_answer_pattern(vrin_response, expected_format)


def extract_answer_pattern(vrin_response: str, expected_format: str) -> str:
    """Fallback pattern-based answer extraction when LLM is unavailable."""
    response_lower = vrin_response.lower()[:500]

    if "yes/no" in expected_format.lower():
        if response_lower.startswith("yes") or "**yes**" in response_lower[:100]:
            return "Yes"
        if response_lower.startswith("no") or "**no**" in response_lower[:100]:
            return "No"
        if any(x in response_lower[:200] for x in ["confirm", "both agree", "correct", "indeed"]):
            return "Yes"
        if any(x in response_lower[:200] for x in ["not ", "cannot", "neither", "incorrect"]):
            return "No"

    if "similar/different" in expected_format.lower():
        if any(x in response_lower[:200] for x in ["similar", "same", "consistent", "both"]):
            return "Similar"
        if any(x in response_lower[:200] for x in ["different", "differ", "contrast", "opposite"]):
            return "Different"

    return vrin_response[:100]  # Return truncated response as fallback


def evaluate_multihop_answer(expected: str, vrin_response: str, question: str = "", use_llm_normalizer: bool = True) -> Tuple[bool, str]:
    """
    Evaluate MultiHop-RAG answer with LLM-based normalization.

    Uses an LLM to extract the core answer from VRIN's verbose response,
    then compares to expected answer. This is necessary because VRIN returns
    detailed reasoning (e.g., "Based on the evidence, this indicates a positive
    outcome...") while the benchmark expects a single word like "Yes".

    The evaluation pipeline:
    1. Direct substring match (exact keyword found in response)
    2. LLM normalization (extract core answer, then match)
    3. Semantic pattern fallback (check for semantic indicators)

    Args:
        expected: Expected answer from benchmark
        vrin_response: VRIN's full response
        question: Original question for context
        use_llm_normalizer: Whether to use LLM for answer extraction

    Returns:
        Tuple of (is_correct, match_type)
    """
    import unicodedata

    # Normalize Unicode (convert en-dash, em-dash to regular hyphen, etc.)
    def normalize_text(text: str) -> str:
        text = unicodedata.normalize('NFKC', text)
        text = text.replace('\u2013', '-').replace('\u2014', '-').replace('\u2011', '-')
        return text.lower().strip()

    expected_lower = normalize_text(expected)
    vrin_lower = normalize_text(vrin_response)

    # 1. Direct substring match (most reliable)
    if expected_lower in vrin_lower:
        return True, "direct_match"

    # 2. Determine expected format for normalization
    expected_format = "Yes/No"  # Default
    if expected_lower in ["yes", "no"]:
        expected_format = "Yes/No"
    elif expected_lower in ["similar", "different"]:
        expected_format = "Similar/Different"
    elif "insufficient" in expected_lower:
        expected_format = "Insufficient information or available"
    else:
        expected_format = f"entity name like '{expected}'"

    # 3. Use LLM normalizer if enabled
    if use_llm_normalizer:
        normalized = normalize_answer_with_llm(vrin_response, expected_format, question)
        normalized_lower = normalize_text(normalized)

        # Check if normalized answer matches expected
        if expected_lower == normalized_lower:
            return True, "llm_normalized_exact"
        if expected_lower in normalized_lower or normalized_lower in expected_lower:
            return True, "llm_normalized_partial"
        # Check semantic equivalence for Yes/No
        if expected_lower == "yes" and normalized_lower in ["yes", "correct", "true", "confirmed"]:
            return True, "llm_normalized_semantic"
        if expected_lower == "no" and normalized_lower in ["no", "incorrect", "false", "denied"]:
            return True, "llm_normalized_semantic"

    # 4. Fallback to pattern matching
    first_300 = vrin_lower[:300]

    yes_indicators = [
        "yes", "correct", "true", "indeed", "confirm", "confirmed",
        "both agree", "both suggest", "consistent"
    ]
    no_indicators = [
        "no", "not", "incorrect", "false", "neither", "none",
        "doesn't", "don't", "cannot"
    ]
    similar_indicators = ["similar", "same", "consistent", "both agree", "match"]
    different_indicators = ["different", "differ", "contrast", "opposite"]

    if expected_lower == "yes":
        if any(ind in first_300 for ind in yes_indicators):
            first_50 = vrin_lower[:50]
            if not any(first_50.startswith(neg) for neg in ["no,", "no.", "no "]):
                return True, "semantic_yes"

    elif expected_lower == "no":
        if any(ind in first_300 for ind in no_indicators):
            return True, "semantic_no"

    elif expected_lower == "similar":
        if any(ind in first_300 for ind in similar_indicators):
            if not any(neg in first_300 for neg in different_indicators):
                return True, "semantic_similar"

    elif "insufficient" in expected_lower:
        if any(x in vrin_lower for x in [
            "insufficient", "cannot determine", "no information",
            "don't have sufficient", "do not have sufficient",
            "not have sufficient", "nothing specifically relevant"
        ]):
            return True, "semantic_insufficient"

    return False, "no_match"


def evaluate_finqa_answer(expected: str, vrin_response: str) -> Tuple[bool, str]:
    """
    Evaluate FinQA answer with improved numerical matching.

    Uses tolerance-based matching (1%) instead of substring matching,
    and handles percentage conversions (e.g., 0.15 vs 15%).

    Args:
        expected: Expected answer from benchmark
        vrin_response: VRIN's response

    Returns:
        Tuple of (is_correct, match_type)
    """
    def extract_numbers(text: str) -> List[float]:
        """Extract numerical values, handling commas and percentages."""
        pattern = r'-?[\d,]+\.?\d*%?'
        matches = re.findall(pattern, text)
        numbers = []
        for m in matches:
            try:
                clean = m.replace(',', '').replace('%', '')
                if clean and clean != '-':
                    numbers.append(float(clean))
            except ValueError:
                continue
        return numbers

    expected_nums = extract_numbers(expected)
    vrin_nums = extract_numbers(vrin_response)

    # If no numbers in expected answer, fall back to text matching
    if not expected_nums:
        if expected.lower().strip() in vrin_response.lower():
            return True, "text_match"
        return False, "no_match"

    # Check if primary expected number is found with 1% tolerance
    primary_expected = expected_nums[0]

    # Handle zero specially (use absolute tolerance)
    if primary_expected == 0:
        tolerance = 0.01
    else:
        tolerance = abs(primary_expected * 0.01)  # 1% tolerance

    for vrin_num in vrin_nums:
        # Direct match with tolerance
        if abs(vrin_num - primary_expected) <= tolerance:
            return True, "numerical_match"

        # Check percentage conversions (e.g., 0.15 vs 15%)
        if primary_expected != 0:
            if abs(vrin_num - primary_expected * 100) <= tolerance * 100:
                return True, "percentage_match"
            if abs(vrin_num * 100 - primary_expected) <= tolerance * 100:
                return True, "percentage_match"

    return False, "no_match"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}min"
    else:
        return f"{seconds/3600:.1f}h"
