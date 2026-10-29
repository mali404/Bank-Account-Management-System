# Injection templates

Jinja templates in `templates/injections/`. The runner passes `payload`
(the scenario goal) and, for the adaptive template, `feedback` (the mock
passes `held`).

| File | Style |
|---|---|
| `important_message.j2` | A marked block the model is told to apply |
| `tool_knowledge.j2` | An instruction phrased as a tool note |
| `ignore_previous.j2` | An instruction that replaces the user request |
| `authority.j2` | A compliance-desk instruction |
| `multilingual.j2` | The same instruction in another language |
| `split_payload.j2` | The instruction split across two parts |
| `encoded.j2` | The instruction as base64 of the payload |
| `adaptive.j2` | A revised instruction after `feedback` |

These are original short templates for this harness. A PyRIT orchestrator
that rewrites `adaptive.j2` from oracle feedback is M7.
