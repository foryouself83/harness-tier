# When the `wiki` gate blocks the promotion commit

`doc-sync` is the only **gate** that rebuilds `graph.yaml`, and it is not a promotion one — so
graph drift that reached the integration branch through a terminal commit surfaces here, as a
blocked promotion commit. Resolve it in place:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
```

Stage the rebuilt `graph.yaml` into the promotion commit. A failure naming a **structure**
violation instead — `wiki_id` format or duplicate, missing `title`, dangling `depends_on`, a
cycle, front matter that carries a `wiki_id` and does not parse — is a document's front matter
to fix; `--build` cannot resolve those.
