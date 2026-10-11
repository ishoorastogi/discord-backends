**This is for match engine**

## Event schema

Events use UTF-8 newline-delimited JSON: one JSON object per line, terminated
by a newline. The maximum message size is 1 MiB (1,048,576 bytes), excluding
the terminating newline.

Each event requires two nonempty top-level objects, `resume` and `internship`:

- `resume` requires `id` and `text`. The `text` field contains extracted resume text.
- `internship` requires `id`.

All other fields are optional and subject to change.

Example event (send with a terminating newline):

```json
{"resume":{"id":"resume-123","text":"Python developer with SQL experience"},"internship":{"id":"internship-456","title":"Software Engineering Intern","description":"Python and SQL"}}
```

Newlines inside text must be JSON-escaped as `\n`, rather than literal newlines
that would split the event across lines.
