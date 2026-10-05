# Skill tag taxonomy

Skill tags (`skill_tags`) are the shared vocabulary that team skills, drills and training plans use. Each tag has
an `id`, an `area` (technical, tactical, mental, goalkeeping, physical), a `label`, and `level_1`, `level_3`,
`level_5`: what Developing, Achieving and Excelling look like on the shared 1–5 scale, relative to the player's
age group.

Team matrices link each skill to one or more tags (`matrix_skill_tags`, per matrix version, weight 1.0 Main or
0.5 Partial). A player's level on a tag is the weighted average of their coach scores on the skills that feed it.

## The rule

A tag's **id** never changes and is never deleted, and its **meaning** never changes. Only its wording can be
improved. Drills, mappings and past tag levels all refer to the id.

| Change | How | Effect |
| --- | --- | --- |
| Clearer wording, same meaning | Update the row in place | None |
| New tag | Insert a row | Available to new matrix versions and drills |
| Tag no longer wanted | Set `active = false` | Old mappings and drills keep working; editors stop offering it |
| Meaning changes (split, merge, recalibrate) | Add new tag id(s) and retire the old one | Old matrix versions keep the old mapping; drills on the old tag need re-tagging |
| Rename an id | Not allowed; treat as a meaning change | |

## How to make a change

1. Add `skill_tags_vN.json` here containing only the new or changed rows (same fields as the table).
2. Add a migration that applies it: insert new rows, update wording, or set `active = false`. Never delete rows.
3. Get the change reviewed like any code change.

`test_skill_tag_ids_are_never_removed` fails if any id defined in a `skill_tags_v*.json` file is missing from the
database. Coaches cannot create tags; owners only choose from active tags when editing their matrix.

The `_v1` files are frozen: they record what migration 0007 loaded. Never edit them; a fresh database must end up
with the same data as one migrated earlier.
