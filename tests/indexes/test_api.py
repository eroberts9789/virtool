import pytest
from aiohttp.test_utils import make_mocked_coro


async def test_find(mocker, snapshot, spawn_client, static_time):
    client = await spawn_client(authorize=True)

    await client.db.indexes.insert_many([
        {
            "_id": "bar",
            "version": 1,
            "created_at": static_time.datetime,
            "manifest": {
                "foo": 2
            },
            "ready": False,
            "has_files": True,
            "job": {
                "id": "bar"
            },
            "reference": {
                "id": "bar"
            },
            "user": {
                "id": "bob"
            },
            "sequence_otu_map": {
                "foo": "bar_otu"
            }
        },
        {
            "_id": "foo",
            "version": 0,
            "created_at": static_time.datetime,
            "manifest": {
                "foo": 2
            },
            "ready": False,
            "has_files": True,
            "job": {
                "id": "foo"
            },
            "reference": {
                "id": "foo"
            },
            "user": {
                "id": "bob"
            },
            "sequence_otu_map": {
                "foo": "foo_otu"
            }
        }
    ])

    await client.db.history.insert_many([
        {
            "_id": "0",
            "index": {
                "id": "bar"
            },
            "otu": {
                "id": "baz"
            }
        },
        {
            "_id": "1",
            "index": {
                "id": "foo"
            },
            "otu": {
                "id": "baz"
            }
        },
        {
            "_id": "2",
            "index": {
                "id": "bar"
            },
            "otu": {
                "id": "bat"
            }
        },
        {
            "_id": "3",
            "index": {
                "id": "bar"
            },
            "otu": {
                "id": "baz"
            }
        },
        {
            "_id": "4",
            "index": {
                "id": "bar"
            },
            "otu": {
                "id": "bad"
            }
        },
        {
            "_id": "5",
            "index": {
                "id": "foo"
            },
            "otu": {
                "id": "boo"
            }
        }
    ])

    mocker.patch("virtool.indexes.db.get_unbuilt_stats", make_mocked_coro({
        "total_otu_count": 123,
        "change_count": 12,
        "modified_otu_count": 3
    }))

    resp = await client.get("/api/indexes")

    assert resp.status == 200
    snapshot.assert_match(await resp.json())


@pytest.mark.parametrize("error", [None, "404"])
async def test_get(error, mocker, snapshot, resp_is, spawn_client, static_time):
    client = await spawn_client(authorize=True)

    if not error:
        await client.db.indexes.insert_one({
            "_id": "foobar",
            "version": 0,
            "created_at": static_time.datetime,
            "ready": False,
            "has_files": True,
            "user": {
                "id": "test"
            },
            "job": {
                "id": "sj82la"
            }
        })

    await client.db.history.insert_many([
        {
            "_id": "0",
            "index": {
                "id": "foobar"
            },
            "otu": {
                "id": "foo"
            }
        },
        {
            "_id": "1",
            "index": {
                "id": "foobar"
            },
            "otu": {
                "id": "baz"
            }
        },
        {
            "_id": "2",
            "index": {
                "id": "bar"
            },
            "otu": {
                "id": "bat"
            }
        }
    ])

    contributors = [
        {
            "id": "fred",
            "count": 1
        },
        {
            "id": "igboyes",
            "count": 3
        }
    ]

    otus = [
        {
            "id": "kjs8sa99",
            "name": "Foo",
            "change_count": 1
        },
        {
            "id": "zxbbvngc",
            "name": "Test",
            "change_count": 3
        }
    ]

    m_get_contributors = mocker.patch("virtool.indexes.db.get_contributors", make_mocked_coro(contributors))
    m_get_otus = mocker.patch("virtool.indexes.db.get_otus", make_mocked_coro(otus))

    resp = await client.get("/api/indexes/foobar")

    if error:
        assert await resp_is.not_found(resp)
        return

    m_get_contributors.assert_called_with(
        client.db,
        "foobar"
    )

    m_get_otus.assert_called_with(
        client.db,
        "foobar"
    )

    assert resp.status == 200
    snapshot.assert_match(await resp.json())


