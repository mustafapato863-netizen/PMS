---
status: accepted
---

# Insights stays a working screen

Insights and Monthly Review can both be shown for the same month, which invites a second speaking deck. Insights stays a working analysis screen that can be presented. Monthly Review stays the only speaking deck, so the room has one spoken narrative and the two screens are not free to disagree on a live score.

## Considered Options

- **A second speaking deck.** Dress Insights in the Monthly Review narrative and presentation chrome. Rejected: two decks would split the spoken review, and the September story plus generated role actions would sit beside live evidence.
- **Open Monthly Review to the General Manager.** That role can open Insights and cannot open Monthly Review. Rejected as the reason to clone the deck. If that role needs the spoken script, the change is the Monthly Review allow-list, not a second narrative.

## Consequences

- A month with no live rows stays empty on Insights. That includes an empty headline. Insights does not fall back to a September narrative or to generated role actions.
- The two screens share live score math only. Insights does not call `buildFunctionDeepDiveFromRecords`, `buildTeamDeepDiveFromRecords`, or `buildRoleDetail` whole, because those builders still fill gaps from the September baseline and can invent role actions.
- Insights may walk Company, then Function, then Team or Role, and may show the live sections the Insights API already returns.
- The dock, the notes pad, the Mac cursor, and the light document stay on Monthly Review. Insights keeps its working appearance.
