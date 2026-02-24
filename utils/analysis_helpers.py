"""
Helper functions for advanced user analysis.
Includes word frequency analysis, multi-agent pipeline, and psychoanalysis frameworks.
"""

from collections import Counter
from typing import Dict, List, Any, Optional
import re
import logging

logger = logging.getLogger(__name__)


def analyze_word_frequency(messages: List[Dict[str, Any]], top_n: int = 50) -> Dict[str, Any]:
    """
    Analyze word frequency to identify meaningful patterns.
    Filters out common stop words and focuses on personality-revealing vocabulary.
    
    Args:
        messages: List of message dictionaries
        top_n: Number of top words to return
    
    Returns:
        Dictionary with word frequency statistics
    """
    # Common stop words to filter out
    stop_words = {
        'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for', 'not',
        'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his', 'by', 'from',
        'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would',
        'there', 'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which',
        'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
        'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them', 'see',
        'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over', 'think',
        'also', 'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first', 'well',
        'way', 'even', 'new', 'want', 'because', 'any', 'these', 'give', 'day', 'most', 'us',
        'is', 'was', 'are', 'been', 'has', 'had', 'were', 'said', 'did', 'having', 'may',
        'im', 'dont', 'cant', 'wont', 'didnt', 'doesnt', 'isnt', 'arent', 'wasnt', 'werent',
        'yeah', 'yes', 'no', 'ok', 'okay', 'oh', 'ah', 'um', 'uh', 'lol', 'lmao', 'haha'
    }
    
    # Collect all words
    all_words = []
    for msg in messages:
        # Clean and tokenize
        text = msg['content'].lower()
        # Remove URLs, mentions, emojis
        text = re.sub(r'http\S+|www\S+|<@\d+>|<#\d+>|:\w+:', '', text)
        # Extract words (alphanumeric only)
        words = re.findall(r'\b[a-z]{3,}\b', text)
        all_words.extend(words)
    
    # Filter stop words and count
    meaningful_words = [w for w in all_words if w not in stop_words]
    word_counts = Counter(meaningful_words)
    
    # Get top words
    top_words = word_counts.most_common(top_n)
    
    # Calculate statistics
    total_words = len(all_words)
    unique_words = len(set(all_words))
    vocabulary_richness = unique_words / total_words if total_words > 0 else 0
    
    return {
        'top_words': top_words,
        'total_words': total_words,
        'unique_words': unique_words,
        'vocabulary_richness': vocabulary_richness,
        'meaningful_word_count': len(meaningful_words)
    }