class TestCreate:

    async def test(self, mocker, spawn_client, static_time, test_random_alphanumeric, check_ref_right, resp_is):
        client = await spawn_client(authorize=True)

        client.app["settings"].update({
            "sm_proc": 1,
            "sm_mem": 2
        })

        await client.db.references.insert_one({
            "_id": "foo"
        })

        # Insert unbuilt changes to prevent initial check failure.
        await client.db.history.insert_one({
            "index": {
                "id": "unbuilt",
                "version": "unbuilt"
            },
            "reference": {
                "id": "foo"
            }
        })

        # Define mocks.
        m_job_manager = client.app["jobs"] = mocker.Mock()
        mocker.patch.object(m_job_manager, "close", make_mocked_coro())
        m_enqueue = mocker.patch.object(m_job_manager, "enqueue", make_mocked_coro())

        m_get_next_version = mocker.patch("virtool.indexes.db.get_next_version", new=make_mocked_coro(9))

        m_create_manifest = mocker.patch("virtool.references.db.get_manifest", new=make_mocked_coro("manifest"))

        # Make API call.
        resp = await client.post("/api/refs/foo/indexes")

        if not check_ref_right:
            assert await resp_is.insufficient_rights(resp)
            return

        assert resp.status == 201

        expected_id = test_random_alphanumeric.history[1]

        expected_job_id = test_random_alphanumeric.history[2]

        expected = {
            "_id": expected_id,
            "version": 9,
            "created_at": static_time.datetime,
            "ready": False,
            "has_files": True,
            "manifest": "manifest",
            "job": {
                "id": expected_job_id
            },
            "reference": {
                "id": "foo"
            },
            "user": {
                "id": "test"
            }
        }

        assert resp.headers["Location"] == "/api/indexes/{}".format(expected_id)

        assert await client.db.jobs.find_one() == {
            "_id": test_random_alphanumeric.history[2],
            "args": {
                "index_id": "u3cuwaoq",
                "index_version": 9,
                "manifest": "manifest",
                "ref_id": "foo",
                "user_id": "test"
            },
            "mem": 2,
            "proc": 1,
            "status": [
                {
                    "error": None,
                    "progress": 0,
                    "stage": None,
                    "state": "waiting",
                    "timestamp": static_time.datetime
                }
            ],
            "task": "build_index",
            "user": {
                "id": "test"
            }
        }

        assert await client.db.indexes.find_one() == expected

        expected["id"] = expected.pop("_id")
        expected["created_at"] = static_time.iso

        assert await resp.json() == expected

        m_get_next_version.assert_called_with(client.db, "foo")

        m_create_manifest.assert_called_with(client.db, "foo")

        # Check that appropriate mocks were called.
        m_enqueue.assert_called_with(expected_job_id)

    @pytest.mark.parametrize("error", [None, "400_unbuilt", "400_unverified", "409_running"])
    async def test_checks(self, error, resp_is, spawn_client, check_ref_right):
        client = await spawn_client(authorize=True)

        await client.db.references.insert_one({
            "_id": "foo"
        })

        if error == "409_running":
            await client.db.indexes.insert_one({
                "ready": False,
                "reference": {
                    "id": "foo"
                }
            })

        if error == "400_unverified":
            await client.db.otus.insert_one({
                "verified": False,
                "reference": {
                    "id": "foo"
                }
            })

        resp = await client.post("/api/refs/foo/indexes", {})

        if not check_ref_right:
            assert await resp_is.insufficient_rights(resp)
            return

        if error == "400_unverified":
            assert await resp_is.bad_request(resp, "There are unverified OTUs")
            return

        if error == "400_unbuilt":
            assert await resp_is.bad_request(resp, "There are no unbuilt changes")
            return

        if error == "409_running":
            assert await resp_is.conflict(resp, "Index build already in progress")
            return


@pytest.mark.parametrize("error", [None, "404"])
async def test(error, spawn_client, resp_is):
    client = await spawn_client(authorize=True)

    if not error:
        await client.db.indexes.insert_one({
            "_id": "foobar",
            "version": 0
        })

    await client.db.history.insert_many([
        {
            "_id": "zxbbvngc.0",
            "otu": {
                "version": 0,
                "name": "Test",
                "id": "zxbbvngc"
            },
            "user": {
                "id": "igboyes"
            },
            "index": {
                "version": 0,
                "id": "foobar"
            }
        },
        {
            "_id": "zxbbvngc.1",
            "otu": {
                "version": 1,
                "name": "Test",
                "id": "zxbbvngc"
            },
            "user": {
                "id": "igboyes"
            },
            "method_name": "add_isolate",
            "index": {
                "version": 0,
                "id": "foobar"
            }
        },
        {
            "_id": "zxbbvngc.2",
            "otu": {
                "version": 2,
                "name": "Test",
                "id": "zxbbvngc"
            },
            "user": {
                "id": "igboyes"
            },
            "method_name": "add_isolate",
            "index": {
                "version": 0,
                "id": "foobar"
            }
        },
        {
            "_id": "kjs8sa99.3",
            "otu": {
                "version": 3,
                "name": "Foo",
                "id": "kjs8sa99"
            },
            "user": {
                "id": "fred"
            },
            "method_name": "add_sequence",
            "index": {
                "version": 0,
                "id": "foobar"
            }
        },
        {
            "_id": "test_1",
            "index": {
                "id": "baz"
            }

        },
        {
            "_id": "test_2",
            "index": {
                "id": "baz"
            }
        }
    ])

    resp = await client.get("/api/indexes/foobar/history")

    if error:
        assert await resp_is.not_found(resp)
        return

    assert resp.status == 200

    assert await resp.json() == {
        "found_count": 4,
        "page": 1,
        "page_count": 1,
        "per_page": 25,
        "total_count": 6,
        "documents": [
            {
                "id": "kjs8sa99.3",
                "index": {
                    "id": "foobar",
                    "version": 0
                },
                "method_name": "add_sequence",
                "user": {
                    "id": "fred"
                },
                "otu": {
                    "id": "kjs8sa99",
                    "name": "Foo",
                    "version": 3
                }
            },
            {
                "id": "zxbbvngc.2",
                "index": {
                    "id": "foobar", "version": 0
                },
                "method_name": "add_isolate",
                "user": {
                    "id": "igboyes"
                },
                "otu": {
                    "id": "zxbbvngc",
                    "name": "Test",
                    "version": 2
                }
            },
            {
                "id": "zxbbvngc.1",
                "index": {
                    "id": "foobar", "version": 0
                },
                "method_name": "add_isolate",
                "user": {
                    "id": "igboyes"
                },
                "otu": {
                    "id": "zxbbvngc",
                    "name": "Test",
                    "version": 1
                }
            },
            {
                "id": "zxbbvngc.0",
                "index": {
                    "id": "foobar",
                    "version": 0
                },
                "user": {
                    "id": "igboyes"
                },
                "otu": {
                    "id": "zxbbvngc",
                    "name": "Test",
                    "version": 0
                }
            }
        ]
    }
