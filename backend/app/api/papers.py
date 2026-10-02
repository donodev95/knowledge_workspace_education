from uuid import UUID
from backend.app.auth.dependencies import CurrentUserDep
from backend.app.repositories.papers import get_a_paper
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.app.db.session import SessionDep
from backend.app.core.errors import ApplicationError
from backend.app.models import Paper
from backend.app.schemas.paper import PaperCreate, PaperPublic

router = APIRouter(prefix='/papers', tags=['papers'])


@router.post('', response_model=PaperPublic, status_code=201)
async def create_paper(payload: PaperCreate, session: SessionDep, user: CurrentUserDep):
    paper = Paper(owner_id=user.id, **payload.model_dump())
    session.add(paper)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApplicationError(409, 'paper_exists', 'Paper code already exists') from exc
    await session.refresh(paper)
    return paper


@router.get('', response_model=list[PaperPublic])
async def list_papers(session: SessionDep, user: CurrentUserDep):
    return (await session.execute(select(Paper).where(Paper.owner_id == user.id).order_by(Paper.code))).scalars().all()


@router.get('/{paper_id}', response_model=PaperPublic)
async def get_paper(paper_id: UUID, session: SessionDep, user: CurrentUserDep):
    return await get_a_paper(session, paper_id, user.id)
