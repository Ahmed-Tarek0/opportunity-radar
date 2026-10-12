from __future__ import annotations

import re

# Synonym/alias dictionary: maps aliases to canonical names
SKILL_SYNONYMS: dict[str, str] = {
    # JavaScript ecosystem
    "js": "javascript",
    "javascript": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "node": "node.js",
    "nodejs": "node.js",
    "node.js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "react": "react",
    "vuejs": "vue.js",
    "vue": "vue.js",
    "vue.js": "vue.js",
    "angular": "angular",
    "angularjs": "angular",
    "nextjs": "next.js",
    "next.js": "next.js",
    "next": "next.js",
    # Python ecosystem
    "python": "python",
    "py": "python",
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
    "fast-api": "fastapi",
    # Java
    "java": "java",
    "spring": "spring",
    "spring boot": "spring boot",
    "springboot": "spring boot",
    # Databases
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mongo": "mongodb",
    "mongodb": "mongodb",
    "redis": "redis",
    "elasticsearch": "elasticsearch",
    "elastic": "elasticsearch",
    # Cloud & Infra
    "aws": "aws",
    "amazon web services": "aws",
    "gcp": "gcp",
    "google cloud": "gcp",
    "azure": "azure",
    "microsoft azure": "azure",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "terraform": "terraform",
    "ansible": "ansible",
    # ML/AI
    "tensorflow": "tensorflow",
    "tf": "tensorflow",
    "pytorch": "pytorch",
    "torch": "pytorch",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "pandas": "pandas",
    "numpy": "numpy",
    # CI/CD
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    "github actions": "github actions",
    "gitlab ci": "gitlab ci",
    "jenkins": "jenkins",
    # Other
    "git": "git",
    "graphql": "graphql",
    "grpc": "grpc",
    "rest": "rest api",
    "restful": "rest api",
    "rest api": "rest api",
    "sql": "sql",
    "linux": "linux",
    "html": "html",
    "css": "css",
    "tailwind": "tailwind css",
    "tailwind css": "tailwind css",
    "c++": "c++",
    "cpp": "c++",
    "c#": "c#",
    "csharp": "c#",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "kafka": "kafka",
    "rabbitmq": "rabbitmq",
    "celery": "celery",
    "airflow": "apache airflow",
    "apache airflow": "apache airflow",
    "pyspark": "pyspark",
    "spark": "apache spark",
    "apache spark": "apache spark",
    "dbt": "dbt",
    "mlflow": "mlflow",
    "hugging face": "hugging face",
    "transformers": "hugging face",
    # AI/ML/Data Domains
    "ai": "artificial intelligence",
    "artificial intelligence": "artificial intelligence",
    "ml": "machine learning",
    "machine learning": "machine learning",
    "dl": "deep learning",
    "deep learning": "deep learning",
    "cv": "computer vision",
    "computer vision": "computer vision",
    "nlp": "natural language processing",
    "natural language processing": "natural language processing",
    "cs": "computer science",
    "computer science": "computer science",
    "ds": "data science",
    "data science": "data science",
    "data analysis": "data analysis",
    "data analytics": "data analysis",
    "bi": "business intelligence",
    "business intelligence": "business intelligence",
    "eda": "exploratory data analysis",
    "exploratory data analysis": "exploratory data analysis",
    "image processing": "computer vision",
    "digital image processing": "computer vision",
    "neural networks": "deep learning",
    "deep neural networks": "deep learning",
}

# Explicitly NOT synonymous — must not be merged
DISTINCT_SKILLS = frozenset({
    ("java", "javascript"),
    ("javascript", "java"),
    ("react", "angular"),
    ("angular", "react"),
    ("react", "vue.js"),
    ("python", "fastapi"),
})

