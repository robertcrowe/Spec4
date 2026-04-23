from __future__ import annotations

import uuid

from a2a.types import (
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)


def make_message(role: Role, text: str, task_id: str | None = None, context_id: str | None = None) -> Message:
    """Create an A2A Message with a single TextPart."""
    return Message(
        role=role,
        message_id=str(uuid.uuid4()),
        parts=[Part(root=TextPart(text=text))],
        task_id=task_id,
        context_id=context_id,
    )


def create_task(context_id: str, initial_message: Message, session: dict) -> Task:
    """Create a new A2A Task in submitted state and store it in session."""
    task_id = str(uuid.uuid4())
    msg = Message(
        role=initial_message.role,
        message_id=initial_message.message_id,
        parts=initial_message.parts,
        task_id=task_id,
        context_id=context_id,
    )
    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.submitted),
        history=[msg],
    )
    session["a2a_tasks"][task_id] = task
    return task


def update_task(task_id: str, state: TaskState, message: Message | None = None, session: dict = None) -> Task:
    """Update a task's state and optionally append a message to its history."""
    task: Task = session["a2a_tasks"][task_id]
    new_history = list(task.history or [])
    if message is not None:
        new_history.append(message)
    updated = task.model_copy(
        update={
            "status": TaskStatus(state=state, message=message),
            "history": new_history,
        }
    )
    session["a2a_tasks"][task_id] = updated
    return updated
