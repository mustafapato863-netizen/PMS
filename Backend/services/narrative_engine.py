def generate_narrative(summary: dict, metric: str, direction: str = "higher") -> str:
    """
    Generates a deterministic narrative based on the provided metrics and direction.
    direction can be "higher" (e.g., Revenue) or "lower" (e.g., Costs).
    """
    if not summary:
        return "No sufficient data available to generate a narrative."

    record_count = summary.get("record_count", 0)
    if record_count == 0:
        return f"There are no records available for {metric} in this period."

    # A simple deterministic sentence builder
    sentences = []

    # 1. Volume
    sentences.append(f"A total of {record_count} records were processed for this reporting period.")

    # 2. Performance overview (if grade distribution exists)
    grades = summary.get("grade_distribution", {})
    if grades:
        top_grade = max(grades.items(), key=lambda x: x[1])
        sentences.append(f"The most frequent grade was '{top_grade[0]}' with {top_grade[1]} occurrences.")

    # 3. Status overview
    statuses = summary.get("status_distribution", {})
    if statuses:
        top_status = max(statuses.items(), key=lambda x: x[1])
        sentences.append(f"The predominant status observed was '{top_status[0]}'.")

    return " ".join(sentences)