def get_psychoanalysis_prompt(analysis_type: str, user_name: str, message_count: int, 
                               message_samples: str, word_freq: Dict[str, Any]) -> str:
    """
    Generate specialized prompts based on psychoanalysis framework.
    
    Args:
        analysis_type: Type of psychological framework
        user_name: Display name of user
        message_count: Number of messages
        message_samples: Sample messages
        word_freq: Word frequency analysis data
    
    Returns:
        Specialized analysis prompt
    """
    # Format top words for prompt
    top_words_str = ", ".join([f"{word} ({count}x)" for word, count in word_freq['top_words'][:20]])
    
    base_context = f"""User: {user_name}
Messages Analyzed: {message_count:,}
Vocabulary Richness: {word_freq['vocabulary_richness']:.2%}
Most Used Words: {top_words_str}

Sample Messages:
{message_samples}"""

    frameworks = {
        "freudian": f"""🔬 **FREUDIAN PSYCHOANALYSIS**

{base_context}

Analyze {user_name} through a Freudian lens. Focus on:

1. **Unconscious Motivations**: What hidden drives appear in their communication?
2. **Defense Mechanisms**: Do they use denial, projection, rationalization, displacement, or sublimation?
3. **Id, Ego, Superego Balance**: Which dominates their personality?
4. **Fixations & Conflicts**: Any signs of unresolved psychological conflicts?
5. **Symbolic Language**: What do their word choices reveal about unconscious desires?
6. **Transference Patterns**: How do they relate to authority figures or peers?

Be insightful and respectful. Use their most frequent words to support your analysis.""",

        "jungian": f"""🎭 **JUNGIAN ANALYTICAL PSYCHOLOGY**

{base_context}

Analyze {user_name} through a Jungian framework. Explore:

1. **Dominant Archetype**: Hero, Sage, Caregiver, Rebel, Lover, Creator, etc.
2. **Shadow Self**: What aspects do they repress or project onto others?
3. **Persona vs. True Self**: How authentic are they online vs. their public mask?
4. **Anima/Animus**: Integration of masculine/feminine psychological traits
5. **Individuation Journey**: Are they on a path of self-discovery and integration?
6. **Collective Unconscious Symbols**: Universal themes in their communication
7. **Psychological Type**: Introversion/Extraversion, Thinking/Feeling, etc.

Use their vocabulary patterns to identify archetypal themes.""",

        "humanistic": f"""🌟 **HUMANISTIC PSYCHOLOGY (Rogers/Maslow)**

{base_context}

Analyze {user_name} through humanistic psychology. Focus on:

1. **Self-Actualization**: Are they pursuing growth and potential?
2. **Hierarchy of Needs**: Which needs (physiological, safety, belonging, esteem, self-actualization) dominate?
3. **Authenticity & Congruence**: How genuine and self-aware are they?
4. **Positive Regard**: Do they show unconditional acceptance of others?
5. **Growth Mindset**: Evidence of learning, curiosity, and personal development
6. **Peak Experiences**: Moments of joy, flow, or transcendence in their messages
7. **Self-Concept**: How do they view themselves? Positive or negative self-image?

Highlight their strengths and growth potential.""",

        "cognitive_behavioral": f"""🧩 **COGNITIVE-BEHAVIORAL ANALYSIS**

{base_context}

Analyze {user_name} through CBT principles. Examine:

1. **Thought Patterns**: Identify cognitive distortions (all-or-nothing, overgeneralization, catastrophizing, etc.)
2. **Core Beliefs**: What fundamental beliefs about self, others, and world emerge?
3. **Automatic Thoughts**: Recurring thought patterns in their messages
4. **Behavioral Patterns**: Observable habits and response patterns
5. **Emotional Regulation**: How do they manage and express emotions?
6. **Problem-Solving Style**: Adaptive or maladaptive coping strategies?
7. **Cognitive Flexibility**: Can they shift perspectives or are they rigid?

Use word frequency to identify thought pattern indicators.""",

        "trait_theory": f"""🎨 **BIG FIVE PERSONALITY TRAITS**

{base_context}

Analyze {user_name} using the Five-Factor Model (OCEAN). Rate and explain:

1. **Openness to Experience** (1-10): Creativity, curiosity, imagination
   - Evidence from messages and vocabulary diversity
   
2. **Conscientiousness** (1-10): Organization, responsibility, goal-directed behavior
   - Patterns in communication style and follow-through
   
3. **Extraversion** (1-10): Sociability, assertiveness, energy level
   - Interaction frequency and social engagement
   
4. **Agreeableness** (1-10): Compassion, cooperation, trust
   - How they treat others, conflict resolution style
   
5. **Neuroticism** (1-10): Emotional stability, anxiety, mood swings
   - Emotional tone and stress indicators

Provide specific examples from their messages for each trait.""",

        "mbti": f"""💼 **MBTI-STYLE COGNITIVE FUNCTIONS**

{base_context}

Analyze {user_name} using MBTI-inspired cognitive function framework:

1. **Dominant Function**: What's their primary way of processing information?
   - Ti (Introverted Thinking), Te (Extraverted Thinking)
   - Fi (Introverted Feeling), Fe (Extraverted Feeling)
   - Ni (Introverted Intuition), Ne (Extraverted Intuition)
   - Si (Introverted Sensing), Se (Extraverted Sensing)

2. **Auxiliary Function**: Their secondary cognitive process

3. **Tertiary & Inferior Functions**: Less developed aspects

4. **Likely Type**: Best-fit MBTI type (e.g., INTJ, ENFP, ISTP)

5. **Communication Style**: How their cognitive functions manifest in messages

6. **Strengths & Blind Spots**: Based on function stack

Use vocabulary and interaction patterns to determine cognitive preferences."""
    }
    
    return frameworks.get(analysis_type, frameworks["trait_theory"])


