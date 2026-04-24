from a2a.types import Role, TaskState

from spec4.a2a_bus import create_task, make_message, update_task


class TestMakeMessage:
    def test_role_is_preserved(self):
        msg = make_message(Role.user, "Hello")
        assert msg.role == Role.user

    def test_text_content_in_parts(self):
        msg = make_message(Role.user, "Hello world")
        assert len(msg.parts) == 1
        assert msg.parts[0].root.text == "Hello world"

    def test_message_ids_are_unique(self):
        m1 = make_message(Role.user, "Hi")
        m2 = make_message(Role.user, "Hi")
        assert m1.message_id != m2.message_id

    def test_optional_task_and_context_ids(self):
        msg = make_message(Role.agent, "Response", task_id="t1", context_id="ctx1")
        assert msg.task_id == "t1"
        assert msg.context_id == "ctx1"

    def test_agent_role(self):
        msg = make_message(Role.agent, "Reply")
        assert msg.role == Role.agent


class TestCreateTask:
    def test_task_stored_in_session(self):
        session = {"a2a_tasks": {}}
        task = create_task("ctx-1", make_message(Role.user, "Start"), session)
        assert task.id in session["a2a_tasks"]

    def test_task_starts_submitted(self):
        session = {"a2a_tasks": {}}
        task = create_task("ctx-1", make_message(Role.user, "Start"), session)
        assert task.status.state == TaskState.submitted

    def test_task_context_id(self):
        session = {"a2a_tasks": {}}
        task = create_task("ctx-abc", make_message(Role.user, "Start"), session)
        assert task.context_id == "ctx-abc"

    def test_task_history_has_initial_message(self):
        session = {"a2a_tasks": {}}
        task = create_task("ctx-1", make_message(Role.user, "Start"), session)
        assert len(task.history) == 1

    def test_multiple_tasks_have_unique_ids(self):
        session = {"a2a_tasks": {}}
        t1 = create_task("ctx-1", make_message(Role.user, "T1"), session)
        t2 = create_task("ctx-1", make_message(Role.user, "T2"), session)
        assert t1.id != t2.id
        assert len(session["a2a_tasks"]) == 2


class TestUpdateTask:
    def _make_task(self):
        session = {"a2a_tasks": {}}
        task = create_task("ctx-1", make_message(Role.user, "Start"), session)
        return task, session

    def test_updates_state(self):
        task, session = self._make_task()
        updated = update_task(task.id, TaskState.completed, session=session)
        assert updated.status.state == TaskState.completed

    def test_appends_message_to_history(self):
        task, session = self._make_task()
        reply = make_message(Role.agent, "Done")
        updated = update_task(task.id, TaskState.completed, message=reply, session=session)
        assert len(updated.history) == 2

    def test_no_message_leaves_history_length_unchanged(self):
        task, session = self._make_task()
        updated = update_task(task.id, TaskState.completed, session=session)
        assert len(updated.history) == 1

    def test_session_reflects_updated_task(self):
        task, session = self._make_task()
        update_task(task.id, TaskState.completed, session=session)
        assert session["a2a_tasks"][task.id].status.state == TaskState.completed
