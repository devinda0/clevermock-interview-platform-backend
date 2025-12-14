from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from uuid import UUID
from app.models.chat import Conversation, Message
from app.models.user import User
from app.api.deps import get_current_user
from app.core.graph import app_graph
from app.core.llm import get_llm
from pypdf import PdfReader
import io
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()

@router.post("/start")
async def start_preparation(
    file: UploadFile = File(...),
    position: str = Form(...),
    instruction: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    # 1. Extract text from PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    content = await file.read()
    pdf = PdfReader(io.BytesIO(content))
    cv_text = ""
    for page in pdf.pages:
        cv_text += page.extract_text()
        
    # 2. Initialize Conversation
    conversation = Conversation(
        title=f"Interview Prep: {position}",
        user_id=str(current_user.id),
        participants=[str(current_user.id)], 
        metadata={
            "cv_text": cv_text,
            "position": position,
            "instruction": instruction,
            "status": "initialized",
            "position_valid": False,
            "cv_valid": False,
            "interview_details": ""
        }
    )
    await conversation.insert()
    
    # 3. Run Initial Graph
    initial_state = {
        "cv_text": cv_text,
        "position": position,
        "instruction": instruction,
        "messages": [],
        "position_valid": False,
        "cv_valid": False,
        "interview_details": "",
        "status": "initialized"
    }
    
    result = await app_graph.ainvoke(initial_state)
    
    # 4. Update Conversation with Result
    # We need to serialize messages to store in DB (or just store text content)
    # For metadata, we keep the state fields
    conversation.metadata.update({
        "position_valid": result.get("position_valid"),
        "cv_valid": result.get("cv_valid"),
        "interview_details": result.get("interview_details"),
        "status": result.get("status"),
        "position": result.get("position"), # In case it was updated
        "cv_text": result.get("cv_text"), # In case it was updated
        "cv_details": result.get("cv_details")
    })
    
    # Handle messages returned by graph
    graph_messages = result.get("messages", [])
    if graph_messages:
        last_msg = graph_messages[-1]
        if isinstance(last_msg, AIMessage):
            msg = Message(content=last_msg.content, sender_type="ai")
            conversation.messages.append(msg)
            conversation.updated_at = msg.created_at
        
    await conversation.save()
    
    # Return the last AI message content as interview_details if it's the plan, 
    # or the validation error message.
    response_text = ""
    if graph_messages and isinstance(graph_messages[-1], AIMessage):
        response_text = graph_messages[-1].content
    
    return {
        "conversation_id": str(conversation.id),
        "status": result.get("status"),
        "interview_details": response_text 
    }

@router.post("/{conversation_id}/refine")
async def refine_details(conversation_id: UUID, message: str = Form(...)):
    conversation = await Conversation.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    # Reconstruct state from metadata
    state = conversation.metadata
    
    # Add user message to state
    # We need to convert existing DB messages to LangChain messages if we wanted full history,
    # but for now let's just pass the new message as the "input" for the graph to react to.
    # The graph logic uses `messages[-1]` to get the user input.
    
    current_messages = [HumanMessage(content=message)]
    state["messages"] = current_messages
    
    # Run Graph
    result = await app_graph.ainvoke(state)
    
    # Update Conversation
    conversation.metadata.update({
        "position_valid": result.get("position_valid"),
        "cv_valid": result.get("cv_valid"),
        "interview_details": result.get("interview_details"),
        "status": result.get("status"),
        "position": result.get("position"),
        "cv_text": result.get("cv_text"),
        "cv_details": result.get("cv_details")
    })
    
    # Save messages to DB
    user_msg = Message(content=message, sender_type="user")
    conversation.messages.append(user_msg)
    
    graph_messages = result.get("messages", [])
    response_text = ""
    
    if graph_messages:
        last_msg = graph_messages[-1]
        if isinstance(last_msg, AIMessage):
            ai_msg = Message(content=last_msg.content, sender_type="ai")
            conversation.messages.append(ai_msg)
            conversation.updated_at = ai_msg.created_at
            response_text = last_msg.content
            
    await conversation.save()
    
    return {
        "interview_details": response_text
    }

@router.post("/{conversation_id}/accept")
async def accept_details(conversation_id: UUID):
    conversation = await Conversation.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    # Sanitize the interview details
    current_details = conversation.metadata.get("interview_details", "")
    if current_details:
        try:
            llm = get_llm()
            prompt = f"""
            The following text is an interview plan generated by an AI. It might contain conversational filler at the beginning or end (e.g., "Here is the plan", "Okay, I've updated it").
            
            Input Text:
            {current_details}
            
            Task: 
            Extract ONLY the markdown content of the interview plan. 
            Remove any introductory or concluding conversational remarks.
            Ensure it starts directly with the markdown headers/content.
            Return ONLY the cleaned markdown.
            """
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            conversation.metadata["interview_details"] = response.content
        except Exception as e:
            # If LLM sanitation fails (e.g. rate limit), just proceed with original text
            print(f"Warning: Failed to sanitize interview plan: {e}")
            pass

    conversation.metadata["status"] = "accepted"
    await conversation.save()
    
    return {"status": "accepted"}
