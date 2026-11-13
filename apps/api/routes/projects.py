"""Projetos: subjects with their conversations, pages and files."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from apps.api.deps import CurrentUser, DbSession
from apps.api.routes.artifacts import ArtifactOut, artifact_out
from apps.api.routes.attachments import AttachmentOut, attachment_out
from core import projects
from infrastructure.database.models import Artifact, Attachment, Conversation, Message, Project

router = APIRouter(prefix="/projects", tags=["projects"])

MAX_PROJECTS = 100


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    conversations: int = 0
    pages: int = 0
    files: int = 0


class ProjectConversationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    title: str


class ProjectDetailOut(ProjectOut):
    conversation_list: list[ProjectConversationOut] = []
    page_list: list[ArtifactOut] = []
    file_list: list[AttachmentOut] = []


def own_project(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projeto não encontrado")
    return project


def _counts(db: Session, project: Project) -> dict[str, int]:
    conversations = select(Conversation.id).where(Conversation.project_id == project.id)
    return {
        "conversations": db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.project_id == project.id)
        )
        or 0,
        "pages": db.scalar(
            select(func.count())
            .select_from(Artifact)
            .where(Artifact.conversation_id.in_(conversations), Artifact.status == "ready")
        )
        or 0,
        "files": db.scalar(
            select(func.count())
            .select_from(Attachment)
            .join(Message, Attachment.message_id == Message.id)
            .where(Message.conversation_id.in_(conversations))
        )
        or 0,
    }


def _out(db: Session, project: Project) -> ProjectOut:
    return ProjectOut(
        id=project.id, name=project.name, created_at=project.created_at, **_counts(db, project)
    )


@router.get("")
def list_projects(db: DbSession, user: CurrentUser) -> list[ProjectOut]:
    rows = db.scalars(
        select(Project).where(Project.owner_user_id == user.id).order_by(Project.created_at.desc())
    )
    return [_out(db, p) for p in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, db: DbSession, user: CurrentUser) -> ProjectOut:
    name = projects.clean_name(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Dê um nome ao projeto")
    count = db.scalar(
        select(func.count()).select_from(Project).where(Project.owner_user_id == user.id)
    )
    if (count or 0) >= MAX_PROJECTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Projetos demais; apague algum")
    project = Project(owner_user_id=user.id, name=name)
    db.add(project)
    db.commit()
    return _out(db, project)


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProjectDetailOut:
    project = own_project(db, user.id, project_id)
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.project_id == project.id)
        .order_by(Conversation.created_at.desc())
    ).all()
    ids = [c.id for c in conversations]
    names = projects.titles(db, ids)
    pages = db.scalars(
        select(Artifact)
        .where(Artifact.conversation_id.in_(ids), Artifact.status == "ready")
        .order_by(Artifact.created_at.desc())
    ).all()
    files = db.scalars(
        select(Attachment)
        .join(Message, Attachment.message_id == Message.id)
        .where(Message.conversation_id.in_(ids))
        .order_by(Attachment.created_at.desc())
    ).all()
    return ProjectDetailOut(
        **_out(db, project).model_dump(),
        conversation_list=[
            ProjectConversationOut(
                id=c.id, created_at=c.created_at, title=names.get(c.id, "Conversa nova")
            )
            for c in conversations
        ],
        page_list=[artifact_out(a) for a in pages],
        file_list=[attachment_out(a) for a in files],
    )


@router.patch("/{project_id}")
def rename_project(
    project_id: uuid.UUID, body: ProjectIn, db: DbSession, user: CurrentUser
) -> ProjectOut:
    project = own_project(db, user.id, project_id)
    name = projects.clean_name(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Dê um nome ao projeto")
    project.name = name
    db.commit()
    return _out(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """The project goes; its conversations, pages and files stay, outside any project."""
    project = own_project(db, user.id, project_id)
    db.execute(
        update(Conversation).where(Conversation.project_id == project.id).values(project_id=None)
    )
    db.delete(project)
    db.commit()