async def multi_agent_analysis(llm, messages: List[Dict[str, Any]], user_name: str, 
                                model: str, analysis_type: str, 
                                progress_callback: Optional[callable] = None) -> Dict[str, str]:
    """
    Run multi-agent analysis pipeline where each agent handles a specific section.
    This ensures NO EMPTY RESPONSES and high-quality analysis for each section.
    
    Args:
        llm: LLM instance for chat
        messages: Message data
        user_name: Display name
        model: Model to use
        analysis_type: Psychoanalysis framework
        progress_callback: Optional callback for progress updates
    
    Returns:
        Complete analysis data dictionary
    """
    # Prepare data
    word_freq = analyze_word_frequency(messages)
    sample_size = min(100, len(messages))
    step = max(1, len(messages) // sample_size)
    message_samples = "\n".join([
        f"- {messages[i]['content'][:200]}" 
        for i in range(0, len(messages), step)
    ][:100])
    
    analysis_data = {}
    
    # Agent 1: Word Frequency & Vocabulary Analysis
    if progress_callback:
        await progress_callback("🔤 Agent 1: Analyzing vocabulary patterns...")
    
    top_words_list = "\n".join([f"- **{word}**: {count} times" for word, count in word_freq['top_words'][:30]])
    
    agent1_prompt = f"""Analyze {user_name}'s vocabulary and linguistic patterns:

**Word Frequency Data:**
- Total words: {word_freq['total_words']:,}
- Unique words: {word_freq['unique_words']:,}
- Vocabulary richness: {word_freq['vocabulary_richness']:.2%}

**Top 30 Most Used Words:**
{top_words_list}

Provide detailed analysis of:
1. What their most-used words reveal about their personality and values
2. Vocabulary sophistication and communication style
3. Emotional tone indicators (positive/negative word usage)
4. Unique linguistic quirks or signature phrases
5. How their word choices reflect their mindset

Be specific and insightful. No character limits."""

    agent1_response = ""
    async for chunk in llm.chat_stream([{"role": "user", "content": agent1_prompt}], model=model):
        agent1_response += chunk
    
    analysis_data["vocabulary_analysis"] = agent1_response
    
    # Agent 2: Communication Style & Tone
    if progress_callback:
        await progress_callback("💬 Agent 2: Analyzing communication style...")
    
    agent2_prompt = f"""Analyze {user_name}'s communication style based on {len(messages):,} messages:

Sample messages:
{message_samples}

Provide detailed analysis of:
1. **Tone & Emotional Expression**: Formal/casual, warm/cold, enthusiastic/reserved
2. **Message Structure**: Short/long, organized/stream-of-consciousness
3. **Emoji & Formatting Use**: How they enhance communication
4. **Engagement Style**: Question-asker, storyteller, advisor, comedian
5. **Adaptability**: Do they mirror others or maintain consistent style?

Be thorough and specific. No character limits."""

    agent2_response = ""
    async for chunk in llm.chat_stream([{"role": "user", "content": agent2_prompt}], model=model):
        agent2_response += chunk
    
    analysis_data["communication_style"] = agent2_response
    
    # Agent 3: Psychological Profile (using selected framework)
    if progress_callback:
        await progress_callback(f"🧠 Agent 3: Running {analysis_type} analysis...")
    
    agent3_prompt = get_psychoanalysis_prompt(analysis_type, user_name, len(messages), message_samples, word_freq)
    
    agent3_response = ""
    async for chunk in llm.chat_stream([{"role": "user", "content": agent3_prompt}], model=model):
        agent3_response += chunk
    
    analysis_data["psychological_profile"] = agent3_response
    
    # Agent 4: Social Dynamics & Relationships
    if progress_callback:
        await progress_callback("👥 Agent 4: Analyzing social dynamics...")
    
    agent4_prompt = f"""Analyze {user_name}'s social dynamics and relationship patterns:

Messages: {len(messages):,}
Sample interactions:
{message_samples}

Provide detailed analysis of:
1. **Social Role**: Leader, supporter, mediator, entertainer, observer
2. **Interaction Patterns**: How they engage with different people
3. **Conflict Resolution**: How they handle disagreements
4. **Empathy & Emotional Intelligence**: Understanding others' perspectives
5. **Group Dynamics**: How they contribute to community
6. **Relationship Building**: Depth vs. breadth of connections

Be insightful and thorough. No character limits."""

    agent4_response = ""
    async for chunk in llm.chat_stream([{"role": "user", "content": agent4_prompt}], model=model):
        agent4_response += chunk
    
    analysis_data["social_dynamics"] = agent4_response
    
    # Agent 5: Behavioral Patterns & Habits
    if progress_callback:
        await progress_callback("🔄 Agent 5: Identifying behavioral patterns...")
    
    agent5_prompt = f"""Analyze {user_name}'s behavioral patterns and habits:

Messages: {len(messages):,}
Samples:
{message_samples}

Provide detailed analysis of:
1. **Activity Patterns**: When and how often they engage
2. **Consistency**: Reliable or sporadic presence
3. **Response Patterns**: Quick responder or thoughtful pauser
4. **Topic Preferences**: What they gravitate toward
5. **Behavioral Quirks**: Unique habits or rituals
6. **Evolution**: How their behavior has changed over time

Be specific with examples. No character limits."""

    agent5_response = ""
    async for chunk in llm.chat_stream([{"role": "user", "content": agent5_prompt}], model=model):
        agent5_response += chunk
    
    analysis_data["behavioral_patterns"] = agent5_response
    
    # Agent 6: Synthesis & Unique Insights
    if progress_callback:
        await progress_callback("✨ Agent 6: Synthesizing unique insights...")
    
    agent6_prompt = f"""Synthesize unique insights about {user_name}:

You have access to:
- Vocabulary analysis
- Communication style analysis
- Psychological profile ({analysis_type})
- Social dynamics analysis
- Behavioral patterns analysis

Provide:
1. **Core Identity**: Who are they at their essence?
2. **Standout Qualities**: What makes them unique?
3. **Hidden Depths**: Subtle patterns others might miss
4. **Growth Areas**: Potential for development
5. **Memorable Traits**: What people remember about them
6. **Overall Impression**: Holistic view of their personality

Be profound and insightful. This is the synthesis of everything. No character limits."""

    agent6_response = ""
    async for chunk in llm.chat_stream([{"role": "user", "content": agent6_prompt}], model=model):
        agent6_response += chunk
    
    analysis_data["synthesis_insights"] = agent6_response
    
    # Add metadata
    analysis_data["analysis_type"] = analysis_type
    analysis_data["word_frequency_data"] = word_freq
    
    return analysis_data

