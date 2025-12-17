from typing import TypedDict, Annotated, List, Literal, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from app.core.llm import get_llm
import operator

llm = get_llm()

class PrepareState(TypedDict):
    cv_text: str
    position: str
    instruction: str
    interview_details: str
    messages: Annotated[List[BaseMessage], operator.add]
    position_valid: bool
    cv_valid: bool
    cv_details: dict
    status: str # "validating", "generated", "refining"

def validate_position(state: PrepareState):
    print("---VALIDATE POSITION---")
    position = state.get("position", "")
    messages = state.get("messages", [])
    
    # If we are in a correction loop, the last message might be the new position
    if not state.get("position_valid") and messages and isinstance(messages[-1], HumanMessage):
        # Assume the user's last message is the corrected position
        position = messages[-1].content
        # Update state position for future steps
        state["position"] = position

    # LLM Validation
    prompt = f"""
    Is '{position}' a valid job position title? 
    It should be a specific role like "Software Engineer", "Product Manager", "Marketing Specialist", etc.
    It should not be gibberish or a full sentence unrelated to a job title.
    
    Answer strictly with "YES" or "NO".
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    is_valid = "YES" in response.content.strip().upper()
    
    if is_valid:
        return {"position_valid": True, "position": position}
    else:
        return {
            "position_valid": False, 
            "messages": [AIMessage(content=f"'{position}' doesn't look like a valid job position. Please enter the job position you are applying for (e.g., 'Senior Python Developer').")]
        }

def validate_cv(state: PrepareState):
    print("---VALIDATE CV---")
    cv_text = state.get("cv_text", "")
    messages = state.get("messages", [])
    import json
    import re
    
    # If we are in a correction loop, the last message might be the new CV text (if they pasted it)
    # But usually CV is a file. If they type, maybe they are explaining?
    # For now, let's assume if they type in this stage, they are providing details about their experience.
    if not state.get("cv_valid") and messages and isinstance(messages[-1], HumanMessage):
        # Append to CV text or replace? Let's append as additional context.
        cv_text += f"\n\nUser provided details: {messages[-1].content}"
        state["cv_text"] = cv_text

    if not cv_text or len(cv_text) < 50:
        return {
            "cv_valid": False,
            "messages": [AIMessage(content="Your CV content seems too sparse or invalid. Please provide a summary of your experience or upload a valid PDF.")]
        }
        
    # LLM Validation/Extraction
    prompt = f"""
    Analyze the following text to see if it contains professional experience or a resume.
    
    Text:
    {cv_text[:4000]}...
    
    If it is a valid resume or professional summary, extract the following details in JSON format:
    {{
        "is_valid": true,
        "name": "Candidate Name (or 'Unknown')",
        "skills": ["Skill1", "Skill2"],
        "experience_summary": "Brief summary of experience (max 2 sentences)"
    }}
    
    If it is NOT a valid resume, return JSON:
    {{
        "is_valid": false,
        "reason": "Why it is invalid"
    }}
    
    Return ONLY the JSON. Do not add markdown formatting.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()
    
    # Clean up standard markdown code blocks if present
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'^```\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails - assume valid if "is_valid": true string is present, but likely invalid json
        print(f"JSON Parse Error: {content}")
        # Simplistic fallback
        if '"is_valid": true' in content or '"is_valid":true' in content:
             data = {"is_valid": True, "name": "Unknown", "skills": [], "experience_summary": "Parsed from text"}
        else:
             data = {"is_valid": False}

    is_valid = data.get("is_valid", False)
    
    if is_valid:
        return {"cv_valid": True, "cv_text": cv_text, "cv_details": data}
    else:
        return {
            "cv_valid": False, 
            "messages": [AIMessage(content="I couldn't detect a valid professional background in your CV. Could you briefly describe your experience?")]
        }

def generate_plan(state: PrepareState):
    print("---GENERATE PLAN---")
    
    cv_details = state.get("cv_details", {})
    name = cv_details.get("name", "Candidate")
    skills = ", ".join(cv_details.get("skills", []))
    exp_summary = cv_details.get("experience_summary", "No summary available")
    
    prompt = f"""
    You are an expert technical interviewer named CleverMock.
    Based on the following inputs, generate a structured interview plan for a 10-minute interview.
    The plan must be realistic for a short 10-minute session.
    
    Candidate Name: {name}
    Position: {state['position']}
    Instructions: {state['instruction']}
    Candidate Skills: {skills}
    Candidate Experience: {exp_summary}
    
    CV Excerpt: {state['cv_text'][:1000]}...
    
    Generate a concise but comprehensive interview plan including:
    1. Key topics to cover (tailored to their actual skills)
    2. 2-3 initial questions (referencing their specific experience if possible)
    3. Evaluation criteria
    
    Format it nicely in Markdown.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    return {
        "interview_details": response.content, 
        "status": "generated",
        "messages": [AIMessage(content=response.content)] # Send the plan to the user
    }

def refine_plan(state: PrepareState):
    print("---REFINE PLAN---")
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    
    if not last_message or not isinstance(last_message, HumanMessage):
        return {} 

    prompt = f"""
    Current Interview Plan:
    {state['interview_details']}
    
    User Feedback:
    {last_message.content}
    
    Update the interview plan based on the feedback. Keep the format structured in Markdown.
    IMPORTANT: The interview duration MUST REMAIN STRICTLY 10 MINUTES. Do not change the time duration even if the user asks for it. Default to 10 minutes if unsure.
    Return the FULL updated plan.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    return {
        "interview_details": response.content, 
        "messages": [AIMessage(content=response.content)]
    }

def router(state: PrepareState):
    # Determine where to go based on state
    if not state.get("position_valid"):
        return "validate_position"
    if not state.get("cv_valid"):
        return "validate_cv"
    if state.get("status") == "generated" or state.get("interview_details"):
        return "refine_plan"
    return "generate_details"

# Build Graph
workflow = StateGraph(PrepareState)

workflow.add_node("validate_position", validate_position)
workflow.add_node("validate_cv", validate_cv)
workflow.add_node("generate_details", generate_plan)
workflow.add_node("refine_plan", refine_plan)

# We need a conditional entry point or a router node
# Let's use a dummy start node that routes
def start_node(state: PrepareState):
    return state

workflow.add_node("start", start_node)
workflow.set_entry_point("start")

workflow.add_conditional_edges(
    "start",
    router,
    {
        "validate_position": "validate_position",
        "validate_cv": "validate_cv",
        "generate_details": "generate_details",
        "refine_plan": "refine_plan"
    }
)

# After validate_position
def after_validate_position(state: PrepareState):
    if not state.get("position_valid"):
        return END # Stop and wait for user input
    # If valid, check CV
    if not state.get("cv_valid"):
        return "validate_cv"
    # If both valid (and we haven't generated yet), generate
    if not state.get("interview_details"):
        return "generate_details"
    return END

workflow.add_conditional_edges(
    "validate_position",
    after_validate_position,
    {
        END: END,
        "validate_cv": "validate_cv",
        "generate_details": "generate_details"
    }
)

# After validate_cv
def after_validate_cv(state: PrepareState):
    if not state.get("cv_valid"):
        return END # Stop and wait for user input
    # If valid, generate
    if not state.get("interview_details"):
        return "generate_details"
    return END

workflow.add_conditional_edges(
    "validate_cv",
    after_validate_cv,
    {
        END: END,
        "generate_details": "generate_details"
    }
)

workflow.add_edge("generate_details", END)
workflow.add_edge("refine_plan", END)

app_graph = workflow.compile()
