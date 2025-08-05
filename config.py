# ==============================================================================
# File: config.py
# Description: Contains configuration for the Gemini model and prompts.
# ==============================================================================
def config():
    """Returns the model name, prompts, and other settings."""
    model = "gemini-2.5-flash" #2.5 is latest version strictly do not change until we have better than this.
    
    # New: The duration in seconds that triggers chunking.
    # Files longer than this will be split into segments of this duration.
    # Set to 30 minutes (30 * 60 = 1800 seconds).
    max_duration_seconds = 1800

    # New: A dedicated prompt for transcribing audio chunks
    transcription_prompt = """
    You are a highly accurate audio transcription service. Your task is to transcribe the provided audio segment word-for-word.
    - Do not add any commentary, interpretation, or summary.
    - Preserve the exact wording, including filler words (e.g., "um," "uh"), pauses, and grammatical errors.
    - The output should be only the raw text of the speech from the audio.
    - Stricktly do not output things like "Here's the transcription of the audio segment: "
    """
    
    summary_prompt = """
    You are an expert summarizer specializing in crafting professional minutes of meetings and executive summaries. Please analyze the following call recording and generate a concise, well-structured, and formal summary. Ensure the output reflects a tone appropriate for stakeholders or senior management.
    Instructions: 
    Review the video thoroughly; feel free to replay it multiple times to ensure complete understanding.
    Focus on capturing key discussion points, decisions made, action items, participants involved, and any timelines or follow-ups discussed.
    Structure the summary in a clear, professional format — ideally with bullet points or short sections under headers (e.g., Meeting Objective, Key Discussions, Decisions, Action Items, Next Steps).
    Maintain an objective tone and avoid subjective interpretation.
    Output Format: Provide the summary in a clean and professional style suitable for corporate documentation or official records. Important: avoid writting things like "Here's the minutes of the meeting as per your request which is professionally written" instead directly write what's asked and also avoid ending statements such as "Let me know if you’d like a lighter version for internal use or a template for recurring use across meetings." or anything similar your response will directly be copy pasted in docs and emailed to c-suite executives, so it should be ready to use without further editing.
    pls make sure to avoid writing things like "Certainly. Here's a summary of the call recording: ..." stright 
    "**Call Summary**
**Date:** October 26, 2023
**Participants:** David, Aman
"
this was an example, it could be starting as minutes of meeting. or somerhign which sounds good.
    """

    return model, summary_prompt, max_duration_seconds, transcription_prompt