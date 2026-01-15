"""
Validation Agent - Validates recommendations before returning to user.

This agent ensures recommendations are actionable, non-conflicting,
and align with business rules.
"""
from typing import Dict, Any, List
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class ValidationAgent:
    """
    Validation Agent for validating recommendations.

    Ensures recommendations are:
    - Actionable and specific
    - Non-conflicting
    - Aligned with business rules
    - Have sufficient data quality
    """

    def __init__(self):
        """Initialize Validation Agent."""
        pass

    def validate_recommendations(
        self,
        recommendations: List[Dict[str, str]],
        diagnosis: Dict[str, Any],
        agent_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate recommendations.

        Args:
            recommendations: List of recommendations to validate
            diagnosis: Diagnosis results
            agent_results: Results from specialist agents

        Returns:
            Dict with:
            - valid: bool - Whether recommendations pass validation
            - validated_recommendations: List[Dict] - Validated recommendations
            - warnings: List[str] - Validation warnings
            - errors: List[str] - Validation errors
        """
        validated = []
        warnings = []
        errors = []

        # Validation Rule 1: Check for required fields
        for i, rec in enumerate(recommendations):
            if not isinstance(rec, dict):
                errors.append(f"Recommendation {i+1}: Invalid format")
                continue

            if "action" not in rec or not rec["action"]:
                errors.append(f"Recommendation {i+1}: Missing action")
                continue

            if "priority" not in rec:
                warnings.append(f"Recommendation {i+1}: Missing priority, defaulting to medium")
                rec["priority"] = "medium"

            if "reason" not in rec:
                warnings.append(f"Recommendation {i+1}: Missing reason")

            validated.append(rec)

        # Validation Rule 2: Check for conflicts
        actions = [rec.get("action", "").lower() for rec in validated]
        for i, action1 in enumerate(actions):
            for j, action2 in enumerate(actions[i+1:], start=i+1):
                if self._are_conflicting(action1, action2):
                    warnings.append(
                        f"Recommendations {i+1} and {j+1} may conflict: "
                        f"'{validated[i]['action'][:50]}...' vs '{validated[j]['action'][:50]}...'"
                    )

        # Validation Rule 3: Check for vague recommendations
        for i, rec in enumerate(validated):
            action = rec.get("action", "")
            if len(action.split()) < 5:
                warnings.append(f"Recommendation {i+1}: Action may be too vague")

            # Check for vague verbs
            vague_verbs = ["improve", "optimize", "enhance", "review", "consider"]
            if any(verb in action.lower() for verb in vague_verbs) and "specific" not in action.lower():
                warnings.append(f"Recommendation {i+1}: Consider making action more specific")

        # Validation Rule 4: Check severity alignment
        severity = diagnosis.get("severity", "medium")
        high_priority_count = sum(1 for rec in validated if rec.get("priority") == "high")

        if severity in ["critical", "high"] and high_priority_count == 0:
            warnings.append("Severity is high but no high-priority recommendations - consider prioritizing")

        if severity in ["low", "medium"] and high_priority_count > 2:
            warnings.append("Severity is low/medium but many high-priority recommendations - may be over-reacting")

        # Validation Rule 5: Limit recommendations
        if len(validated) > 7:
            warnings.append(f"Too many recommendations ({len(validated)}), limiting to top 7")
            validated = validated[:7]

        # Determine overall validation status
        valid = len(errors) == 0 and len(validated) > 0

        logger.info(
            "Validation complete",
            valid=valid,
            validated_count=len(validated),
            warnings_count=len(warnings),
            errors_count=len(errors)
        )

        return {
            "valid": valid,
            "validated_recommendations": validated,
            "warnings": warnings,
            "errors": errors
        }

    def _are_conflicting(self, action1: str, action2: str) -> bool:
        """Check if two actions are conflicting."""
        # Simple conflict detection
        conflict_pairs = [
            (["increase", "scale", "raise"], ["decrease", "reduce", "lower"]),
            (["pause", "stop"], ["start", "launch", "enable"]),
            (["expand", "broaden"], ["narrow", "focus", "limit"]),
        ]

        for positive_words, negative_words in conflict_pairs:
            has_positive_1 = any(word in action1 for word in positive_words)
            has_negative_1 = any(word in action1 for word in negative_words)
            has_positive_2 = any(word in action2 for word in positive_words)
            has_negative_2 = any(word in action2 for word in negative_words)

            # If one action has positive words and other has negative words
            if (has_positive_1 and has_negative_2) or (has_negative_1 and has_positive_2):
                # Check if they're about the same thing (simple heuristic)
                words1 = set(action1.split())
                words2 = set(action2.split())
                common_words = words1.intersection(words2)
                if len(common_words) > 2:  # Share at least 2 words
                    return True

        return False


# Global instance
validation_agent = ValidationAgent()
