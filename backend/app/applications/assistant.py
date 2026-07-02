import os
from typing import Dict, Any

class ApplyAssistant:
    @staticmethod
    def prepare_clipboard_payload(package: Dict[str, Any], job_title: str, company: str) -> str:
        """
        Formats the generated package into a single readable clipboard buffer.
        """
        bullets_text = "\n".join([f"- {b}" for b in package.get("resume_bullets", [])])
        key_points_text = "\n".join([f"- {kp}" for kp in package.get("key_points", [])])
        payload = f"""=== APPLICATION PACKAGE FOR {job_title.upper()} AT {company.upper()} ===

SUGGESTED EMAIL SUBJECT:
{package.get('suggested_subject_line', '')}

KEY HIGHLIGHTS:
{key_points_text}

TAILORED RESUME BULLETS:
{bullets_text}

COVER LETTER:
{package.get('cover_letter', '')}
==================================================
"""
        return payload
