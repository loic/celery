.. _message-protocol:

===================
 Message Protocol
===================

.. contents::
    :local:

.. _message-protocol-task:
.. _internals-task-message-protocol:

Task messages
=============

.. _message-protocol-task-v2:

Version 2
---------

Definition
~~~~~~~~~~

.. code-block:: python

    # protocol v2 implies UTC=True
    # 'class' header existing means protocol is v2

    properties = {
        'correlation_id': uuid task_id,
        'content_type': string mimetype,
        'content_encoding': string encoding,

        # optional
        'reply_to': string queue_or_url,
    }
    headers = {
        'lang': string 'py'
        'task': string task,
        'id': uuid task_id,
        'root_id': uuid root_id,
        'parent_id': uuid parent_id,
        'group': uuid group_id,

        # optional
        'meth': string method_name,
        'shadow': string alias_name,
        'eta':  iso8601 eta,
        'expires'; iso8601 expires,
        'retries': int retries,
        'timelimit': (soft, hard),
    }

    body = (
        object[] args,
        Mapping kwargs,
        Mapping embed {
            'callbacks': Signature[] callbacks,
            'errbacks': Signature[] errbacks,
            'chain': Signature[] chain,
            'chord': Signature chord_callback,
        }
    )

Example
~~~~~~~

This example sends a task message using version 2 of the protocol:

.. code-block:: python

    # chain: add(add(add(2, 2), 4), 8) == 2 + 2 + 4 + 8

    task_id = uuid()
    basic_publish(
        message=json.dumps(([2, 2], {}, None),
        application_headers={
            'lang': 'py',
            'task': 'proj.tasks.add',
        }
        properties={
            'correlation_id': task_id,
            'content_type': 'application/json',
            'content_encoding': 'utf-8',
        }
    )

Changes from version 1
~~~~~~~~~~~~~~~~~~~~~~

- Protocol version detected by the presence of a ``task`` message header.

- Support for multiple languages via the ``lang`` header.

    Worker may redirect the message to a worker that supports
    the language.

- Metadata moved to headers.

    This means that workers/intermediates can inspect the message
    and make decisions based on the headers without decoding
    the payload (which may be language specific, e.g. serialized by the
    Python specific pickle serializer).

- Body is only for language specific data.

    - Python stores args/kwargs and embedded signatures in body.

    - If a message uses raw encoding then the raw data
      will be passed as a single argument to the function.

    - Java/C, etc. can use a thrift/protobuf document as the body

- Dispatches to actor based on ``task``, ``meth`` headers

    ``meth`` is unused by python, but may be used in the future
    to specify class+method pairs.

- Chain gains a dedicated field.

    Reducing the chain into a recursive ``callbacks`` argument
    causes problems when the recursion limit is exceeded.

    This is fixed in the new message protocol by specifying
    a list of signatures, each task will then pop a task off the list
    when sending the next message::

        execute_task(message)
        chain = embed['chain']
        if chain:
            sig = maybe_signature(chain.pop())
            sig.apply_async(chain=chain)

- ``correlation_id`` replaces ``task_id`` field.

- ``root_id`` and ``parent_id`` fields helps keep track of workflows.

- ``shadow`` lets you specify a different name for logs, monitors
  can be used for e.g. meta tasks that calls any function::

    from celery.utils.imports import qualname

    class PickleTask(Task):
        abstract = True

        def unpack_args(self, fun, args=()):
            return fun, args

        def apply_async(self, args, kwargs, **options):
            fun, real_args = self.unpack_args(*args)
            return super(PickleTask, self).apply_async(
                (fun, real_args, kwargs), shadow=qualname(fun), **options
            )

    @app.task(base=PickleTask)
    def call(fun, args, kwargs):
        return fun(*args, **kwargs)


.. _message-protocol-task-v1:
.. _task-message-protocol-v1:

Version 1
---------

In version 1 of the protocol all fields are stored in the message body,
which means workers and intermediate consumers must deserialize the payload
to read the fields.

Message body
~~~~~~~~~~~~

* task
    :`string`:

    Name of the task. **required**

* id
    :`string`:

    Unique id of the task (UUID). **required**

* args
    :`list`:

    List of arguments. Will be an empty list if not provided.

* kwargs
    :`dictionary`:

    Dictionary of keyword arguments. Will be an empty dictionary if not
    provided.

* retries
    :`int`:

    Current number of times this task has been retried.
    Defaults to `0` if not specified.

* eta
    :`string` (ISO 8601):

    Estimated time of arrival. This is the date and time in ISO 8601
    format. If not provided the message is not scheduled, but will be
    executed asap.

* expires
    :`string` (ISO 8601):

    .. versionadded:: 2.0.2

    Expiration date. This is the date and time in ISO 8601 format.
    If not provided the message will never expire. The message
    will be expired when the message is received and the expiration date
    has been exceeded.

* taskset
    :`string`:

    The taskset this task is part of (if any).

* chord
    :`Signature`:

    .. versionadded:: 2.3

    Signifies that this task is one of the header parts of a chord.  The value
    of this key is the body of the cord that should be executed when all of
    the tasks in the header has returned.

* utc
    :`bool`:

    .. versionadded:: 2.5

    If true time uses the UTC timezone, if not the current local timezone
    should be used.

* callbacks
    :`<list>Signature`:

    .. versionadded:: 3.0

    A list of signatures to call if the task exited successfully.

* errbacks
    :`<list>Signature`:

    .. versionadded:: 3.0

    A list of signatures to call if an error occurs while executing the task.

* timelimit
    :`<tuple>(float, float)`:

    .. versionadded:: 3.1

    Task execution time limit settings. This is a tuple of hard and soft time
    limit value (`int`/`float` or :const:`None` for no limit).

    Example value specifying a soft time limit of 3 seconds, and a hard time
    limt of 10 seconds::

        {'timelimit': (3.0, 10.0)}


Example message
~~~~~~~~~~~~~~~

This is an example invocation of a `celery.task.ping` task in JSON
format:

.. code-block:: javascript

    {"id": "4cc7438e-afd4-4f8f-a2f3-f46567e7ca77",
     "task": "celery.task.PingTask",
     "args": [],
     "kwargs": {},
     "retries": 0,
     "eta": "2009-11-17T12:30:56.527191"}

Task Serialization
------------------

Several types of serialization formats are supported using the
`content_type` message header.

The MIME-types supported by default are shown in the following table.

    =============== =================================
         Scheme                 MIME Type
    =============== =================================
    json            application/json
    yaml            application/x-yaml
    pickle          application/x-python-serialize
    msgpack         application/x-msgpack
    =============== =================================
