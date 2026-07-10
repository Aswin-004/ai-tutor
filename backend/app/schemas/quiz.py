from pydantic import BaseModel, Field


class QuizGenerateRequest(BaseModel):
    # Every other user-supplied text field in the app has a length cap
    # (ChatRequest.message, FeedbackRequest.message, SubjectSwitch.subject) -
    # this one didn't. Added for consistency; any well-formed topic a real
    # client would send is far under 200 chars, so this rejects only
    # previously-nonsensical input (e.g. empty string), not legitimate use.
    topic: str = Field(..., min_length=1, max_length=200)


class QuizSubmitRequest(BaseModel):
    topic: str
    score: int
    total_questions: int  # required — client must send actual question count
