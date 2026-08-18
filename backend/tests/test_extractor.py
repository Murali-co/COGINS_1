import pytest
from app.resume.extractor import SkillExtractor

def test_extract_skills_case_insensitive():
    text = "Experience with Python, JavaScript, and React."
    skills = SkillExtractor.extract_skills(text)
    
    extracted_names = [s["skill"] for s in skills]
    assert "Python" in extracted_names
    assert "JavaScript" in extracted_names
    assert "React" in extracted_names

def test_extract_skills_common_words_avoidance():
    # "go" used as a verb should not trigger Go skill
    text_with_verb = "I like to go shopping. We go there often."
    skills = SkillExtractor.extract_skills(text_with_verb)
    extracted_names = [s["skill"] for s in skills]
    assert "Go" not in extracted_names
    
    # "Go" capitalized as the programming language should be matched
    text_with_skill = "Experienced in Go development and Kubernetes."
    skills_with_go = SkillExtractor.extract_skills(text_with_skill)
    extracted_names_go = [s["skill"] for s in skills_with_go]
    assert "Go" in extracted_names_go
    assert "Kubernetes" in extracted_names_go

def test_extract_skills_single_letter_avoidance():
    # Standalone lowercase "r" as a letter/bullet should not match R programming
    text_with_letter = "Please select option a or r from the menu."
    skills = SkillExtractor.extract_skills(text_with_letter)
    extracted_names = [s["skill"] for s in skills]
    assert "R" not in extracted_names
    
    # Capitalized "R" should match the programming language
    text_with_skill = "Data analysis using R and Python."
    skills_with_r = SkillExtractor.extract_skills(text_with_skill)
    extracted_names_r = [s["skill"] for s in skills_with_r]
    assert "R" in extracted_names_r
