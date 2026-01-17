from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.friend import FriendRequest, Notification
from pydantic import BaseModel
from typing import Optional


router = APIRouter(prefix="/api/friends", tags=["friends"])


class FriendRequestCreate(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None


class FriendRequestResponse(BaseModel):
    id: int
    requester_id: int
    recipient_id: int
    status: str
    created_at: datetime


class NotificationResponse(BaseModel):
    id: int
    type: str
    message: str
    data: Optional[str]
    is_read: bool
    created_at: datetime


@router.get("/search")
async def search_users(
    q: str = Query("", min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users = (
        db.query(User)
        .filter(User.username.ilike(f"%{q}%"))
        .filter(User.id != current_user.id)
        .limit(10)
        .all()
    )
    return [
        {
            "id": user.id,
            "username": user.username,
            "profile_picture": user.profile_picture,
        }
        for user in users
    ]


@router.post("/request", response_model=FriendRequestResponse)
async def create_friend_request(
    payload: FriendRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.username and not payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or user_id required",
        )

    target_user = None
    if payload.user_id:
        target_user = db.query(User).filter(User.id == payload.user_id).first()
    if payload.username:
        target_user = db.query(User).filter(User.username == payload.username).first()

    if not target_user or target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )

    existing = (
        db.query(FriendRequest)
        .filter(
            ((FriendRequest.requester_id == current_user.id) & (FriendRequest.recipient_id == target_user.id))
            | ((FriendRequest.requester_id == target_user.id) & (FriendRequest.recipient_id == current_user.id))
        )
        .first()
    )

    if existing and existing.status in ["pending", "accepted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Friend request already exists",
        )

    friend_request = FriendRequest(
        requester_id=current_user.id,
        recipient_id=target_user.id,
        status="pending",
    )
    db.add(friend_request)

    notification = Notification(
        user_id=target_user.id,
        type="friend_request",
        message=f"{current_user.username} sent you a friend request",
        data=str(friend_request.requester_id),
        is_read=False,
    )
    db.add(notification)
    db.commit()
    db.refresh(friend_request)
    return friend_request


@router.get("/requests")
async def get_friend_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requests = (
        db.query(FriendRequest)
        .filter(FriendRequest.recipient_id == current_user.id)
        .filter(FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc())
        .all()
    )
    return [
        {
            "id": fr.id,
            "requester_id": fr.requester_id,
            "recipient_id": fr.recipient_id,
            "status": fr.status,
            "created_at": fr.created_at,
            "requester": {
                "id": fr.requester.id,
                "username": fr.requester.username,
                "profile_picture": fr.requester.profile_picture,
            },
        }
        for fr in requests
    ]


@router.post("/requests/{request_id}/accept")
async def accept_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    friend_request = (
        db.query(FriendRequest)
        .filter(FriendRequest.id == request_id)
        .filter(FriendRequest.recipient_id == current_user.id)
        .first()
    )
    if not friend_request or friend_request.status != "pending":
        raise HTTPException(status_code=404, detail="Request not found")

    friend_request.status = "accepted"
    friend_request.responded_at = datetime.utcnow()

    notification = Notification(
        user_id=friend_request.requester_id,
        type="friend_accept",
        message=f"{current_user.username} accepted your friend request",
        data=str(current_user.id),
        is_read=False,
    )
    db.add(notification)
    db.commit()
    return {"status": "ok"}


@router.post("/requests/{request_id}/decline")
async def decline_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    friend_request = (
        db.query(FriendRequest)
        .filter(FriendRequest.id == request_id)
        .filter(FriendRequest.recipient_id == current_user.id)
        .first()
    )
    if not friend_request or friend_request.status != "pending":
        raise HTTPException(status_code=404, detail="Request not found")

    friend_request.status = "declined"
    friend_request.responded_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.get("/list")
async def list_friends(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requests = (
        db.query(FriendRequest)
        .filter(FriendRequest.status == "accepted")
        .filter(
            (FriendRequest.requester_id == current_user.id)
            | (FriendRequest.recipient_id == current_user.id)
        )
        .all()
    )
    friend_ids = set()
    for fr in requests:
        if fr.requester_id == current_user.id:
            friend_ids.add(fr.recipient_id)
        else:
            friend_ids.add(fr.requester_id)

    friends = db.query(User).filter(User.id.in_(friend_ids)).all() if friend_ids else []
    return [
        {
            "id": user.id,
            "username": user.username,
            "profile_picture": user.profile_picture,
        }
        for user in friends
    ]


@router.get("/notifications")
async def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .filter(Notification.is_read == False)
        .count()
    )
    return {
        "unread_count": unread_count,
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "message": n.message,
                "data": n.data,
                "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in notifications
        ],
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id)
        .filter(Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()
    return {"status": "ok"}