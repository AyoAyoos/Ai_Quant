"""Conversation and Project management endpoints.

Provides CRUD operations for conversations and projects with proper
user ownership enforcement.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.auth import AuthenticatedUser, get_or_create_user, verify_user
from app.ids import canonical_uuid_or_404
from app.models import Conversation, Message, Project, MessageRole, ConversationStatus
from app.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectOut,
    ConversationCreate,
    ConversationUpdate,
    ConversationOut,
    ConversationDetailOut,
    MessageOut,
    MoveConversationIn,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ============================================================
# Project Endpoints
# ============================================================

@router.post("/projects", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Create a new project for the authenticated user."""
    current = get_or_create_user(db, user)
    project = Project(user_id=current.id, name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat() if project.created_at else "",
        updated_at=project.updated_at.isoformat() if project.updated_at else None,
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """List all projects for the authenticated user."""
    current = get_or_create_user(db, user)
    projects = db.query(Project).filter(Project.user_id == current.id).order_by(Project.updated_at.desc()).all()
    return [
        ProjectOut(
            id=p.id,
            user_id=p.user_id,
            name=p.name,
            description=p.description,
            created_at=p.created_at.isoformat() if p.created_at else "",
            updated_at=p.updated_at.isoformat() if p.updated_at else None,
        )
        for p in projects
    ]


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Update a project's name or description."""
    current = get_or_create_user(db, user)
    detail = "Project not found"
    canonical = canonical_uuid_or_404(project_id, detail)
    project = db.query(Project).filter(Project.id == canonical, Project.user_id == current.id).first()
    if not project:
        raise HTTPException(status_code=404, detail=detail)

    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description

    db.commit()
    db.refresh(project)
    return ProjectOut(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat() if project.created_at else "",
        updated_at=project.updated_at.isoformat() if project.updated_at else None,
    )


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    move_conversations: bool = True,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Delete a project.

    If move_conversations=True (default), conversations in the project
    are moved to the unassigned section (project_id = NULL).
    If move_conversations=False, conversations are deleted along with the project.
    """
    current = get_or_create_user(db, user)
    detail = "Project not found"
    canonical = canonical_uuid_or_404(project_id, detail)
    project = db.query(Project).filter(Project.id == canonical, Project.user_id == current.id).first()
    if not project:
        raise HTTPException(status_code=404, detail=detail)

    if move_conversations:
        # Move conversations to unassigned (project_id = NULL)
        db.query(Conversation).filter(Conversation.project_id == project.id).update(
            {Conversation.project_id: None, Conversation.updated_at: func.now()},
            synchronize_session=False,
        )
    else:
        # Delete conversations and their messages (cascade)
        db.query(Conversation).filter(Conversation.project_id == project.id).delete(synchronize_session=False)

    db.delete(project)
    db.commit()
    return {"status": "deleted"}


# ============================================================
# Conversation Endpoints
# ============================================================

@router.post("", response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Create a new conversation, optionally within a project."""
    current = get_or_create_user(db, user)

    # Validate project ownership if provided
    if payload.project_id is not None:
        project_detail = "Project not found"
        project_canonical = canonical_uuid_or_404(payload.project_id, project_detail)
        project = db.query(Project).filter(Project.id == project_canonical, Project.user_id == current.id).first()
        if not project:
            raise HTTPException(status_code=404, detail=project_detail)
        project_id = project_canonical
    else:
        project_id = None

    conversation = Conversation(
        user_id=current.id,
        project_id=project_id,
        title=payload.title or "New conversation",
        status=ConversationStatus.active,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_to_out(db, conversation)


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    project_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """List all conversations for the authenticated user.

    Optional filters:
    - project_id: filter by project (use 'unassigned' for conversations without a project)
    - status: filter by status (active, archived)
    """
    current = get_or_create_user(db, user)
    query = db.query(Conversation).filter(Conversation.user_id == current.id)

    if project_id == "unassigned":
        query = query.filter(Conversation.project_id.is_(None))
    elif project_id is not None:
        canonical = canonical_uuid_or_404(project_id, "Project not found")
        query = query.filter(Conversation.project_id == canonical)

    if status:
        try:
            status_enum = ConversationStatus(status)
            query = query.filter(Conversation.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    conversations = query.order_by(Conversation.updated_at.desc()).all()
    return [_conversation_to_out(db, c) for c in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Get a conversation with its full message history."""
    current = get_or_create_user(db, user)
    detail = "Conversation not found"
    canonical = canonical_uuid_or_404(conversation_id, detail)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == canonical, Conversation.user_id == current.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail=detail)

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
        .all()
    )

    return ConversationDetailOut(
        conversation=_conversation_to_out(db, conversation),
        messages=[
            MessageOut(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role.value,
                content=m.content,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Update a conversation's title, project, or status."""
    current = get_or_create_user(db, user)
    detail = "Conversation not found"
    canonical = canonical_uuid_or_404(conversation_id, detail)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == canonical, Conversation.user_id == current.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail=detail)

    if payload.title is not None:
        conversation.title = payload.title

    if payload.project_id is not None:
        if payload.project_id == "unassigned":
            conversation.project_id = None
        else:
            project_detail = "Project not found"
            project_canonical = canonical_uuid_or_404(payload.project_id, project_detail)
            project = db.query(Project).filter(Project.id == project_canonical, Project.user_id == current.id).first()
            if not project:
                raise HTTPException(status_code=404, detail=project_detail)
            conversation.project_id = project_canonical

    if payload.status is not None:
        try:
            conversation.status = ConversationStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {payload.status}")

    db.commit()
    db.refresh(conversation)
    return _conversation_to_out(db, conversation)


@router.post("/{conversation_id}/move", response_model=ConversationOut)
def move_conversation(
    conversation_id: str,
    payload: MoveConversationIn,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Move a conversation to a different project (or unassigned)."""
    current = get_or_create_user(db, user)
    detail = "Conversation not found"
    canonical = canonical_uuid_or_404(conversation_id, detail)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == canonical, Conversation.user_id == current.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail=detail)

    if payload.project_id is None or payload.project_id == "unassigned":
        conversation.project_id = None
    else:
        project_detail = "Project not found"
        project_canonical = canonical_uuid_or_404(payload.project_id, project_detail)
        project = db.query(Project).filter(Project.id == project_canonical, Project.user_id == current.id).first()
        if not project:
            raise HTTPException(status_code=404, detail=project_detail)
        conversation.project_id = project_canonical

    db.commit()
    db.refresh(conversation)
    return _conversation_to_out(db, conversation)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Delete a conversation and all its messages."""
    current = get_or_create_user(db, user)
    detail = "Conversation not found"
    canonical = canonical_uuid_or_404(conversation_id, detail)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == canonical, Conversation.user_id == current.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail=detail)

    db.delete(conversation)
    db.commit()
    return {"status": "deleted"}


@router.post("/{conversation_id}/archive", response_model=ConversationOut)
def archive_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Archive a conversation."""
    current = get_or_create_user(db, user)
    detail = "Conversation not found"
    canonical = canonical_uuid_or_404(conversation_id, detail)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == canonical, Conversation.user_id == current.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail=detail)

    conversation.status = ConversationStatus.archived
    db.commit()
    db.refresh(conversation)
    return _conversation_to_out(db, conversation)


@router.post("/{conversation_id}/restore", response_model=ConversationOut)
def restore_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(verify_user),
):
    """Restore an archived conversation."""
    current = get_or_create_user(db, user)
    detail = "Conversation not found"
    canonical = canonical_uuid_or_404(conversation_id, detail)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == canonical, Conversation.user_id == current.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail=detail)

    conversation.status = ConversationStatus.active
    db.commit()
    db.refresh(conversation)
    return _conversation_to_out(db, conversation)


# ============================================================
# Helper Functions
# ============================================================

def _conversation_to_out(db: Session, conversation: Conversation) -> ConversationOut:
    """Convert Conversation model to ConversationOut schema with message count."""
    message_count = db.query(func.count(Message.id)).filter(Message.conversation_id == conversation.id).scalar() or 0
    return ConversationOut(
        id=conversation.id,
        user_id=conversation.user_id,
        project_id=conversation.project_id,
        title=conversation.title,
        status=conversation.status.value,
        created_at=conversation.created_at.isoformat() if conversation.created_at else "",
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else "",
        message_count=message_count,
    )