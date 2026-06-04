from typing import List, Dict

# Static subject/topic → curated video mapping.
# Keys must be lowercase and match the topic strings stored in weak_topics.
video_resources: Dict[str, List[Dict[str, str]]] = {
    # --- Data Structures & Algorithms ---
    "recursion": [
        {"title": "Recursion Basics", "url": "https://www.youtube.com/watch?v=ngCos392W4w", "level": "beginner"},
        {"title": "Advanced Recursion Problems", "url": "https://www.youtube.com/watch?v=IJDJ0kBx2LM", "level": "advanced"},
    ],
    "arrays": [
        {"title": "Arrays Explained", "url": "https://www.youtube.com/watch?v=55l-aZ7_F24", "level": "beginner"},
        {"title": "Array Interview Problems", "url": "https://www.youtube.com/watch?v=RBSGKlAvoiM", "level": "advanced"},
    ],
    "linked lists": [
        {"title": "Linked Lists for Beginners", "url": "https://www.youtube.com/watch?v=F8AbOfQwl1c", "level": "beginner"},
        {"title": "Linked List Problems", "url": "https://www.youtube.com/watch?v=Hj_rA0dhr2I", "level": "advanced"},
    ],
    "trees": [
        {"title": "Binary Trees Explained", "url": "https://www.youtube.com/watch?v=fAAZixBzIAI", "level": "beginner"},
        {"title": "Tree Traversal Deep Dive", "url": "https://www.youtube.com/watch?v=9RHO6jU--GU", "level": "advanced"},
    ],
    "graphs": [
        {"title": "Graph Theory Basics", "url": "https://www.youtube.com/watch?v=tWVWeAqZ0WU", "level": "beginner"},
        {"title": "BFS and DFS Explained", "url": "https://www.youtube.com/watch?v=pcKY4hjDrxk", "level": "beginner"},
        {"title": "Dijkstra's Algorithm", "url": "https://www.youtube.com/watch?v=GazC3A4OQTE", "level": "advanced"},
    ],
    "sorting": [
        {"title": "Sorting Algorithms Visualized", "url": "https://www.youtube.com/watch?v=kgBjXUE_Nwc", "level": "beginner"},
        {"title": "Merge Sort vs Quick Sort", "url": "https://www.youtube.com/watch?v=es2T6KY45cA", "level": "advanced"},
    ],
    "dynamic programming": [
        {"title": "Dynamic Programming Introduction", "url": "https://www.youtube.com/watch?v=oBt53YbR9Kk", "level": "beginner"},
        {"title": "DP Patterns for Interviews", "url": "https://www.youtube.com/watch?v=oBt53YbR9Kk", "level": "advanced"},
    ],
    "stacks": [
        {"title": "Stack Data Structure", "url": "https://www.youtube.com/watch?v=KInG04mAjO0", "level": "beginner"},
    ],
    "queues": [
        {"title": "Queue Data Structure", "url": "https://www.youtube.com/watch?v=HcB_5KFzIJc", "level": "beginner"},
    ],
    "hashing": [
        {"title": "Hash Tables Explained", "url": "https://www.youtube.com/watch?v=KyUTuwz_b7Q", "level": "beginner"},
        {"title": "Hash Collisions and Resolution", "url": "https://www.youtube.com/watch?v=mFY0J5W8Udk", "level": "advanced"},
    ],
    "binary search": [
        {"title": "Binary Search Explained", "url": "https://www.youtube.com/watch?v=P3YID7liBug", "level": "beginner"},
        {"title": "Binary Search on Answer", "url": "https://www.youtube.com/watch?v=GU7DpgHINWQ", "level": "advanced"},
    ],
    # --- Mathematics ---
    "calculus": [
        {"title": "Calculus Fundamentals", "url": "https://www.youtube.com/watch?v=WUvTyaaNkzM", "level": "beginner"},
        {"title": "Derivatives and Integrals", "url": "https://www.youtube.com/watch?v=rAof9Ld5sOg", "level": "advanced"},
    ],
    "algebra": [
        {"title": "Algebra Basics", "url": "https://www.youtube.com/watch?v=NybHckSEQBI", "level": "beginner"},
        {"title": "Linear Algebra Full Course", "url": "https://www.youtube.com/watch?v=JnTa9XtvmfI", "level": "advanced"},
    ],
    "probability": [
        {"title": "Probability for Beginners", "url": "https://www.youtube.com/watch?v=uzkc-qNVoOk", "level": "beginner"},
        {"title": "Conditional Probability", "url": "https://www.youtube.com/watch?v=_IgyaD7vOOA", "level": "advanced"},
    ],
    "statistics": [
        {"title": "Statistics Introduction", "url": "https://www.youtube.com/watch?v=xxpc-HPKN28", "level": "beginner"},
        {"title": "Statistical Inference", "url": "https://www.youtube.com/watch?v=tFRXsngz4UQ", "level": "advanced"},
    ],
}


def get_video_recommendations(
    weak_topics: List[str],
    proficiency_score: float,
) -> List[Dict[str, str]]:
    """Return curated video recommendations for the top weak topic.

    proficiency_score must be in 0-1 range (normalize before calling).
    Returns beginner videos only when proficiency < 0.5, all levels otherwise.
    Returns [] when weak_topics is empty or topic has no mapped videos.
    """
    if not weak_topics:
        return []

    topic = weak_topics[0].lower().strip()
    videos = video_resources.get(topic, [])

    if not videos:
        return []

    if proficiency_score < 0.5:
        return [v for v in videos if v["level"] == "beginner"]
    return videos
