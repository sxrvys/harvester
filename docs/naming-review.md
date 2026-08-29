# Naming review: first ten bundles

The stable contract is:

```text
<primary subject>[_<specific context or credit>]_<instagram ID>
```

The Instagram ID is always retained. Automatic naming is appropriate only when
the caption contains explicit structure. Prose-only captions receive an editorial
proposal for review; HARVEST should not pretend that arbitrary word truncation is
a meaningful summary.

| Source ID | Proposed readable name | Evidence |
|---|---|---|
| `DcSvEX4IWu7` | `shame-1968_ingmar-bergman_DcSvEX4IWu7` | Explicit title/creator line |
| `DXwmj7bitr0` | `streetwise_martin-bell-1984_DXwmj7bitr0` | Standalone work title and credit line |
| `DYq_kZXMZ6y` | `cwalk-footwork-tutorial_v-step-back-step_DYq_kZXMZ6y` | Title and labeled footwork name |
| `DaUV1RBsnbC` | `cwalk-footwork-tutorial_DaUV1RBsnbC` | Short explicit title |
| `DZWc7PMC10J` | `mario-savio_free-speech-movement-1964_DZWc7PMC10J` | Repeated named subject, movement, and year |
| `DZfdM4cs3y2` | `belfast-unrest_stuart-griffiths_DZfdM4cs3y2` | Location/event and named photographer |
| `DYpapJIOqys` | `giglio-lift-capo-calls_monsignor-cassato_DYpapJIOqys` | Named tradition, action, and speaker |
| `DaV8DkIC6lE` | `jim-jordan_congressional-aide-clip_DaV8DkIC6lE` | Named subject and clip context |
| `DZsSYNGDdDl` | `wombat-rescue_rehabilitation_DZsSYNGDdDl` | Repeated organization/subject and activity |
| `DZ8cdUWJ8GE` | `micah-washington_civil-rights-lawsuit_DZ8cdUWJ8GE` | Named subject and explicit event |

The first four can be derived by deterministic structural rules. The remaining
six are good editorial proposals, but require either user approval or a later,
explicit entity/keyphrase extractor before HARVEST applies them automatically.
