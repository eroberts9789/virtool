import concurrent.futures
import multiprocessing
import os
import pytest
import queue

import virtool.file_manager


@pytest.fixture
def test_watcher_instance(tmpdir):
    files_path = str(tmpdir.mkdir("files"))
    watch_path = str(tmpdir.mkdir("watch"))

    watcher = virtool.file_manager.Watcher(files_path, watch_path, multiprocessing.Queue())

    watcher.start()

    yield watcher

    watcher.terminate()


@pytest.fixture
def test_manager_instance(loop, test_motor, test_dispatch, tmpdir, test_queue):

    files_path = str(tmpdir.mkdir("files"))
    watch_path = str(tmpdir.mkdir("watch"))

    executor = concurrent.futures.ThreadPoolExecutor()

    manager = virtool.file_manager.Manager(loop, executor, test_motor, test_dispatch, files_path, watch_path)

    return manager


class TestWatcher:

    async def test_alive(self, test_watcher_instance):
        assert test_watcher_instance.queue.get(block=True, timeout=2) == "alive"

    async def test_create(self, test_watcher_instance):
        # This will be an 'alive' message
        test_watcher_instance.queue.get(block=True, timeout=2)

        path = os.path.join(test_watcher_instance.files_path, "test.dat")

        with open(path, "w") as handle:
            handle.write("hello world")

        first_message = test_watcher_instance.queue.get(block=True, timeout=3)

        assert first_message["action"] == "create"

        file = dict(first_message["file"])
        file.pop("modify")

        assert file == {
            "filename": "test.dat",
            "size": 11
        }

        action = "modify"
        next_message = None

        while action == "modify":
            next_message = test_watcher_instance.queue.get(block=True, timeout=3)
            action = next_message["action"]

        assert next_message["action"] == "close"

        file = dict(first_message["file"])
        file.pop("modify")

        assert file == {
            "filename": "test.dat",
            "size": 11
        }

    async def test_delete(self, test_watcher_instance):
        path = os.path.join(test_watcher_instance.files_path, "test.dat")

        with open(path, "w") as handle:
            handle.write("hello world")

        # This will be an 'alive' message
        test_watcher_instance.queue.get(block=True, timeout=2)

        os.remove(path)

        message = test_watcher_instance.queue.get(block=True, timeout=3)

        assert message == {
            "action": "delete",
            "file": {
                "filename": "test.dat"
            }
        }

    @pytest.mark.parametrize("move", [True, False], ids=["move", "write"])
    @pytest.mark.parametrize("fastq", [True, False], ids=["fastq", "not_fastq"])
    async def test_watch(self, move, fastq, tmpdir, test_watcher_instance):
        target_watch_path = os.path.join(test_watcher_instance.watch_path, "test.fq" if fastq else "test.dat")

        if move:
            path = os.path.join(str(tmpdir), "test.fq" if fastq else "test.dat")
        else:
            path = target_watch_path

        # This will be an 'alive' message
        test_watcher_instance.queue.get(block=True, timeout=2)

        with open(path, "w") as f:
            f.write("hello world")

        if move:
            os.rename(path, target_watch_path)

        if fastq:
            message = test_watcher_instance.queue.get(block=True, timeout=1)

            assert message["action"] == "watch"

            file = dict(message["file"])
            file.pop("modify")

            assert file == {
                "filename": "test.fq",
                "size": 11
            }
        else:
            with pytest.raises(queue.Empty):
                test_watcher_instance.queue.get(block=True, timeout=1)

    async def test_watch_delete(self, test_watcher_instance):
        """
        Make sure no exception is raised when deleting from the watch folder.

        """
        path = os.path.join(test_watcher_instance.watch_path, "test.fq")

        # This will be an 'alive' message
        test_watcher_instance.queue.get(block=True, timeout=2)

        with open(path, "w") as f:
            f.write("hello world")

        test_watcher_instance.queue.get(block=True, timeout=3)

        os.remove(path)


