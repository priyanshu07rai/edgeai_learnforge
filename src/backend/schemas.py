"""
schemas.py — Pydantic output schemas for Ollama structured decoding (format=Schema.model_json_schema()).
Guarantees 100% syntactically valid JSON output from local LLMs.
"""
from typing import Literal
from pydantic import BaseModel, Field


class Flashcard(BaseModel):
    question: str = Field(description="Active-recall conceptual question")
    answer: str = Field(description="Clear, concise factual answer")
    type: Literal["conceptual", "application", "misconception"] = Field(
        description="Pedagogical type of the flashcard"
    )
    hint: str = Field(description="Single short sentence nudging toward the answer")


class FlashcardSet(BaseModel):
    cards: list[Flashcard] = Field(description="List of 6-8 active recall flashcards")


class QuizQuestion(BaseModel):
    question: str = Field(description="Reasoning-based multiple choice question")
    options: list[str] = Field(description="Exactly 4 options labeled A, B, C, D")
    correct_answer: str = Field(description="Single letter corresponding to the correct option: A, B, C, or D")
    explanation: str = Field(description="Detailed educational explanation of why the answer is correct")


class QuizSet(BaseModel):
    quiz: list[QuizQuestion] = Field(description="List of 5 reasoning-based MCQs")


class KnowledgeLayer(BaseModel):
    definition: str = Field(description="One clear textbook definition sentence")
    explanation: str = Field(description="2-4 cohesive sentences explaining mechanism and importance")
    key_points: list[str] = Field(description="Exactly 3 key facts as bullet points")
    summary: str = Field(description="One sentence high-level summary")