# Domain Knowledge Implication Graph:
# If a job requires the key, any of the values in the set proves the candidate has this competency.
SKILL_IMPLICATIONS: dict[str, set[str]] = {
    "computer vision": {
        "image processing", "digital image processing", "opencv", "computer vision",
        "object detection", "yolo", "cnn", "convolutional neural networks",
        "image segmentation", "edge detection", "spatial filtering", "image manipulation",
    },
    "artificial intelligence": {
        "artificial intelligence", "ai", "machine learning", "ml", "deep learning",
        "neural networks", "tensorflow", "keras", "pytorch", "computer vision",
        "nlp", "natural language processing", "scikit-learn", "data science",
        "artificial intelligence degree", "ai degree",
    },
    "machine learning": {
        "machine learning", "ml", "deep learning", "tensorflow", "keras", "pytorch",
        "scikit-learn", "supervised learning", "unsupervised learning", "hyperparameter tuning",
        "feature engineering", "feature selection", "random forest", "xgboost",
        "model evaluation", "gridsearchcv",
    },
    "deep learning": {
        "deep learning", "neural networks", "deep neural network", "dnn", "tensorflow",
        "keras", "pytorch", "cnn", "rnn", "transformers", "lstm",
    },
    "computer science": {
        "computer science", "cs", "artificial intelligence", "data structures",
        "algorithms", "data structures & algorithms", "oop", "object-oriented programming",
        "c++", "software engineering", "computer science degree", "ai degree",
    },
    "data science": {
        "data science", "machine learning", "deep learning", "predictive modeling",
        "eda", "exploratory data analysis", "feature engineering", "scikit-learn",
        "tensorflow", "pandas", "numpy", "statistics",
    },
    "data analysis": {
        "data analysis", "data analytics", "power bi", "tableau", "excel",
        "eda", "exploratory data analysis", "pandas", "numpy", "data visualization",
        "business intelligence", "bi", "sql", "dashboard",
    },
    "business intelligence": {
        "business intelligence", "bi", "power bi", "tableau", "dwh", "data warehouse",
        "etl", "data modeling", "dashboard", "reporting",
    },
    "databases": {
        "database", "databases", "sql", "postgresql", "mysql", "sqlite", "mongodb",
        "redis", "dwh", "rdbms", "database management",
    },
    "software engineering": {
        "software engineering", "software development", "git", "github", "oop",
        "design patterns", "clean code", "unit testing", "ci/cd",
    },
}


def normalize_skill(skill: str) -> str:
    """Normalize a skill name to its canonical form."""
    cleaned = re.sub(r"\s+", " ", skill.lower().strip())
    cleaned = re.sub(r"[^a-z0-9#+./\s-]", "", cleaned).strip()
    return SKILL_SYNONYMS.get(cleaned, cleaned)


def are_same_skill(skill_a: str, skill_b: str) -> bool:
    """Check if two skills are the same after normalization."""
    norm_a = normalize_skill(skill_a)
    norm_b = normalize_skill(skill_b)

    if (norm_a, norm_b) in DISTINCT_SKILLS:
        return False

    return norm_a == norm_b



# Skills so generic they should NEVER be considered a real match signal.
# e.g. "Engineering" alone doesn't tell us anything — it matches everything.
TOO_GENERIC_SKILLS: frozenset[str] = frozenset({
    "engineering", "technology", "management", "administration",
    "communication", "teamwork", "problem solving", "leadership",
    "analytical skills", "analytical", "skills", "experience",
    "knowledge", "ability", "understanding", "proficiency",
    "excellence", "excellence skills", "time management",
})


def is_skill_satisfied(requirement: str, candidate_knowledge: list[str]) -> bool:
    """Intelligently check if a required skill is satisfied by the candidate's knowledge base.

    Checks:
    1. Direct match (are_same_skill)
    2. Implication match (e.g. Image Processing satisfies Computer Vision, TensorFlow satisfies AI)
    3. Phrase/substring containment (e.g. 'Python programming' satisfied by 'Python')
    """
    req_norm = normalize_skill(requirement)

    # Immediately reject if the requirement itself is too generic to be meaningful
    if req_norm in TOO_GENERIC_SKILLS:
        return False

    # 1. Direct or synonym match (skip if candidate skill is too generic)
    for cand in candidate_knowledge:
        cand_norm = normalize_skill(cand)
        if cand_norm in TOO_GENERIC_SKILLS:
            continue
        if are_same_skill(requirement, cand):
            return True

    # 2. Domain implication match
    implications = SKILL_IMPLICATIONS.get(req_norm)
    if implications:
        for cand in candidate_knowledge:
            cand_norm = normalize_skill(cand)
            if cand_norm in TOO_GENERIC_SKILLS:
                continue
            if cand_norm in implications or any(imp in cand.lower() for imp in implications):
                return True

    # 3. Substring & phrase containment (skip generic terms to avoid false positives)
    req_clean = req_norm.replace("-", " ")
    for cand in candidate_knowledge:
        cand_norm = normalize_skill(cand).replace("-", " ")
        if cand_norm in TOO_GENERIC_SKILLS:
            continue
        if (norm_pair := (req_norm, cand_norm)) in DISTINCT_SKILLS or (cand_norm, req_norm) in DISTINCT_SKILLS:
            continue
        # If candidate skill is a major keyword in the requirement (e.g. 'python' in 'python 3 development')
        if len(cand_norm) >= 4 and cand_norm in req_clean:
            return True
        # If requirement is a major keyword in candidate evidence (e.g. 'power bi' in 'power bi dashboard')
        if len(req_clean) >= 4 and req_clean in cand_norm:
            return True

    return False