class TestManager:

    async def test_create(self, test_manager_instance):
        """
        Test that a ``create`` action results in the ``created`` field on the matching file document in the database
        to be set to ``True``.

        """
        await test_manager_instance.db.files.insert_one({
            "_id": "test.dat"
        })

        # Do this so the the clean task doesn't remove the database record.
        with open(os.path.join(test_manager_instance.files_path, "test.dat"), "w") as f:
            f.write("hello world")

        test_manager_instance.queue.put("alive")

        test_manager_instance.queue.put({
            "action": "create",
            "file": {
                "filename": "test.dat",
                "size": 50
            }
        })

        await test_manager_instance.start()
        await test_manager_instance.close()

        assert await test_manager_instance.db.files.find_one() == {
            "_id": "test.dat",
            "created": True
        }

    async def test_close(self, test_manager_instance):
        """
        Test that a ``close`` action results in ``ready`` being set to ``True`` on the matching file document in the
        database.

        """
        await test_manager_instance.db.files.insert_one({
            "_id": "test.dat",
            "expires_at": None,
            "created": True
        })

        # Do this so the the clean task doesn't remove the database record.
        with open(os.path.join(test_manager_instance.files_path, "test.dat"), "w") as f:
            f.write("hello world")

        test_manager_instance.queue.put("alive")

        test_manager_instance.queue.put({
            "action": "close",
            "file": {
                "filename": "test.dat",
                "size": 100
            }
        })

        await test_manager_instance.start()
        await test_manager_instance.close()

        assert test_manager_instance.dispatch.stub.call_args[0] == (
            "files",
            "update",
            {
                "id": "test.dat",
                "ready": True,
                "size": 100
            }
        )

        assert await test_manager_instance.db.files.find_one() == {
            "_id": "test.dat",
            "expires_at": None,
            "created": True,
            "ready": True,
            "size": 100
        }

    async def test_delete(self, test_manager_instance):
        """
        Test that a ``delete`` action from the Watcher results in the deletion of the matching file document in the
        database.

        """
        await test_manager_instance.db.files.insert_one({
            "_id": "test.dat",
            "created": True,
            "ready": True,
            "size": 100
        })

        test_manager_instance.queue.put("alive")

        test_manager_instance.queue.put({
            "action": "delete",
            "file": {
                "filename": "test.dat"
            }
        })

        await test_manager_instance.start()
        await test_manager_instance.close()

        assert await test_manager_instance.db.files.count() == 0

    async def test_watch(self, test_manager_instance, static_time):
        """
        Test that a ``watch`` action results in the creation of a file document and copying of the file to the
        files path. We'll assume that the file document is updated with ``{"created": True, "ready": True}`` afterwards.

        """
        assert await test_manager_instance.db.files.count() == 0

        with open(os.path.join(test_manager_instance.watch_path, "test.fq"), "w") as f:
            f.write("hello world")

        test_manager_instance.queue.put("alive")

        test_manager_instance.queue.put({
            "action": "watch",
            "file": {
                "filename": "test.fq",
                "size": 50
            }
        })

        await test_manager_instance.start()
        await test_manager_instance.close()

        assert await test_manager_instance.db.files.find_one({}, {"_id": False}) == {
            "name": "test.fq",
            "type": "reads",
            "expires_at": None,
            "created": False,
            "uploaded_at": static_time,
            "reserved": False,
            "ready": False,
            "user": None
        }

        assert os.listdir(test_manager_instance.watch_path) == list()
        assert os.listdir(test_manager_instance.files_path)[0].endswith("test.fq")

    async def test_start_and_close(self, tmpdir, loop, test_motor, test_dispatch):
        """
        Test the starting and closing the file manager work as designed. The manager should wait for the watch to
        send and "alive" message on the Queue before returning. This results in the ``alive`` attribute being set to
        ``True`` on the manager.

        Closing the manager should result in ``alive`` being set to ``False``.

        """
        manager = virtool.file_manager.Manager(
            loop,
            concurrent.futures.ThreadPoolExecutor(),
            test_motor,
            test_dispatch,
            str(tmpdir.mkdir("files")),
            str(tmpdir.mkdir("watch"))
        )

        assert manager.alive is False

        await manager.start()

        assert manager.alive is True

        await manager.close()

        assert manager.alive is False

    async def test_clean_dir(self, tmpdir, loop, test_motor, test_dispatch):
        await test_motor.files.insert_one({
            "_id": "test.dat",
            "created": True
        })

        files = tmpdir.mkdir("files")

        for filename in ("test.dat", "invalid.dat"):
            files.join(filename).write(filename)

        manager = virtool.file_manager.Manager(
            loop,
            concurrent.futures.ThreadPoolExecutor(),
            test_motor,
            test_dispatch,
            str(files),
            str(tmpdir.mkdir("watch"))
        )

        await manager.start()
        await manager.close()

        assert os.listdir(str(files)) == ["test.dat"]

    async def test_clean_db(self, tmpdir, loop, test_motor, test_dispatch):

        await test_motor.files.insert_many([
            {"_id": "test.dat", "created": True},
            {"_id": "invalid.dat", "created": True}
        ])

        files = tmpdir.mkdir("files")

        file_a = files.join("test.dat")
        file_a.write("hello world")

        manager = virtool.file_manager.Manager(
            loop,
            concurrent.futures.ThreadPoolExecutor(),
            test_motor,
            test_dispatch,
            str(files),
            str(tmpdir.mkdir("watch"))
        )

        await manager.start()
        await manager.close()

        assert list(await test_motor.files.find().to_list(None)) == [{"_id": "test.dat", "created": True}]